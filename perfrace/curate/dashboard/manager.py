"""FIFO scheduling and tmux supervision for Pair Verification sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from perfrace.curate.dashboard.store import DashboardStore, parse_candidate_jsonl
from perfrace.curate.dashboard.events import (
    EventSnapshot,
    EventTracker,
)
from perfrace.curate.report import ReportState, read_report
from perfrace.curate.dashboard.session import (
    DEFAULT_CANDIDATE_AGENT,
    DEFAULT_CANDIDATE_MODEL,
    DEFAULT_CANDIDATE_TIMEOUT_SECONDS,
    DEFAULT_MODEL,
    REJECTION_FILENAME,
    SESSION_ROOT,
    _initial_prompt,
    _normalize_repo_url,
    archive_rejected_workspace,
    copilot_session_exists,
    create_session,
    estimate_session_cost_usd,
    find_session_report,
    is_rejected_workspace,
    load_session,
    promote_staging_workspace,
    refresh_workspace_path,
    session_invocation_active,
)
from perfrace.release.catalog import sync_release_catalog

logger = logging.getLogger(__name__)

IDLE_GRACE_SECONDS = 2.0
COMPLETED_STATES = frozenset({"accepted", "rejected"})
ATTENTION_ORDER = {
    "needs_human": 0,
    "running": 1,
    "queued": 2,
    "accepted": 3,
    "rejected": 3,
}


@dataclass
class DashboardConfig:
    instance_root: Path
    max_sessions: int = 4
    model: str = DEFAULT_MODEL
    candidate_agent: str = DEFAULT_CANDIDATE_AGENT
    candidate_model: str = DEFAULT_CANDIDATE_MODEL
    candidate_timeout_seconds: int = DEFAULT_CANDIDATE_TIMEOUT_SECONDS
    run_id: str = "default"
    session_root: Path | None = None
    release_catalog_path: Path | None = None


class DashboardManager:
    """Manage the candidate queue and reconcile live session state."""

    def __init__(self, store: DashboardStore, config: DashboardConfig):
        self.store = store
        self.config = config
        self.session_root = (config.session_root or SESSION_ROOT).expanduser().resolve()
        self.slot_limit = config.max_sessions
        self._listeners: set[asyncio.Queue[dict[str, Any]]] = set()
        self._task: asyncio.Task[None] | None = None
        self._trackers: dict[str, EventTracker] = {}
        self._sent_report_feedback: dict[str, str] = {}
        self._promotion_exit_requested: set[str] = set()
        self._idle_since: dict[str, float] = {}
        self._clock = time.monotonic

    async def start(self) -> None:
        await self.reconcile_existing_sessions()
        if self.config.release_catalog_path is not None:
            await asyncio.to_thread(self._sync_release_catalog)
        await self.fill_slots()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        self._listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._listeners.discard(queue)

    async def publish_snapshot(self) -> None:
        message = {"type": "snapshot", "payload": self.snapshot()}
        for queue in list(self._listeners):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)

    def snapshot(self) -> dict[str, Any]:
        sessions = sorted(
            self.store.sessions(),
            key=lambda item: (
                ATTENTION_ORDER.get(item["state"], 9),
                item["started_at"],
            ),
        )
        return {
            "runId": self.config.run_id,
            "slotLimit": self.slot_limit,
            "sessions": [self._serialize_session(item) for item in sessions],
            "queue": self.store.queued_candidates(),
        }

    @staticmethod
    def _serialize_session(session: dict[str, Any]) -> dict[str, Any]:
        elapsed_until = session["updated_at"] if session["state"] in COMPLETED_STATES else None
        return {
            "session_id": session["session_id"],
            "repo_url": session["repo_url"],
            "instance_id": (
                Path(session["instance_path"]).name if session["instance_path"] else None
            ),
            "state": session["state"],
            "stage": session["stage"],
            "engagement_kind": session["engagement_kind"],
            "engagement_reason": session["engagement_reason"],
            "started_at": session["started_at"],
            "updated_at": session["updated_at"],
            "elapsed_until": elapsed_until,
            "disposition": session["disposition"],
            "live_cost_usd": session["live_cost_usd"],
            "human_comments": session["human_comments"],
            "error": session["error"],
            "candidate": session["candidate"],
        }

    async def add_candidate(self, payload: dict[str, Any]) -> int:
        _normalize_repo_url(str(payload.get("repo_url") or ""))
        candidate_id = self.store.add_candidate(payload)
        await self.fill_slots()
        await self.publish_snapshot()
        return candidate_id

    async def import_jsonl(self, content: str) -> list[int]:
        for line_number, payload in enumerate(parse_candidate_jsonl(content), start=1):
            try:
                _normalize_repo_url(str(payload.get("repo_url") or ""))
            except ValueError as exc:
                raise ValueError(f"line {line_number}: {exc}") from exc
        candidate_ids = self.store.import_jsonl(content)
        await self.fill_slots()
        await self.publish_snapshot()
        return candidate_ids

    async def add_slot(self) -> int:
        self.slot_limit += 1
        await self.fill_slots()
        await self.publish_snapshot()
        return self.slot_limit

    async def reconcile_existing_sessions(self) -> None:
        for state_path in sorted(self.session_root.glob("*/state.json")):
            try:
                state, session_dir = load_session(
                    state_path.parent.name,
                    session_root=self.session_root,
                )
                state = refresh_workspace_path(state, session_dir)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
            existing = self.store.session(state.session_id)
            candidate_id = (
                existing["candidate_id"]
                if existing
                else self.store.candidate_id_for_session(state.session_id)
            )
            self.store.upsert_session(
                self._session_values(
                    state,
                    session_dir,
                    candidate_id=candidate_id,
                    state_name="running",
                )
            )
            stored = self.store.session(state.session_id)
            if stored is not None:
                try:
                    report = read_report(find_session_report(state, session_dir))
                except (OSError, TypeError, ValueError) as exc:
                    self._mark_session_refresh_error(state.session_id, exc)
                    continue
                disposition = report.status if report else None
                if (
                    disposition not in {"ACCEPT", "REJECT"}
                    and not self.tmux_exists(stored["tmux_name"])
                    and not session_invocation_active(session_dir)
                ):
                    worker_state = self._worker_state(session_dir)
                    wait_for_resume = worker_state.get(
                        "state"
                    ) == "needs_human" or copilot_session_exists(state, session_dir)
                    error = self._start_tmux(
                        state,
                        stored["tmux_name"],
                        wait_for_resume=wait_for_resume,
                    )
                    if error is not None or wait_for_resume:
                        self.store.update_session(
                            state.session_id,
                            state="needs_human",
                            engagement_kind="failed",
                            engagement_reason=(
                                error
                                or worker_state.get("message")
                                or "Resume required after dashboard restart."
                            ),
                            error=error,
                        )
        for candidate in self.store.claimed_candidates_without_session():
            state_path = self.session_root / candidate["session_id"] / "state.json"
            if state_path.exists():
                workspace_path = (
                    self.config.instance_root
                    / ".staging"
                    / self.config.run_id
                    / candidate["session_id"]
                )
                self.store.upsert_session(
                    {
                        "session_id": candidate["session_id"],
                        "candidate_id": candidate["id"],
                        "repo_url": candidate["repo_url"],
                        "model": self.config.model,
                        "state": "needs_human",
                        "stage": "Explore & Design",
                        "engagement_kind": "failed",
                        "engagement_reason": "Session metadata is unreadable.",
                        "started_at": candidate["created_at"],
                        "disposition": None,
                        "tmux_name": (
                            f"perfrace-pv-{self.config.run_id}-{candidate['session_id']}"
                        ),
                        "session_dir": str(state_path.parent),
                        "workspace_path": str(workspace_path),
                        "instance_path": None,
                        "live_cost_usd": None,
                        "human_comments": 0,
                        "error": "Session state could not be loaded.",
                    }
                )
                continue
            await self._launch_claimed_candidate(
                candidate,
                candidate["session_id"],
            )
        await self.refresh_sessions()

    async def fill_slots(self) -> None:
        unfinished = sum(
            session["state"] not in COMPLETED_STATES for session in self.store.sessions()
        )
        available = max(self.slot_limit - unfinished, 0)
        for candidate in self.store.queued_candidates()[:available]:
            await self._launch_candidate(candidate)

    async def _launch_candidate(self, candidate: dict[str, Any]) -> None:
        session_id = str(uuid.uuid4())
        if not self.store.claim_candidate(candidate["id"], session_id):
            return
        try:
            await self._launch_claimed_candidate(candidate, session_id)
        except (OSError, TypeError, ValueError):
            self.store.release_candidate_claim(candidate["id"], session_id)
            raise

    async def _launch_claimed_candidate(
        self,
        candidate: dict[str, Any],
        session_id: str,
    ) -> None:
        state, session_dir = create_session(
            candidate["repo_url"],
            self.config.model,
            self.config.instance_root,
            candidate_agent=self.config.candidate_agent,
            candidate_model=self.config.candidate_model,
            candidate_timeout_seconds=self.config.candidate_timeout_seconds,
            session_id=session_id,
            run_id=self.config.run_id,
            session_root=self.session_root,
        )
        tmux_name = f"perfrace-pv-{self.config.run_id}-{state.session_id}"
        values = self._session_values(
            state,
            session_dir,
            candidate_id=candidate["id"],
            state_name="running",
            tmux_name=tmux_name,
        )
        self.store.upsert_session(values)
        error = self._start_tmux(state, tmux_name)
        if error is not None:
            self.store.update_session(
                state.session_id,
                state="needs_human",
                engagement_kind="failed",
                engagement_reason=error,
                error=error,
            )
            return

    def _start_tmux(
        self,
        state: Any,
        tmux_name: str,
        *,
        wait_for_resume: bool = False,
    ) -> str | None:
        command_parts = [
            sys.executable,
            "-m",
            "perfrace.curate.dashboard.session",
            "worker",
            state.session_id,
        ]
        if wait_for_resume:
            command_parts.append("--wait-for-resume")
        tmux_environment = {
            "PERFRACE_VERIFICATION_SESSION_ROOT": str(self.session_root),
            "PERFRACE_INSTANCE_ROOT": state.instance_root,
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
        }
        environment_args = [
            argument
            for key, value in tmux_environment.items()
            for argument in ("-e", f"{key}={value}")
        ]
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "new-session",
                    "-d",
                    *environment_args,
                    "-s",
                    tmux_name,
                    "-c",
                    state.workspace_path,
                    shlex.join(command_parts),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return f"failed to start tmux session: {exc}"
        if result.returncode == 0:
            return None
        return result.stderr.strip() or "failed to start tmux session"

    def _session_values(
        self,
        state: Any,
        session_dir: Path,
        *,
        candidate_id: int | None,
        state_name: str,
        tmux_name: str | None = None,
    ) -> dict[str, Any]:
        workspace_path = Path(state.workspace_path)
        is_formal_instance = self._is_formal_instance_workspace(
            workspace_path,
            Path(state.instance_root),
        )
        return {
            "session_id": state.session_id,
            "candidate_id": candidate_id,
            "repo_url": state.repo_url,
            "model": state.model,
            "state": state_name,
            "stage": "Explore & Design",
            "engagement_kind": None,
            "engagement_reason": None,
            "started_at": state.started_at,
            "disposition": None,
            "tmux_name": (tmux_name or f"perfrace-pv-{self.config.run_id}-{state.session_id}"),
            "session_dir": str(session_dir),
            "workspace_path": str(workspace_path),
            "instance_path": str(workspace_path) if is_formal_instance else None,
            "live_cost_usd": 0.0,
            "human_comments": 0,
            "error": None,
        }

    async def refresh_sessions(self) -> None:
        for stored in self.store.sessions():
            if stored["state"] in COMPLETED_STATES:
                continue
            try:
                await self._refresh_session(stored)
            except (OSError, TypeError, ValueError) as exc:
                self._mark_session_refresh_error(stored["session_id"], exc)

    def _sync_release_catalog(self, required_instance: str | None = None) -> None:
        catalog_path = self.config.release_catalog_path
        if catalog_path is None:
            return
        instances = sync_release_catalog(self.config.instance_root, catalog_path)
        if required_instance is not None and required_instance not in instances:
            raise ValueError(
                f"accepted instance has no active release record: {required_instance}"
            )

    def _send_report_feedback(self, session_id: str, error: Exception) -> None:
        """Queue one report-format correction in an active Copilot terminal."""
        detail = " ".join(str(error).split())
        if "report.md" not in detail:
            return
        if self._sent_report_feedback.get(session_id) == detail:
            return
        stored = self.store.session(session_id)
        if stored is None:
            return
        session_dir = Path(stored["session_dir"])
        tmux_name = str(stored["tmux_name"])
        if not session_invocation_active(session_dir) or not self.tmux_exists(tmux_name):
            return
        feedback = (
            f"Manager feedback: {detail}. Fix report.md front matter using exact values: "
            "status is IN_PROGRESS, ACCEPT, REVISE, or REJECT; review fields are "
            "PENDING, APPROVED, REVISE, or REJECTED. Put limitations in the report "
            f"body, then run `perfrace lint {stored['workspace_path']}`."
        )
        for keys in (("-l", feedback), ("Enter",)):
            result = subprocess.run(
                ["tmux", "send-keys", "-t", tmux_name, *keys],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(
                    "Could not send report feedback to %s: %s",
                    session_id,
                    result.stderr.strip() or "tmux send-keys failed",
                )
                return
        self._sent_report_feedback[session_id] = detail

    def _rejection_pending(self, session_id: str) -> bool:
        """Return whether this session has an unfinished rejection move."""
        stored = self.store.session(session_id)
        if stored is None:
            return False
        return (Path(stored["session_dir"]) / REJECTION_FILENAME).is_file()

    def _mark_session_refresh_error(self, session_id: str, error: Exception) -> None:
        self._send_report_feedback(session_id, error)
        reason = f"Session artifacts are unreadable: {error}"
        changes: dict[str, Any] = {
            "state": "needs_human",
            "engagement_kind": "failed",
            "engagement_reason": reason,
            "error": str(error),
        }
        if self._rejection_pending(session_id):
            changes["instance_path"] = None
        self.store.update_session(session_id, **changes)

    async def _refresh_session(self, stored: dict[str, Any]) -> None:
        await asyncio.to_thread(self._refresh_session_sync, stored)

    def _refresh_session_sync(self, stored: dict[str, Any]) -> None:
        session_id = stored["session_id"]
        try:
            state, session_dir = load_session(
                session_id,
                session_root=self.session_root,
            )
            if is_rejected_workspace(
                Path(state.workspace_path),
                Path(state.instance_root),
                state.run_id,
                session_id,
            ):
                self.store.update_session(
                    session_id,
                    workspace_path=state.workspace_path,
                    instance_path=None,
                )
                stored = {
                    **stored,
                    "workspace_path": state.workspace_path,
                    "instance_path": None,
                }
            state = refresh_workspace_path(state, session_dir)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            self._send_report_feedback(session_id, exc)
            reason = f"Session metadata is unreadable: {exc}"
            changes: dict[str, Any] = {
                "state": "needs_human",
                "engagement_kind": "failed",
                "engagement_reason": reason,
                "error": str(exc),
            }
            if self._rejection_pending(session_id):
                changes["instance_path"] = None
            self.store.update_session(session_id, **changes)
            return

        report = read_report(find_session_report(state, session_dir))
        self._sent_report_feedback.pop(session_id, None)
        if (
            report is not None
            and report.status == "REJECT"
            and stored["instance_path"] is not None
        ):
            self.store.update_session(session_id, instance_path=None)
            stored = {**stored, "instance_path": None}
        event_path = session_dir / "copilot-home" / "session-state" / session_id / "events.jsonl"
        tracker = self._trackers.setdefault(
            session_id,
            EventTracker(_initial_prompt(state, session_dir)),
        )
        event_snapshot = tracker.refresh(
            event_path,
            sorted(session_dir.glob("otel-*.jsonl")),
        )
        event_snapshot = self._debounce_idle(session_id, event_snapshot)
        worker_state = self._worker_state(session_dir)
        tmux_alive = self.tmux_exists(stored["tmux_name"])
        invocation_active = session_invocation_active(session_dir)
        disposition = report.status if report else None
        stage = self._current_stage(report)
        finalization_pending = False
        catalog_error = None
        if report is not None and disposition == "ACCEPT":
            try:
                self._sync_release_catalog(report.instance)
            except (OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                catalog_error = f"Release catalog sync failed: {exc}"
        if report is not None and disposition == "ACCEPT":
            workspace = Path(state.workspace_path)
            if catalog_error is not None:
                self._promotion_exit_requested.discard(session_id)
                disposition = None
                state_name = "needs_human"
            elif self._is_staging_workspace(workspace, Path(state.instance_root)):
                if invocation_active:
                    finalization_pending = True
                    disposition = None
                    state_name = "running"
                    copilot_idle = (
                        event_snapshot.needs_human and event_snapshot.engagement_kind == "idle"
                    )
                    if (
                        copilot_idle
                        and tmux_alive
                        and session_id not in self._promotion_exit_requested
                    ):
                        exit_error = self._request_copilot_exit(stored["tmux_name"])
                        if exit_error is not None:
                            self.store.update_session(
                                session_id,
                                state="needs_human",
                                engagement_kind="failed",
                                engagement_reason=exit_error,
                                error=exit_error,
                            )
                            return
                        self._promotion_exit_requested.add(session_id)
                else:
                    try:
                        state = promote_staging_workspace(
                            state,
                            session_dir,
                            report.instance,
                        )
                    except (OSError, ValueError) as exc:
                        self.store.update_session(
                            session_id,
                            state="needs_human",
                            engagement_kind="failed",
                            engagement_reason=str(exc),
                            error=str(exc),
                        )
                        return
                    workspace = Path(state.workspace_path)
                    self._promotion_exit_requested.discard(session_id)
                    if (
                        not self._is_formal_instance_workspace(
                            workspace,
                            Path(state.instance_root),
                        )
                        or workspace.name != report.instance
                    ):
                        self.store.update_session(
                            session_id,
                            state="needs_human",
                            engagement_kind="failed",
                            engagement_reason="Accepted report is not at its final instance path.",
                            error="Accepted report is not at its final instance path.",
                        )
                        return
                    state_name = "accepted"
            elif (
                not self._is_formal_instance_workspace(
                    workspace,
                    Path(state.instance_root),
                )
                or workspace.name != report.instance
            ):
                self.store.update_session(
                    session_id,
                    state="needs_human",
                    engagement_kind="failed",
                    engagement_reason="Accepted report is not at its final instance path.",
                    error="Accepted report is not at its final instance path.",
                )
                return
            else:
                self._promotion_exit_requested.discard(session_id)
                state_name = "accepted"
        elif report is not None and disposition == "REJECT":
            workspace = Path(state.workspace_path)
            if not is_rejected_workspace(
                workspace,
                Path(state.instance_root),
                state.run_id,
                session_id,
            ):
                if invocation_active:
                    finalization_pending = True
                    disposition = None
                    state_name = "running"
                    copilot_idle = (
                        event_snapshot.needs_human and event_snapshot.engagement_kind == "idle"
                    )
                    if (
                        copilot_idle
                        and tmux_alive
                        and session_id not in self._promotion_exit_requested
                    ):
                        exit_error = self._request_copilot_exit(stored["tmux_name"])
                        if exit_error is not None:
                            self.store.update_session(
                                session_id,
                                state="needs_human",
                                engagement_kind="failed",
                                engagement_reason=exit_error,
                                instance_path=None,
                                error=exit_error,
                            )
                            return
                        self._promotion_exit_requested.add(session_id)
                else:
                    try:
                        state = archive_rejected_workspace(
                            state,
                            session_dir,
                            state.run_id,
                        )
                    except (OSError, ValueError) as exc:
                        self.store.update_session(
                            session_id,
                            state="needs_human",
                            engagement_kind="failed",
                            engagement_reason=str(exc),
                            instance_path=None,
                            error=str(exc),
                        )
                        return
                    workspace = Path(state.workspace_path)
                    self.store.update_session(
                        session_id,
                        workspace_path=state.workspace_path,
                        instance_path=None,
                    )
                    stored = {
                        **stored,
                        "workspace_path": state.workspace_path,
                        "instance_path": None,
                    }
                    self._promotion_exit_requested.discard(session_id)
                    if not is_rejected_workspace(
                        workspace,
                        Path(state.instance_root),
                        state.run_id,
                        session_id,
                    ):
                        self.store.update_session(
                            session_id,
                            state="needs_human",
                            engagement_kind="failed",
                            engagement_reason="Rejected workspace was not archived.",
                            instance_path=None,
                            error="Rejected workspace was not archived.",
                        )
                        return
                    state_name = "rejected"
            else:
                self._promotion_exit_requested.discard(session_id)
                state_name = "rejected"
        else:
            self._promotion_exit_requested.discard(session_id)
            state_name = "running"

        recovery_error = None
        if state_name not in COMPLETED_STATES and not tmux_alive and not invocation_active:
            recovery_error = self._start_tmux(
                state,
                stored["tmux_name"],
                wait_for_resume=True,
            )
            if recovery_error is None:
                tmux_alive = True
                worker_state = {
                    "state": "needs_human",
                    "message": (
                        worker_state.get("message") or "Resume required after dashboard restart."
                    ),
                }
        engagement_kind = None
        engagement_reason = None
        error = event_snapshot.error
        if state_name not in COMPLETED_STATES:
            if catalog_error is not None:
                engagement_kind = "failed"
                engagement_reason = catalog_error
                error = catalog_error
            elif finalization_pending and session_id in self._promotion_exit_requested:
                state_name = "running"
            elif event_snapshot.needs_human:
                state_name = "needs_human"
                engagement_kind = event_snapshot.engagement_kind
                engagement_reason = event_snapshot.engagement_reason
            elif event_snapshot.failed:
                state_name = "needs_human"
                engagement_kind = "failed"
                engagement_reason = event_snapshot.error or "Copilot session error."
            elif not invocation_active and (
                worker_state.get("state") == "needs_human" or not tmux_alive
            ):
                state_name = "needs_human"
                engagement_kind = "failed"
                engagement_reason = str(
                    recovery_error
                    or worker_state.get("message")
                    or "Pair Verification process is not running."
                )
                error = error or engagement_reason

        live_cost = event_snapshot.live_cost_usd
        final_cost = estimate_session_cost_usd(session_dir)
        if live_cost is None:
            pass
        elif final_cost is not None:
            live_cost = max(live_cost or 0.0, final_cost)
        elif any(session_dir.glob("usage-*.json")):
            live_cost = None

        workspace_path = Path(state.workspace_path)
        is_formal_instance = self._is_formal_instance_workspace(
            workspace_path,
            Path(state.instance_root),
        ) and not (report is not None and report.status == "REJECT")
        values = {
            "state": state_name,
            "stage": stage,
            "engagement_kind": engagement_kind,
            "engagement_reason": engagement_reason,
            "disposition": disposition if disposition in {"ACCEPT", "REJECT"} else None,
            "workspace_path": str(workspace_path),
            "instance_path": str(workspace_path) if is_formal_instance else None,
            "live_cost_usd": live_cost,
            "human_comments": event_snapshot.human_interactions,
            "error": error,
        }
        changes = {key: value for key, value in values.items() if stored.get(key) != value}
        if changes:
            self.store.update_session(session_id, **changes)

    def _debounce_idle(
        self,
        session_id: str,
        snapshot: EventSnapshot,
    ) -> EventSnapshot:
        """Publish idle only after it remains stable across the grace period."""
        if not (snapshot.needs_human and snapshot.engagement_kind == "idle"):
            self._idle_since.pop(session_id, None)
            return snapshot
        now = self._clock()
        idle_since = self._idle_since.setdefault(session_id, now)
        if now - idle_since >= IDLE_GRACE_SECONDS:
            return snapshot
        return replace(
            snapshot,
            needs_human=False,
            engagement_kind=None,
            engagement_reason=None,
        )

    @staticmethod
    def _is_formal_instance_workspace(workspace: Path, instance_root: Path) -> bool:
        """Return whether a workspace is a visible direct child of the instance root."""
        root = instance_root.expanduser().resolve()
        absolute = Path(os.path.abspath(workspace.expanduser()))
        try:
            relative = absolute.relative_to(root)
        except ValueError:
            return False
        return len(relative.parts) == 1 and not relative.parts[0].startswith(".")

    @staticmethod
    def _is_staging_workspace(workspace: Path, instance_root: Path) -> bool:
        """Return whether a workspace is beneath this instance root's staging area."""
        root = instance_root.expanduser().resolve()
        absolute = Path(os.path.abspath(workspace.expanduser()))
        try:
            relative = absolute.relative_to(root)
        except ValueError:
            return False
        return len(relative.parts) > 1 and relative.parts[0] == ".staging"

    @staticmethod
    def _current_stage(report: ReportState | None) -> str:
        if report is None:
            return "Explore & Design"
        for field, stage in (
            ("realism", "Explore & Design"),
            ("reliability", "Build & Calibrate"),
            ("integrity", "Validate Integrity"),
        ):
            if getattr(report, field) != "APPROVED":
                return stage
        return "Finalize"

    @staticmethod
    def _worker_state(session_dir: Path) -> dict[str, Any]:
        path = session_dir / "worker-state.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def tmux_exists(name: str) -> bool:
        if shutil.which("tmux") is None:
            return False
        return (
            subprocess.run(
                ["tmux", "has-session", "-t", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )

    @staticmethod
    def _request_copilot_exit(tmux_name: str) -> str | None:
        """Ask an idle Copilot process to exit before workspace finalization."""
        for keys in (("C-u",), ("-l", "/exit"), ("Enter",)):
            result = subprocess.run(
                ["tmux", "send-keys", "-t", tmux_name, *keys],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or "tmux send-keys failed"
                return f"failed to stop Copilot before workspace finalization: {detail}"
        return None

    def _poll_interval_seconds(self) -> int:
        return 1 if any(session["state"] == "running" for session in self.store.sessions()) else 5

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval_seconds())
            await self.refresh_sessions()
            await self.fill_slots()
            await self.publish_snapshot()
