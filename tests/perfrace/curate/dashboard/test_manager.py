from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import yaml

from perfrace.curate.dashboard import manager as manager_module
from perfrace.curate.dashboard import session as session_module
from perfrace.curate.dashboard.events import EventSnapshot
from perfrace.curate.dashboard.manager import (
    IDLE_GRACE_SECONDS,
    DashboardConfig,
    DashboardManager,
)
from perfrace.curate.dashboard.store import DashboardStore
from perfrace.release.publisher import ReleaseRecord


def _session_values(session_id: str, candidate_id: int, state: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "candidate_id": candidate_id,
        "repo_url": f"https://github.com/example/{session_id}",
        "model": "gpt-5.6-sol",
        "state": state,
        "stage": "Explore & Design",
        "engagement_kind": None,
        "engagement_reason": None,
        "started_at": f"2026-08-29T00:00:0{candidate_id}Z",
        "disposition": None,
        "tmux_name": f"perfrace-pv-{session_id}",
        "session_dir": f"/tmp/{session_id}",
        "workspace_path": f"/tmp/{session_id}/workspace",
        "instance_path": None,
        "live_cost_usd": 0.0,
        "human_comments": 0,
        "error": None,
    }


def _write_release_record(instance_root: Path, instance: str) -> None:
    record = ReleaseRecord(
        schema_version=1,
        instance=instance,
        image=f"ghcr.io/example/{instance}@sha256:" + "a" * 64,
        task_artifact=f"ghcr.io/example/{instance}@sha256:" + "b" * 64,
        task_content_hash="sha256:" + "c" * 64,
        archive_digest="sha256:" + "d" * 64,
        packaged_files=3,
        published_at="2026-09-07T00:00:00Z",
    )
    releases = instance_root / ".releases"
    releases.mkdir(parents=True, exist_ok=True)
    (releases / f"{instance}.json").write_text(
        json.dumps(asdict(record)),
        encoding="utf-8",
    )


def test_fifo_slots_count_waiting_sessions_as_unfinished(tmp_path: Path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    candidate_ids = [
        store.add_candidate({"repo_url": f"https://github.com/example/repo-{index}"})
        for index in range(3)
    ]
    manager = DashboardManager(
        store,
        DashboardConfig(instance_root=tmp_path / "instances", max_sessions=2),
    )
    launched: list[int] = []

    async def fake_launch(candidate):
        launched.append(candidate["id"])
        store.upsert_session(
            _session_values(
                f"session-{candidate['id']}",
                candidate["id"],
                "needs_human" if candidate["id"] == 1 else "running",
            )
        )

    manager._launch_candidate = fake_launch  # type: ignore[method-assign]

    asyncio.run(manager.fill_slots())
    assert launched == candidate_ids[:2]
    assert [item["id"] for item in store.queued_candidates()] == candidate_ids[2:]

    asyncio.run(manager.add_slot())
    assert launched == candidate_ids
    assert manager.slot_limit == 3


def test_dashboard_persists_candidate_agent_and_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    store = DashboardStore(tmp_path / "state.db")
    candidate_id = store.add_candidate({"repo_url": "https://github.com/example/project"})
    candidate = store.queued_candidates()[0]
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            candidate_agent="claude-code",
            candidate_model="claude-sonnet-4-5",
            candidate_timeout_seconds=900,
            run_id="collaborator-20260830",
            session_root=tmp_path / "sessions",
        ),
    )
    monkeypatch.setattr(manager, "_start_tmux", lambda _state, _name: None)

    asyncio.run(
        manager._launch_claimed_candidate(
            candidate,
            "00000000-0000-4000-8000-000000000001",
        )
    )

    state, session_dir = session_module.load_session("00000000-0000-4000-8000-000000000001")
    assert state.candidate_agent == "claude-code"
    assert state.candidate_model == "claude-sonnet-4-5"
    assert state.candidate_timeout_seconds == 900
    config = yaml.safe_load((session_dir / "run.yaml").read_text(encoding="utf-8"))
    assert config["job"]["agents"][0]["name"] == "claude-code"
    assert config["job"]["agents"][0]["override_timeout_sec"] == 900
    assert store.session(state.session_id)["candidate_id"] == candidate_id
    assert store.session(state.session_id)["tmux_name"].startswith(
        "perfrace-pv-collaborator-20260830-"
    )


def test_manager_launches_internal_session_worker(monkeypatch, tmp_path: Path) -> None:
    manager = DashboardManager(
        DashboardStore(tmp_path / "state.db"),
        DashboardConfig(instance_root=tmp_path / "instances"),
    )
    state = SimpleNamespace(
        session_id="session-1",
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(tmp_path / "instances" / ".staging" / "session-1"),
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        ),
    )

    assert manager._start_tmux(state, "perfrace-pv-session-1", wait_for_resume=True) is None

    command = calls[0]
    worker_command = command[-1]
    assert "perfrace.curate.dashboard.session worker session-1 --wait-for-resume" in (
        worker_command
    )


def test_snapshot_sorts_attention_before_running_and_completed(tmp_path: Path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    for index, state in enumerate(["accepted", "running", "needs_human"], start=1):
        candidate_id = store.add_candidate(
            {"repo_url": f"https://github.com/example/repo-{index}"}
        )
        store.upsert_session(_session_values(f"session-{index}", candidate_id, state))
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="collaborator-20260830",
            session_root=tmp_path / "sessions",
        ),
    )

    snapshot = manager.snapshot()

    assert snapshot["runId"] == "collaborator-20260830"
    assert [session["state"] for session in snapshot["sessions"]] == [
        "needs_human",
        "running",
        "accepted",
    ]
    by_state = {session["state"]: session for session in snapshot["sessions"]}
    assert by_state["needs_human"]["elapsed_until"] is None
    assert by_state["running"]["elapsed_until"] is None
    assert by_state["accepted"]["elapsed_until"] == by_state["accepted"]["updated_at"]


def test_formal_instance_detection_ignores_ancestor_reject_name(tmp_path: Path) -> None:
    instance_root = tmp_path / ".reject" / "instances"
    workspace = instance_root / "project--workload"

    assert DashboardManager._is_formal_instance_workspace(
        workspace,
        instance_root,
    )


def test_refresh_sessions_skips_completed_sessions(tmp_path: Path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(instance_root=tmp_path / "instances"),
    )
    for index, state in enumerate(("running", "accepted", "rejected"), start=1):
        candidate_id = store.add_candidate(
            {"repo_url": f"https://github.com/example/repo-{index}"}
        )
        store.upsert_session(_session_values(f"session-{index}", candidate_id, state))
    refreshed: list[str] = []

    async def fake_refresh(stored):
        refreshed.append(stored["session_id"])

    manager._refresh_session = fake_refresh  # type: ignore[method-assign]

    asyncio.run(manager.refresh_sessions())

    assert refreshed == ["session-1"]


def test_poll_interval_slows_when_no_session_is_running(tmp_path: Path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(instance_root=tmp_path / "instances"),
    )
    candidate_id = store.add_candidate({"repo_url": "https://github.com/example/project"})
    store.upsert_session(_session_values("session-1", candidate_id, "needs_human"))

    assert manager._poll_interval_seconds() == 5

    store.update_session("session-1", state="running")

    assert manager._poll_interval_seconds() == 1


def test_current_stage_comes_from_markdown_front_matter() -> None:
    report = session_module.ReportState(
        schema=1,
        instance="project--workload",
        status="IN_PROGRESS",
        realism="APPROVED",
        reliability="REVISE",
        integrity="PENDING",
        updated="2026-08-29T14:00:00Z",
    )
    assert DashboardManager._current_stage(report) == "Build & Calibrate"

    report = session_module.ReportState(
        schema=1,
        instance="project--workload",
        status="IN_PROGRESS",
        realism="APPROVED",
        reliability="APPROVED",
        integrity="REVISE",
        updated="2026-08-29T14:00:00Z",
    )
    assert DashboardManager._current_stage(report) == "Validate Integrity"


def test_idle_requires_stable_grace_period(tmp_path: Path) -> None:
    manager = DashboardManager(
        DashboardStore(tmp_path / "state.db"),
        DashboardConfig(instance_root=tmp_path / "instances"),
    )
    idle = EventSnapshot(
        needs_human=True,
        engagement_kind="idle",
        engagement_reason="Agent is idle.",
    )
    now = 100.0
    manager._clock = lambda: now

    first = manager._debounce_idle("session-1", idle)
    now += IDLE_GRACE_SECONDS - 0.1
    second = manager._debounce_idle("session-1", idle)
    now += 0.1
    stable = manager._debounce_idle("session-1", idle)
    active = manager._debounce_idle("session-1", EventSnapshot())
    restarted = manager._debounce_idle("session-1", idle)

    assert first.needs_human is False
    assert second.needs_human is False
    assert stable.needs_human is True
    assert active.needs_human is False
    assert restarted.needs_human is False


def test_refresh_keeps_staging_after_realism_approval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    report_path = Path(state.workspace_path) / "report.md"
    session_module.update_report(
        report_path,
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="IN_PROGRESS",
            realism="APPROVED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-08-29T14:00:00Z",
        ),
    )

    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=tmp_path / "sessions",
        ),
    )
    values = manager._session_values(
        state,
        session_dir,
        candidate_id=None,
        state_name="running",
    )
    store.upsert_session(values)
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: True)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed is not None
    assert refreshed["instance_path"] is None
    assert Path(refreshed["workspace_path"]) == Path(state.workspace_path)
    assert not (tmp_path / "instances" / "project--workload").exists()


def test_refresh_requests_idle_copilot_exit_before_final_promotion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-08-31T07:00:00Z",
        ),
    )
    event_path = session_dir / "copilot-home" / "session-state" / state.session_id / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(
        json.dumps({"type": "assistant.turn_end", "data": {}}) + "\n",
        encoding="utf-8",
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=tmp_path / "sessions",
        ),
    )
    values = manager._session_values(
        state,
        session_dir,
        candidate_id=None,
        state_name="running",
    )
    store.upsert_session(values)
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: True)
    exits: list[str] = []
    monkeypatch.setattr(
        manager,
        "_request_copilot_exit",
        lambda tmux_name: exits.append(tmux_name) or None,
    )
    ticks = iter((0.0, IDLE_GRACE_SECONDS))
    manager._clock = lambda: next(ticks)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))
    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed is not None
    assert refreshed["state"] == "running"
    assert refreshed["disposition"] is None
    assert refreshed["instance_path"] is None
    assert exits == [values["tmux_name"]]


def test_refresh_promotes_accepted_workspace_after_invocation_stops(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-08-31T07:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=tmp_path / "sessions",
        ),
    )
    values = manager._session_values(
        state,
        session_dir,
        candidate_id=None,
        state_name="running",
    )
    store.upsert_session(values)
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed is not None
    assert refreshed["state"] == "accepted"
    assert refreshed["disposition"] == "ACCEPT"
    assert Path(refreshed["instance_path"]).name == "project--workload"
    assert Path(refreshed["workspace_path"], "report.md").is_file()


def test_refresh_syncs_catalog_before_completing_accept(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    instance_root = tmp_path / "instances"
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        instance_root,
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-09-07T00:00:00Z",
        ),
    )
    _write_release_record(instance_root, "project--workload")
    store = DashboardStore(tmp_path / "state.db")
    catalog = tmp_path / "catalog.json"
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=instance_root,
            session_root=tmp_path / "sessions",
            release_catalog_path=catalog,
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "accepted"
    assert set(json.loads(catalog.read_text())["instances"]) == {"project--workload"}


def test_refresh_blocks_accept_without_release_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    instance_root = tmp_path / "instances"
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        instance_root,
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-09-07T00:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=instance_root,
            session_root=tmp_path / "sessions",
            release_catalog_path=tmp_path / "catalog.json",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)
    starts: list[bool] = []
    monkeypatch.setattr(
        manager,
        "_start_tmux",
        lambda _state, _name, *, wait_for_resume=False: starts.append(wait_for_resume) or None,
    )

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "needs_human"
    assert refreshed["disposition"] is None
    assert refreshed["workspace_path"] == state.workspace_path
    assert refreshed["instance_path"] is None
    assert starts == [True]
    assert refreshed["engagement_reason"] == (
        "Release catalog sync failed: accepted instance has no active release record: "
        "project--workload"
    )


def test_refresh_recovers_formal_accept_without_release_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    instance_root = tmp_path / "instances"
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        instance_root,
    )
    state = session_module.promote_staging_workspace(
        state,
        session_dir,
        "project--workload",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-09-07T00:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=instance_root,
            session_root=tmp_path / "sessions",
            release_catalog_path=tmp_path / "catalog.json",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)
    starts: list[bool] = []
    monkeypatch.setattr(
        manager,
        "_start_tmux",
        lambda _state, _name, *, wait_for_resume=False: starts.append(wait_for_resume) or None,
    )

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "needs_human"
    assert refreshed["workspace_path"] == state.workspace_path
    assert refreshed["instance_path"] == state.workspace_path
    assert starts == [True]
    assert refreshed["engagement_reason"] == (
        "Release catalog sync failed: accepted instance has no active release record: "
        "project--workload"
    )


def test_refresh_requests_idle_copilot_exit_before_reject_archival(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    state = session_module.promote_staging_workspace(
        state,
        session_dir,
        "project--workload",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="REJECT",
            realism="REJECTED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-09-01T04:00:00Z",
        ),
    )
    event_path = session_dir / "copilot-home" / "session-state" / state.session_id / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(
        json.dumps({"type": "assistant.turn_end", "data": {}}) + "\n",
        encoding="utf-8",
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    values = manager._session_values(
        state,
        session_dir,
        candidate_id=None,
        state_name="running",
    )
    store.upsert_session(values)
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: True)
    exits: list[str] = []
    monkeypatch.setattr(
        manager,
        "_request_copilot_exit",
        lambda tmux_name: exits.append(tmux_name) or None,
    )
    ticks = iter((0.0, IDLE_GRACE_SECONDS))
    manager._clock = lambda: next(ticks)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))
    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "running"
    assert refreshed["disposition"] is None
    assert refreshed["instance_path"] is None
    assert Path(refreshed["workspace_path"]).parent == (tmp_path / "instances").resolve()
    assert exits == [values["tmux_name"]]


def test_refresh_archives_rejected_workspace_after_invocation_stops(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="REJECT",
            realism="REJECTED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-09-01T04:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    expected = (tmp_path / "instances" / ".reject" / "review-run" / state.session_id).resolve()
    assert refreshed["state"] == "rejected"
    assert refreshed["disposition"] == "REJECT"
    assert refreshed["instance_path"] is None
    assert Path(refreshed["workspace_path"]) == expected
    assert (expected / "report.md").is_file()


def test_reject_exit_failure_clears_formal_instance_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    state = session_module.promote_staging_workspace(
        state,
        session_dir,
        "project--workload",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="REJECT",
            realism="REJECTED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-09-01T04:00:00Z",
        ),
    )
    event_path = session_dir / "copilot-home" / "session-state" / state.session_id / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(
        json.dumps({"type": "assistant.turn_end", "data": {}}) + "\n",
        encoding="utf-8",
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: True)
    monkeypatch.setattr(
        manager,
        "_request_copilot_exit",
        lambda _name: "could not exit Copilot",
    )
    ticks = iter((0.0, IDLE_GRACE_SECONDS))
    manager._clock = lambda: next(ticks)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))
    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "needs_human"
    assert refreshed["instance_path"] is None
    assert refreshed["error"] == "could not exit Copilot"


def test_reject_archive_failure_clears_formal_instance_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    state = session_module.promote_staging_workspace(
        state,
        session_dir,
        "project--workload",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="REJECT",
            realism="REJECTED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-09-01T04:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)

    def fail_archive(*_args):
        raise FileExistsError("archive collision")

    monkeypatch.setattr(manager_module, "archive_rejected_workspace", fail_archive)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "needs_human"
    assert refreshed["instance_path"] is None
    assert refreshed["error"] == "archive collision"


def test_rejection_recovery_failure_clears_formal_instance_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    state = session_module.promote_staging_workspace(
        state,
        session_dir,
        "project--workload",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="REJECT",
            realism="REJECTED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-09-01T04:00:00Z",
        ),
    )
    session_module.write_text(
        session_dir / session_module.REJECTION_FILENAME,
        json.dumps(
            {
                "source": state.workspace_path,
                "destination": str(tmp_path / "outside"),
            }
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "needs_human"
    assert refreshed["instance_path"] is None
    assert "path escapes the instance root" in refreshed["error"]


def test_post_archive_refresh_failure_keeps_rejected_workspace_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    session_module.update_report(
        Path(state.workspace_path) / "report.md",
        session_module.ReportState(
            schema=1,
            instance="project--workload",
            status="REJECT",
            realism="REJECTED",
            integrity="PENDING",
            reliability="PENDING",
            updated="2026-09-01T04:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)

    def fail_cost(_path):
        raise ValueError("usage is malformed")

    monkeypatch.setattr(manager_module, "estimate_session_cost_usd", fail_cost)

    asyncio.run(manager.refresh_sessions())

    refreshed = store.session(state.session_id)
    expected = (tmp_path / "instances" / ".reject" / "review-run" / state.session_id).resolve()
    assert refreshed["state"] == "needs_human"
    assert refreshed["workspace_path"] == str(expected)
    assert refreshed["instance_path"] is None
    assert refreshed["error"] == "usage is malformed"


def test_recovered_rejection_path_is_persisted_before_report_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    report_path = Path(state.workspace_path) / "report.md"
    report_path.write_text("---\nmalformed\n---\n", encoding="utf-8")
    destination = tmp_path / "instances" / ".reject" / "review-run" / state.session_id
    session_module.write_text(
        session_dir / session_module.REJECTION_FILENAME,
        json.dumps(
            {
                "source": state.workspace_path,
                "destination": str(destination),
            }
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            run_id="review-run",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )

    asyncio.run(manager.refresh_sessions())

    refreshed = store.session(state.session_id)
    assert refreshed["state"] == "needs_human"
    assert refreshed["workspace_path"] == str(destination.resolve())
    assert refreshed["instance_path"] is None
    assert "invalid report.md front matter line" in refreshed["error"]


def test_request_copilot_exit_sends_exit_command(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        ),
    )

    error = DashboardManager._request_copilot_exit("perfrace-pv-session-1")

    assert error is None
    assert [call[-2:] for call in calls] == [
        ["perfrace-pv-session-1", "C-u"],
        ["-l", "/exit"],
        ["perfrace-pv-session-1", "Enter"],
    ]


def test_reconciliation_does_not_duplicate_active_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session_root = tmp_path / "sessions"
    monkeypatch.setattr(session_module, "SESSION_ROOT", session_root)
    monkeypatch.setattr(manager_module, "SESSION_ROOT", session_root)
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        candidate_agent="claude-code",
        candidate_model="claude-sonnet-4-5",
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=tmp_path / "sessions",
        ),
    )
    starts: list[str] = []
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(
        manager,
        "_start_tmux",
        lambda _state, tmux_name, **_kwargs: starts.append(tmux_name),
    )

    with session_module.session_invocation_lock(session_dir):
        asyncio.run(manager.reconcile_existing_sessions())

    stored = store.session(state.session_id)
    assert stored is not None
    assert stored["state"] == "running"
    assert starts == []
    recovered, _ = session_module.load_session(state.session_id)
    assert recovered.candidate_agent == "claude-code"
    assert recovered.candidate_model == "claude-sonnet-4-5"


def test_missing_tmux_recreates_paused_worker_after_startup_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    (session_dir / "worker-state.json").write_text(
        json.dumps(
            {
                "state": "needs_human",
                "return_code": None,
                "message": "Pair Verification invocation failed: proxy startup failed",
            }
        )
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="needs_human",
        )
    )
    starts: list[bool] = []
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: False)
    monkeypatch.setattr(
        manager,
        "_start_tmux",
        lambda _state, _name, *, wait_for_resume=False: starts.append(wait_for_resume) or None,
    )

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    recovered = store.session(state.session_id)
    assert starts == [True]
    assert recovered["state"] == "needs_human"
    assert recovered["engagement_reason"].endswith("proxy startup failed")


def test_reconciliation_recovers_claim_before_session_creation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_root = tmp_path / "sessions"
    monkeypatch.setattr(session_module, "SESSION_ROOT", session_root)
    monkeypatch.setattr(manager_module, "SESSION_ROOT", session_root)
    store = DashboardStore(tmp_path / "state.db")
    candidate_id = store.add_candidate({"repo_url": "https://github.com/example/project"})
    session_id = "00000000-0000-4000-8000-000000000123"
    assert store.claim_candidate(candidate_id, session_id)
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            candidate_agent="claude-code",
            candidate_model="claude-sonnet-4-5",
            session_root=session_root,
        ),
    )
    monkeypatch.setattr(
        manager,
        "_start_tmux",
        lambda _state, _name, **_kwargs: "tmux disabled for test",
    )

    asyncio.run(manager.reconcile_existing_sessions())
    asyncio.run(manager.reconcile_existing_sessions())

    recovered = store.session(session_id)
    assert recovered is not None
    assert recovered["candidate_id"] == candidate_id
    assert len(store.sessions()) == 1
    assert store.queued_candidates() == []
    assert (session_root / session_id / "state.json").is_file()
    recovered_state, _ = session_module.load_session(session_id)
    assert recovered_state.candidate_agent == "claude-code"
    assert recovered_state.candidate_model == "claude-sonnet-4-5"


def test_refresh_isolates_malformed_session_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_root = tmp_path / "sessions"
    monkeypatch.setattr(session_module, "SESSION_ROOT", session_root)
    first, first_dir = session_module.create_session(
        "https://github.com/example/first",
        "gpt-5.6-sol",
        tmp_path / "first-instances",
    )
    second, second_dir = session_module.create_session(
        "https://github.com/example/second",
        "gpt-5.6-sol",
        tmp_path / "second-instances",
    )
    first_report_path = Path(first.workspace_path, "report.md")
    first_report_path.write_text("---\nmalformed\n---\n", encoding="utf-8")
    second_report_path = Path(second.workspace_path, "report.md")
    session_module.update_report(
        second_report_path,
        session_module.ReportState(
            schema=1,
            instance="second--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-08-29T14:00:00Z",
        ),
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=session_root,
        ),
    )
    for state, session_dir in ((first, first_dir), (second, second_dir)):
        store.upsert_session(
            manager._session_values(
                state,
                session_dir,
                candidate_id=None,
                state_name="running",
            )
        )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)

    asyncio.run(manager.refresh_sessions())

    malformed = store.session(first.session_id)
    assert malformed["state"] == "needs_human"
    assert malformed["engagement_reason"] == (
        "Session metadata is unreadable: invalid report.md front matter line: malformed"
    )
    assert store.session(second.session_id)["state"] == "accepted"


def test_manager_queues_report_feedback_once_for_active_copilot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = DashboardStore(tmp_path / "state.db")
    candidate_id = store.add_candidate({"repo_url": "https://github.com/example/project"})
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    values = _session_values("session-1", candidate_id, "running")
    values["session_dir"] = str(session_dir)
    values["workspace_path"] = str(tmp_path / "workspace")
    store.upsert_session(values)
    manager = DashboardManager(
        store,
        DashboardConfig(instance_root=tmp_path / "instances"),
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: True)
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        ),
    )
    error = ValueError("invalid report.md reliability: APPROVED_WITH_LIMITATION")

    manager._send_report_feedback("session-1", error)
    manager._send_report_feedback("session-1", error)

    assert len(calls) == 2
    assert calls[0][:5] == [
        "tmux",
        "send-keys",
        "-t",
        "perfrace-pv-session-1",
        "-l",
    ]
    assert "invalid report.md reliability" in calls[0][5]
    assert calls[1][-1] == "Enter"


def test_manager_does_not_send_feedback_to_worker_resume_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = DashboardStore(tmp_path / "state.db")
    candidate_id = store.add_candidate({"repo_url": "https://github.com/example/project"})
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    values = _session_values("session-1", candidate_id, "needs_human")
    values["session_dir"] = str(session_dir)
    store.upsert_session(values)
    manager = DashboardManager(
        store,
        DashboardConfig(instance_root=tmp_path / "instances"),
    )

    def fail_run(*_args, **_kwargs):
        raise AssertionError("tmux input must not be sent")

    monkeypatch.setattr(subprocess, "run", fail_run)
    monkeypatch.setattr(manager_module, "session_invocation_active", lambda _path: False)
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)

    manager._send_report_feedback(
        "session-1",
        ValueError("invalid report.md reliability: APPROVED_WITH_LIMITATION"),
    )


def test_unknown_live_model_keeps_cost_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_module, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = session_module.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    (session_dir / "usage-0001.json").write_text(
        json.dumps(
            {
                "totalUserRequests": 1,
                "modelMetrics": {
                    "gpt-5.6-sol": {
                        "usage": {
                            "inputTokens": 100,
                            "outputTokens": 10,
                            "cacheReadTokens": 20,
                            "cacheWriteTokens": 30,
                        }
                    }
                },
            }
        )
    )
    (session_dir / "otel-0002.jsonl").write_text(
        json.dumps(
            {
                "type": "span",
                "spanId": "unknown-chat",
                "attributes": {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.response.model": "unpriced-model",
                    "gen_ai.usage.input_tokens": 100,
                    "gen_ai.usage.output_tokens": 10,
                },
            }
        )
        + "\n"
    )
    store = DashboardStore(tmp_path / "state.db")
    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=tmp_path / "instances",
            session_root=tmp_path / "sessions",
        ),
    )
    store.upsert_session(
        manager._session_values(
            state,
            session_dir,
            candidate_id=None,
            state_name="running",
        )
    )
    monkeypatch.setattr(manager, "tmux_exists", lambda _name: True)

    asyncio.run(manager._refresh_session(store.session(state.session_id)))

    assert store.session(state.session_id)["live_cost_usd"] is None
