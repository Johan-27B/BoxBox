"""Fixed-per-trial TerminusBoxBox transition mechanism."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from .interfaces import (
    TaskPhase,
    FaultReport,
    ReviewResult,
    Runtime,
    RuntimeState,
    RuntimeTrap,
)

HARNESS_STATE_DIR = "/tmp/harness-state"
HARNESS_DIR = f"{HARNESS_STATE_DIR}/harness"
RUNTIME_STATE_NAME = ".runtime"
RUNTIME_STATE_DIR = f"{HARNESS_DIR}/{RUNTIME_STATE_NAME}"
REVIEW_USER = 65534
FAULT_LOG = f"{RUNTIME_STATE_DIR}/faults.jsonl"
TRANSITION_TIMEOUT = 3000
RESUME_ITERATION_GUIDANCE = (
    "Resume the original task from the current state. Use the new input as "
    "evidence, revise your plan, and continue making substantive progress."
)
RESUME_REVIEW_REMINDER = (
    "New target experience is available for independent harness review. You "
    "may call boxbox when recent target work provides new trajectory "
    "evidence for a useful harness adaptation; the review will decide whether "
    "to retain the active harness or activate an adaptation. Continue substantive "
    "target work when the prior review decision is the only new information."
)


async def prepare_runtime_state_dir(environment: BaseEnvironment) -> None:
    """Create the shared runtime state directory with stable reviewer ownership."""
    state = await environment.exec(
        (
            f"mkdir -p {shlex.quote(RUNTIME_STATE_DIR)} && "
            f"chown {REVIEW_USER}:{REVIEW_USER} {shlex.quote(RUNTIME_STATE_DIR)}"
        ),
        cwd=HARNESS_DIR,
        timeout_sec=30,
        user="root",
    )
    if state.return_code != 0:
        raise RuntimeError(
            state.stdout or state.stderr or "failed to prepare shared runtime state"
        )


@dataclass(frozen=True)
class Transition:
    """Kernel-owned review result used by its lifecycle loop."""

    context: AgentContext
    prompt: str


class Kernel:
    """Validate, activate, retain, or roll back commit-addressed runtimes."""

    def __init__(
        self,
        *,
        runtime_class: type[Runtime],
        logs: Path,
        constructor: dict[str, Any],
    ) -> None:
        self._logs = logs
        self._constructor = dict(constructor)
        self._active = self._create_runtime(runtime_class)
        self._active_commit: str | None = None
        self._confirmed = self._active
        self._confirmed_commit: str | None = None
        self._sequence = 0
        self._transitioning = False
        self._last_reviewed_fault_at: str | None = None

    @property
    def active_runtime(self) -> Runtime:
        """Return the runtime selected by the latest completed transition."""
        return self._active

    @property
    def active_commit(self) -> str:
        """Return the selected runtime commit."""
        if self._active_commit is None:
            raise RuntimeError("Kernel has not been bound to an initial commit")
        return self._active_commit

    @property
    def confirmed_runtime(self) -> Runtime:
        """Return the last runtime that reached a later voluntary review."""
        return self._confirmed

    @property
    def confirmed_commit(self) -> str:
        """Return the last confirmed runtime commit."""
        if self._confirmed_commit is None:
            raise RuntimeError("Kernel has not been bound to an initial commit")
        return self._confirmed_commit

    @property
    def has_provisional_runtime(self) -> bool:
        """Return whether the active runtime is awaiting confirmation."""
        return self._active is not self._confirmed

    @property
    def sequence(self) -> int:
        """Return the number of completed or entered review transitions."""
        return self._sequence

    def bind(self, *, commit: str) -> None:
        """Bind the fixed Kernel to the trial's initial runtime commit."""
        self._validate_sha(commit, "Initial runtime commit")
        if self._active_commit is not None:
            raise RuntimeError("Kernel is already bound")
        self._active_commit = commit
        self._confirmed_commit = commit

    def _confirm_active_runtime(self) -> None:
        """Promote the active provisional runtime at a voluntary review boundary."""
        self._confirmed = self._active
        self._confirmed_commit = self.active_commit

    @staticmethod
    def _merge_context(context: AgentContext, addition: AgentContext) -> None:
        """Accumulate one Kernel-managed runtime or review segment."""
        context.n_input_tokens = (context.n_input_tokens or 0) + (addition.n_input_tokens or 0)
        context.n_output_tokens = (context.n_output_tokens or 0) + (addition.n_output_tokens or 0)
        context.n_cache_tokens = (context.n_cache_tokens or 0) + (addition.n_cache_tokens or 0)
        if addition.cost_usd is not None:
            context.cost_usd = (context.cost_usd or 0.0) + addition.cost_usd
        context.rollout_details = [
            *(context.rollout_details or []),
            *(addition.rollout_details or []),
        ]
        if addition.metadata:
            metadata = dict(context.metadata or {})
            segments = list(metadata.get("internal_segments", []))
            segments.append(addition.metadata)
            metadata.update(addition.metadata)
            metadata["internal_segments"] = segments
            context.metadata = metadata

    async def setup(
        self,
        environment: BaseEnvironment,
        *,
        workdir: str,
        source: Path,
    ) -> None:
        """Deploy editable harness source, then load its initial runtime."""
        await environment.exec(
            f"mkdir -p {shlex.quote(HARNESS_DIR)}",
            cwd=workdir,
            timeout_sec=30,
        )
        await environment.upload_dir(
            source_dir=source,
            target_dir=HARNESS_DIR,
        )
        initialized = await environment.exec(
            (
                "git init -q && "
                "git symbolic-ref HEAD refs/heads/main && "
                "git config user.email 'runtime@terminus-boxbox.local' && "
                "git config user.name 'runtime' && "
                f"printf '{RUNTIME_STATE_NAME}/\\n__pycache__/\\n*.pyc\\n' > .gitignore && "
                "git add -A && "
                "git commit -q -m 'runtime: initial TerminusBoxBox' && "
                "git tag baseline && "
                "git rev-parse HEAD"
            ),
            cwd=HARNESS_DIR,
            timeout_sec=120,
        )
        lines = (initialized.stdout or "").strip().splitlines()
        if initialized.return_code != 0 or len(lines) != 1:
            raise RuntimeError(
                initialized.stdout
                or initialized.stderr
                or "failed to initialize TerminusBoxBox runtime Git"
            )
        permissions = await environment.exec(
            f"chown -R {REVIEW_USER}:{REVIEW_USER} {shlex.quote(HARNESS_DIR)}",
            cwd=workdir,
            timeout_sec=60,
            user="root",
        )
        if permissions.return_code != 0:
            raise RuntimeError(
                permissions.stdout
                or permissions.stderr
                or "failed to configure TerminusBoxBox review permissions"
            )
        self.bind(commit=lines[0])
        # Load the prepared copy, so both execution and newly forked reviewers
        # use the configured, editable prompts rather than installed defaults.
        initial = self._load_candidate(source, self.active_commit)
        self._validate_candidate(initial)
        self._active = self._confirmed = initial

    async def resume(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
        *,
        phase: TaskPhase = TaskPhase.TASK,
    ) -> None:
        """Resume the selected runtime with the fixed review opportunity."""
        prompt = f"{instruction}\n\n{RESUME_ITERATION_GUIDANCE}"
        if phase is TaskPhase.TASK:
            prompt = f"{prompt}\n\n{RESUME_REVIEW_REMINDER}"
        await self.run_active_runtime(
            prompt,
            environment,
            context,
            phase=phase,
        )

    async def run_active_runtime(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
        *,
        phase: TaskPhase = TaskPhase.TASK,
    ) -> RuntimeTrap | None:
        """Run selected runtimes and handle each synchronous lifecycle trap."""
        prompt = instruction
        while True:
            runtime = self.active_runtime
            segment = AgentContext()
            trap: RuntimeTrap | None = None
            runtime_fault: Exception | None = None
            try:
                await runtime.ensure_agent_session()
                runtime.configure_target_phase(
                    boxbox_enabled=phase is TaskPhase.TASK,
                )
                trap = await runtime.run_until_trap(
                    prompt,
                    environment,
                    segment,
                )
                if trap is not None and trap not in RuntimeTrap:
                    raise RuntimeError(f"Unsupported runtime trap: {trap!r}")
            except Exception as error:
                if phase is not TaskPhase.TASK:
                    raise
                runtime_fault = error
            finally:
                self._merge_context(context, segment)
            if runtime_fault is not None:
                fault_active_commit = self.active_commit
                rolled_back_provisional = False
                if self.has_provisional_runtime:
                    runtime, fault_active_commit = await self._rollback_provisional_runtime(
                        environment
                    )
                    rolled_back_provisional = True
                transition = await self.transition(
                    runtime,
                    environment,
                    runtime_fault=runtime_fault,
                    fault_active_commit=fault_active_commit,
                )
                self._merge_context(context, transition.context)
                if rolled_back_provisional:
                    recovery = (
                        "The provisional runtime faulted and was rolled back to the "
                        "confirmed runtime with a fresh terminal shell. Workspace and "
                        "Git state remain, but shell-local state and interrupted command "
                        "completion are ambiguous. Inspect the workspace, canonical "
                        "trajectory, and fault evidence before continuing."
                    )
                else:
                    recovery = (
                        "The previous runtime phase ended with a fault. Inspect the "
                        "preserved target state before repeating any interrupted work."
                    )
                prompt = f"{transition.prompt}\n\n{recovery}"
                continue
            if trap is None or trap == RuntimeTrap.COMPLETE:
                return trap
            if phase is not TaskPhase.TASK:
                raise RuntimeError("Runtime requested self-review while review is disabled")
            if trap == RuntimeTrap.BOXBOX and self.has_provisional_runtime:
                self._confirm_active_runtime()
            transition = await self.transition(runtime, environment)
            self._merge_context(context, transition.context)
            prompt = transition.prompt

    async def transition(
        self,
        runtime: Runtime,
        environment: BaseEnvironment,
        *,
        runtime_fault: Exception | None = None,
        fault_active_commit: str | None = None,
    ) -> Transition:
        """Run one review, validate its candidate, and deploy or retain."""
        if self._active is not runtime:
            raise RuntimeError("Only the active TerminusBoxBox may request a transition")
        if self._confirmed is not runtime:
            raise RuntimeError("Only the confirmed TerminusBoxBox may start a review transition")
        if self._transitioning:
            raise RuntimeError("A TerminusBoxBox transition is already in flight")
        self._transitioning = True
        self._sequence += 1
        sequence = self._sequence
        transition_dir = self._logs / "transitions" / f"{sequence:04d}"
        transition_dir.mkdir(parents=True, exist_ok=True)
        context = AgentContext()
        previous_commit = self.active_commit
        candidate_commit: str | None = None
        candidate: Runtime | None = None
        exported: RuntimeState | None = None
        review_result: ReviewResult | None = None
        outcome = "retained"
        fault_event_ids: list[str] = []
        trigger = "runtime_fault" if runtime_fault is not None else RuntimeTrap.BOXBOX.value
        stage = "fault_evidence" if runtime_fault is not None else "review"
        rollback_error: Exception | None = None
        prompt = "The TerminusBoxBox review retained the current runtime. Continue the target session."
        try:
            if runtime_fault is not None:
                event_id = await self._append_fault(
                    environment,
                    transition_dir,
                    source="runtime",
                    stage="runtime_execution",
                    candidate_commit=None,
                    error=runtime_fault,
                    include_traceback=True,
                    active_commit=fault_active_commit,
                )
                fault_event_ids.append(event_id)
                stage = "review"
            fault_report = self._new_fault_report()
            review_result = await asyncio.wait_for(
                runtime.review(
                    environment,
                    context,
                    sequence=sequence,
                    reviewer=self._create_reviewer(runtime, transition_dir),
                    fault_report=fault_report,
                ),
                timeout=TRANSITION_TIMEOUT,
            )
            if not isinstance(review_result, ReviewResult):
                raise TypeError("Runtime review must return ReviewResult")
            if fault_report is not None:
                self._last_reviewed_fault_at = fault_report.latest_event_at
            stage = "candidate_inspection"
            candidate_commit = await self._read_candidate_commit(environment)
            if candidate_commit == previous_commit:
                stage = "state_export"
                exported = runtime.export_state()
                prompt = runtime.prepare_continuation()
            else:
                stage = "load"
                source = await self._download_candidate(
                    environment,
                    candidate_commit,
                    transition_dir,
                )
                candidate = self._load_candidate(source, candidate_commit)

                stage = "contract_validation"
                self._validate_candidate(candidate)

                stage = "state_export"
                exported = runtime.export_state()

                stage = "state_import"
                candidate_state = copy.deepcopy(exported)
                candidate.import_state(candidate_state)

                stage = "activation"
                prompt = self._activate_runtime(
                    runtime,
                    candidate,
                    context_through_sequence=review_result.context_through_sequence,
                    context_through_offset=review_result.context_through_offset,
                )
                self._active = candidate
                self._active_commit = candidate_commit
                outcome = "provisional"
        except Exception as error:
            failure_stage = stage
            if failure_stage == "fault_evidence":
                raise RuntimeError("Failed to append runtime fault") from error
            outcome = "rolled-back" if stage in {"state_import", "activation"} else "retained"
            try:
                await self._restore_runtime_repo(environment, self.active_commit)
                if exported is not None:
                    runtime.import_state(exported)
                prompt = runtime.prepare_continuation()
            except Exception as caught:
                rollback_error = caught
                outcome = "rollback-failed"
            if failure_stage != "fault_evidence":
                try:
                    fault_event_ids.append(
                        await self._append_fault(
                            environment,
                            transition_dir,
                            source="kernel",
                            stage=failure_stage,
                            candidate_commit=candidate_commit,
                            error=error,
                            include_traceback=False,
                        )
                    )
                except Exception as persistence_error:
                    raise RuntimeError("Failed to append Kernel fault") from persistence_error
            if rollback_error is not None:
                fault_event_ids.append(
                    await self._append_fault(
                        environment,
                        transition_dir,
                        source="kernel",
                        stage="rollback",
                        candidate_commit=candidate_commit,
                        error=rollback_error,
                        include_traceback=False,
                    )
                )
        finally:
            self._transitioning = False
            self._write_transition(
                transition_dir,
                sequence=sequence,
                previous_commit=previous_commit,
                candidate_commit=candidate_commit,
                selected_commit=self.active_commit,
                context=context,
                outcome=outcome,
                trigger=trigger,
                fault_event_ids=fault_event_ids,
                context_through_sequence=(
                    review_result.context_through_sequence if review_result is not None else None
                ),
                context_through_offset=(
                    review_result.context_through_offset if review_result is not None else None
                ),
                accepted_context_boundary=outcome == "provisional",
            )
        if rollback_error is not None:
            raise RuntimeError("TerminusBoxBox transition and rollback both failed") from rollback_error
        return Transition(
            context=context,
            prompt=prompt,
        )

    @staticmethod
    def _restore_session(
        previous: Runtime,
        candidate: Runtime,
        session: Any,
    ) -> None:
        """Return a transferred session to the previous runtime through the contract."""
        released = candidate.release_session()
        if released is not session:
            raise RuntimeError("Candidate released a different target session")
        previous.attach_session(session)

    async def _rollback_provisional_runtime(
        self,
        environment: BaseEnvironment,
    ) -> tuple[Runtime, str]:
        """Restore the confirmed runtime after the provisional runtime faults."""
        if not self.has_provisional_runtime:
            raise RuntimeError("No provisional runtime is available to roll back")
        failed_runtime = self._active
        failed_commit = self.active_commit
        confirmed = self.confirmed_runtime
        confirmed_commit = self.confirmed_commit

        await self._restore_runtime_repo(environment, confirmed_commit)
        session = failed_runtime.release_session()
        fresh_session = await confirmed.restart_session(session)
        if fresh_session is not session:
            raise RuntimeError("Confirmed runtime restarted a different target session")
        attached_session = confirmed.attach_session(fresh_session)
        if attached_session is not session:
            raise RuntimeError("Confirmed runtime attached a different target session")

        self._active = confirmed
        self._active_commit = confirmed_commit
        confirmed.reconcile_review_trajectory()
        return confirmed, failed_commit

    def _activate_runtime(
        self,
        previous: Runtime,
        candidate: Runtime,
        *,
        context_through_sequence: int,
        context_through_offset: int,
    ) -> str:
        """Attach, validate, and prepare a candidate before changing active identity."""
        session = previous.release_session()
        attached = False
        try:
            attached_session = candidate.attach_session(session)
            attached = True
            if attached_session is not session:
                raise ValueError("Candidate attached a different target session")
            candidate.mark_harness_context_accepted(
                context_through_sequence,
                context_through_offset,
            )
            return candidate.prepare_continuation()
        except Exception:
            if attached:
                self._restore_session(previous, candidate, session)
            else:
                try:
                    released = candidate.release_session()
                except Exception:
                    released = session
                if released is not session:
                    raise RuntimeError("Candidate released a different target session")
                previous.attach_session(session)
            raise

    async def _read_candidate_commit(self, environment: BaseEnvironment) -> str:
        """Return the clean committed HEAD selected by review."""
        inspection = await environment.exec(
            """\
set -eu
candidate_commit=$(git rev-parse HEAD^{commit})
candidate_tree=$(git rev-parse "$candidate_commit^{tree}")
snapshot_index=$(mktemp /tmp/runtime-runtime-index.XXXXXX)
rm -f "$snapshot_index"
trap 'rm -f "$snapshot_index" "$snapshot_index.lock"' EXIT
GIT_INDEX_FILE="$snapshot_index" git read-tree "$candidate_commit"
GIT_INDEX_FILE="$snapshot_index" git add -A
test "$(GIT_INDEX_FILE="$snapshot_index" git write-tree)" = "$candidate_tree"
printf '%s\n' "$candidate_commit"
""",
            cwd=HARNESS_DIR,
            timeout_sec=30,
            user=REVIEW_USER,
        )
        if inspection.return_code != 0:
            raise RuntimeError(
                inspection.stdout
                or inspection.stderr
                or "review did not leave a clean committed runtime HEAD"
            )
        commit = inspection.stdout.strip().splitlines()[-1]
        self._validate_sha(commit, "Candidate runtime commit")
        return commit

    async def _download_candidate(
        self,
        environment: BaseEnvironment,
        commit: str,
        transition_dir: Path,
    ) -> Path:
        """Download a repository and materialize only the validated commit bytes."""
        repository = transition_dir / "candidate-repository"
        if repository.exists():
            shutil.rmtree(repository)
        bundle = transition_dir / "candidate.bundle"
        bundle.unlink(missing_ok=True)
        remote_bundle = "/tmp/runtime-candidate.bundle"
        bundled = await environment.exec(
            (
                f"rm -f {shlex.quote(remote_bundle)} && "
                f"git bundle create {shlex.quote(remote_bundle)} HEAD"
            ),
            cwd=HARNESS_DIR,
            timeout_sec=30,
            user=REVIEW_USER,
        )
        if bundled.return_code != 0:
            raise RuntimeError(
                bundled.stdout or bundled.stderr or "failed to bundle candidate runtime"
            )
        await environment.download_file(
            source_path=remote_bundle,
            target_path=bundle,
        )
        cloned = subprocess.run(
            ["git", "clone", "--quiet", str(bundle), str(repository)],
            capture_output=True,
            text=True,
            check=False,
        )
        if cloned.returncode != 0:
            raise ValueError(
                cloned.stderr.strip()
                or cloned.stdout.strip()
                or "failed to clone candidate runtime bundle"
            )
        if self._git_text(repository, "rev-parse", "HEAD^{commit}") != commit:
            raise ValueError("Downloaded runtime does not match the clean candidate commit")
        candidate_tree = self._git_text(repository, "rev-parse", f"{commit}^{{tree}}")
        descriptor, index_name = tempfile.mkstemp(prefix="runtime-runtime-index-")
        os.close(descriptor)
        Path(index_name).unlink()
        index_environment = {**os.environ, "GIT_INDEX_FILE": index_name}
        try:
            self._git_text(repository, "read-tree", commit, env=index_environment)
            self._git_text(repository, "add", "-A", env=index_environment)
            downloaded_tree = self._git_text(repository, "write-tree", env=index_environment)
        finally:
            Path(index_name).unlink(missing_ok=True)
            Path(f"{index_name}.lock").unlink(missing_ok=True)
        if downloaded_tree != candidate_tree:
            raise ValueError("Downloaded runtime worktree differs from the candidate commit")
        return self._materialize_commit(
            repository,
            commit,
            transition_dir / "candidate",
        )

    @staticmethod
    def _git_text(
        repository: Path,
        *arguments: str,
        env: dict[str, str] | None = None,
    ) -> str:
        """Run one local Git command and return stripped text output."""
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            raise ValueError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"Git command failed: {' '.join(arguments)}"
            )
        return result.stdout.strip()

    @classmethod
    def _materialize_commit(
        cls,
        repository: Path,
        commit: str,
        destination: Path,
    ) -> Path:
        """Write regular files directly from one Git tree without checkout filters."""
        resolved = cls._git_text(repository, "rev-parse", f"{commit}^{{commit}}")
        if resolved != commit:
            raise ValueError("Runtime repository does not contain the requested commit")
        listing = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "ls-tree",
                "-rz",
                "--full-tree",
                commit,
            ],
            capture_output=True,
            check=False,
        )
        if listing.returncode != 0:
            raise ValueError(
                listing.stderr.decode(errors="replace").strip()
                or "failed to inspect committed TerminusBoxBox tree"
            )
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        for record in listing.stdout.split(b"\0"):
            if not record:
                continue
            metadata, separator, raw_path = record.partition(b"\t")
            if not separator:
                raise ValueError("Malformed Git tree entry in candidate commit")
            mode, kind, object_id = metadata.decode("ascii").split()
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("Candidate runtime may contain only regular committed files")
            try:
                relative = PurePosixPath(raw_path.decode("utf-8"))
            except UnicodeDecodeError as error:
                raise ValueError("Candidate runtime contains a non-UTF-8 path") from error
            if (
                relative.is_absolute()
                or not relative.parts
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise ValueError("Candidate runtime contains an unsafe path")
            # Operational state and bytecode are not part of executable harness source,
            # even when a review deliberately commits its feedback under .runtime/.
            if (
                relative.parts[0] == RUNTIME_STATE_NAME
                or any(part in {".git", "__pycache__"} for part in relative.parts)
                or relative.suffix == ".pyc"
            ):
                continue
            blob = subprocess.run(
                ["git", "-C", str(repository), "cat-file", "blob", object_id],
                capture_output=True,
                check=False,
            )
            if blob.returncode != 0:
                raise ValueError(
                    blob.stderr.decode(errors="replace").strip()
                    or f"failed to read committed object {object_id}"
                )
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.stdout)
            target.chmod(0o755 if mode == "100755" else 0o644)
        if not (destination / "__init__.py").is_file():
            raise ValueError("Candidate commit does not contain the TerminusBoxBox package")
        return destination

    def _load_candidate(self, source: Path, commit: str) -> Runtime:
        """Load a commit-addressed TerminusBoxBox class beside the active runtime."""
        package = source
        init = package / "__init__.py"
        # Identical revisions in different trials still own independent files
        # and module state. Do not reuse Python's submodule cache across copies.
        module_name = f"_terminus_boxbox_runtime_{commit}_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            init,
            submodule_search_locations=[str(package)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load TerminusBoxBox package from {init}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            for name in list(sys.modules):
                if name == module_name or name.startswith(module_name + "."):
                    sys.modules.pop(name, None)
            raise
        runtime_class = getattr(module, "TerminusBoxBox", None)
        if not isinstance(runtime_class, type):
            raise TypeError("Runtime package must export a TerminusBoxBox class")
        return self._create_runtime(runtime_class)

    def _create_reviewer(self, runtime: Runtime, transition_dir: Path) -> Runtime:
        """Create a reviewer from the active runtime class."""
        return self._create_runtime(type(runtime), logs_dir=transition_dir / "review")

    def _create_runtime(
        self,
        runtime_class: type[Runtime],
        *,
        logs_dir: Path | None = None,
    ) -> Runtime:
        """Create a runtime already attached to this Kernel."""
        constructor = dict(self._constructor)
        if logs_dir is not None:
            constructor["logs_dir"] = logs_dir
        return runtime_class(**constructor)

    def _validate_candidate(self, candidate: Runtime) -> None:
        """Validate the runtime interface required by Kernel."""
        if not isinstance(candidate, Runtime):
            raise TypeError("Candidate does not implement the TerminusBoxBox runtime Protocol")

    async def _restore_runtime_repo(
        self,
        environment: BaseEnvironment,
        commit: str,
    ) -> None:
        """Restore the review worktree to one loaded runtime commit."""
        self._validate_sha(commit, "Restored runtime commit")
        result = await environment.exec(
            (
                "git reset --hard HEAD && "
                "git clean -fd && "
                f"git checkout --detach {shlex.quote(commit)}"
            ),
            cwd=HARNESS_DIR,
            timeout_sec=60,
            user=REVIEW_USER,
        )
        if result.return_code != 0:
            raise RuntimeError(
                result.stdout or result.stderr or "failed to restore the runtime repository"
            )

    async def _append_fault(
        self,
        environment: BaseEnvironment,
        transition_dir: Path,
        *,
        source: str,
        stage: str,
        candidate_commit: str | None,
        error: Exception,
        include_traceback: bool,
        active_commit: str | None = None,
    ) -> str:
        """Append one runtime or Kernel failure to the persistent fault journal."""
        event = {
            "schema_version": 1,
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "transition_sequence": self._sequence,
            "source": source,
            "stage": stage,
            "active_commit": active_commit or self.active_commit,
            "candidate_commit": candidate_commit,
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": (
                    "".join(traceback.format_exception(type(error), error, error.__traceback__))
                    if include_traceback
                    else None
                ),
            },
        }
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
        journal = self._logs / "faults.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(f"{line}\n")
        upload = transition_dir / f".fault-{event['event_id']}.jsonl"
        upload.write_text(f"{line}\n", encoding="utf-8")
        remote = f"{RUNTIME_STATE_DIR}/.{event['event_id']}.jsonl"
        try:
            await prepare_runtime_state_dir(environment)
            await environment.upload_file(upload, remote)
            ownership = await environment.exec(
                (
                    f"cat {shlex.quote(remote)} >> {shlex.quote(FAULT_LOG)} && "
                    f"rm -f {shlex.quote(remote)} && "
                    f"chown {REVIEW_USER}:{REVIEW_USER} {shlex.quote(FAULT_LOG)}"
                ),
                cwd=HARNESS_DIR,
                timeout_sec=30,
                user="root",
            )
            if ownership.return_code != 0:
                raise RuntimeError(
                    ownership.stdout
                    or ownership.stderr
                    or "failed to append the persistent fault journal"
                )
        finally:
            upload.unlink(missing_ok=True)
        return event["event_id"]

    def _latest_fault_event_at(self) -> str | None:
        """Return the timestamp of the newest host fault-journal event."""
        journal = self._logs / "faults.jsonl"
        if not journal.is_file():
            return None
        latest = ""
        with journal.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    latest = line
        if not latest:
            return None
        try:
            event = json.loads(latest)
        except json.JSONDecodeError as error:
            raise ValueError("Fault journal ends with invalid JSON") from error
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError("Latest fault event has no timestamp")
        return timestamp

    def _new_fault_report(self) -> FaultReport | None:
        """Describe fault evidence newer than the last successful review."""
        latest_event_at = self._latest_fault_event_at()
        if latest_event_at is None:
            return None
        if (
            self._last_reviewed_fault_at is not None
            and latest_event_at <= self._last_reviewed_fault_at
        ):
            return None
        return FaultReport(
            last_reviewed_at=self._last_reviewed_fault_at,
            latest_event_at=latest_event_at,
        )

    def _write_transition(
        self,
        transition_dir: Path,
        *,
        sequence: int,
        previous_commit: str,
        candidate_commit: str | None,
        selected_commit: str,
        context: AgentContext,
        outcome: str,
        trigger: str,
        fault_event_ids: list[str],
        context_through_sequence: int | None,
        context_through_offset: int | None,
        accepted_context_boundary: bool,
    ) -> None:
        """Write the canonical machine-readable transition summary."""
        payload = {
            "schema_version": 1,
            "transition": {
                "sequence": sequence,
            },
            "lineage": {
                "previous_commit": previous_commit,
                "candidate_commit": candidate_commit,
                "selected_commit": selected_commit,
            },
            "usage": {
                "input_tokens": context.n_input_tokens or 0,
                "output_tokens": context.n_output_tokens or 0,
                "cache_tokens": context.n_cache_tokens or 0,
                "cost_usd": context.cost_usd or 0.0,
                "requests": len(context.rollout_details or []),
            },
            "outcome": outcome,
            "trigger": trigger,
            "runtime_selection": {
                "confirmed_commit": self.confirmed_commit,
                "active_commit": self.active_commit,
                "provisional": self.has_provisional_runtime,
            },
            "context_boundary": {
                "through_sequence": context_through_sequence,
                "through_offset": context_through_offset,
                "accepted": accepted_context_boundary,
            },
            "fault_event_ids": fault_event_ids,
        }
        (transition_dir / "transition.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _validate_sha(value: str, label: str) -> None:
        """Require one full lowercase Git object ID."""
        if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{label} must be a full lowercase Git SHA")
