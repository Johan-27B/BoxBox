"""Task-local Harness Scaling inside one Harbor checkpoint trial."""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import shlex
import time
from pathlib import Path
from typing import Any, Literal

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pydantic import BaseModel, ConfigDict, Field

from boxbox.terminus_boxbox import harness
from boxbox.terminus_boxbox.seed import materialize
from perfrace.evolution.evolver import EvolutionOutcome, run_evolver
from perfrace.evolution.meta import MetaAgentEndpoint, rotate_failed_output
from perfrace.evolution.runtime_repository import RuntimeRepository, RuntimeSnapshot
from perfrace.evolution.state import write_model_atomic, write_text_atomic
from perfrace.evolution.loader import validate_harness_source
from perfrace.run.types import Measurement


class HarnessScalingRound(BaseModel):
    """Durable record for one verified target attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    round: int = Field(ge=1)
    runtime_commit: str = Field(min_length=40, max_length=40)
    successor_commit: str | None = Field(default=None, min_length=40, max_length=40)
    measurement: Measurement
    started_at: float
    completed_at: float
    evolution_started_at: float | None = None
    evolution_completed_at: float | None = None
    transition_started_at: float | None = None
    transition_completed_at: float | None = None


class HarnessScalingSummary(BaseModel):
    """Campaign state persisted with one Harbor trial."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: int = 2
    task_id: str
    started_at: float
    completed_at: float | None = None
    stop_reason: Literal["running", "insufficient-time", "deadline", "failed"] = "running"
    rounds: tuple[HarnessScalingRound, ...] = ()


def _run_evolver_process(connection: Any, kwargs: dict[str, Any]) -> None:
    """Run NexAU outside the active CheckpointTrial event loop."""
    try:
        connection.send(("ok", run_evolver(**kwargs)))
    except BaseException as exc:
        connection.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


class HarnessScalingAgent(BaseAgent):
    """Evolve a task-specific harness between fresh agents on one workspace."""

    SUPPORTS_RESUME = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        harness_source = kwargs.pop(
            "harness_source",
            Path(harness.__file__).parent,
        )
        self._harness_revision = kwargs.pop("harness_revision", None)
        evolver_agent_config = kwargs.pop(
            "evolver_agent_config",
            Path(__file__).parents[1]
            / "evolution"
            / "agents"
            / "scaling_evolve_agent.yaml",
        )
        self._max_attempt_timeout_sec = kwargs.pop("max_attempt_timeout_sec", 1_500)
        self._minimum_stage_time_sec = kwargs.pop("minimum_stage_time_sec", 300)
        self._retry_invalid_evolution = kwargs.pop("retry_invalid_evolution", 1)
        self._reasoning_effort = kwargs.pop("reasoning_effort", "high")
        runtime_kwargs = dict(kwargs)
        super().__init__(*args, **kwargs)
        if not self.model_name:
            raise ValueError("HarnessScalingAgent requires model_name")
        if not isinstance(harness_source, (str, Path)):
            raise ValueError("harness_source must be a path")
        if not isinstance(evolver_agent_config, (str, Path)):
            raise ValueError("evolver_agent_config must be a path")
        if type(self._max_attempt_timeout_sec) is not int or self._max_attempt_timeout_sec <= 300:
            raise ValueError("max_attempt_timeout_sec must be an integer above 300")
        if type(self._minimum_stage_time_sec) is not int or self._minimum_stage_time_sec < 1:
            raise ValueError("minimum_stage_time_sec must be a positive integer")
        if type(self._retry_invalid_evolution) is not int or self._retry_invalid_evolution not in {
            0,
            1,
        }:
            raise ValueError("retry_invalid_evolution must be zero or one")
        if self._reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise ValueError("reasoning_effort must be low, medium, high, or xhigh")

        self._harness_source = Path(harness_source).expanduser().resolve()
        self._evolver_agent_config = Path(evolver_agent_config).expanduser().resolve()
        model_name = self.model_name if "/" in self.model_name else f"openai/{self.model_name}"
        api_base = self._extra_env.get("LLM_BASE_URL")
        if api_base:
            api_base = api_base.replace("://host.docker.internal:", "://127.0.0.1:")
        llm_kwargs = dict(runtime_kwargs.pop("llm_kwargs", {}) or {})
        for base_key in (
            "logs_dir",
            "model_name",
            "logger",
            "mcp_servers",
            "skills_dir",
            "extra_env",
        ):
            runtime_kwargs.pop(base_key, None)
        api_key = self._extra_env.get("LLM_API_KEY")
        if api_key:
            llm_kwargs.setdefault("api_key", api_key)
        self._runtime_constructor_kwargs = {
            **runtime_kwargs,
            "model_name": model_name,
            "api_base": api_base,
            "llm_kwargs": llm_kwargs,
            "extra_env": {
                **self._extra_env,
                "GIT_PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
                "PAGER": "cat",
                "SYSTEMD_PAGER": "cat",
            },
            "record_terminal_session": False,
            "use_responses_api": True,
            "reasoning_effort": self._reasoning_effort,
            "completion_name": "submit",
            "completion_description": "Call this to request official verification of the current candidate.",
        }
        self._api_base = api_base
        self._api_key = api_key
        self._campaign_root = self.logs_dir / "harness-scaling"
        self._repository: RuntimeRepository | None = None
        self._runtime: Any | None = None
        self._active_snapshot: RuntimeSnapshot | None = None
        self._last_verified_snapshot: RuntimeSnapshot | None = None
        self._pending_runtime_rollback: RuntimeSnapshot | None = None
        self._round_fault: str | None = None
        self._target_base_commits: dict[str, str] = {}
        self._target_git_dirs: dict[str, str] = {}
        self._rounds: list[HarnessScalingRound] = []
        self._round_number = 1
        self._round_started_at = 0.0
        self._campaign_started_at = 0.0
        self._remaining_sec = 0.0
        self._measurement_overhead_sec = 0.0
        self._task_instruction: str | None = None
        self._round_context: dict[str, Any] | None = None
        self._skip_to_final_checkpoint = False
        self._final_delivery = False

    @staticmethod
    def name() -> str:
        """Return the Harbor agent name."""
        return "harness-scaling"

    def version(self) -> str | None:
        """Return the active wrapper version."""
        return "2.0.0"

    def set_checkpoint_budget(self, *, total_sec: float, remaining_sec: float) -> None:
        """Observe the shared CheckpointTrial budget before one agent phase."""
        if total_sec <= self._minimum_stage_time_sec:
            raise ValueError("Harness Scaling requires a usable shared campaign budget")
        if remaining_sec < 0 or remaining_sec > total_sec:
            raise ValueError("CheckpointTrial reported an invalid remaining budget")
        self._remaining_sec = max(0.0, remaining_sec - self._measurement_overhead_sec)
        if self._campaign_root.exists():
            write_text_atomic(
                self._campaign_root / "budget.json",
                json.dumps(
                    {
                        "total_sec": total_sec,
                        "checkpoint_trial_remaining_sec": remaining_sec,
                        "measurement_overhead_sec": self._measurement_overhead_sec,
                        "effective_remaining_sec": self._remaining_sec,
                    },
                    indent=2,
                )
                + "\n",
            )

    def checkpoint_trial_skip_to_final_checkpoint(self) -> bool:
        """Skip verification for a bookkeeping phase and start final delivery."""
        return self._skip_to_final_checkpoint

    async def checkpoint_fingerprint(self, environment: BaseEnvironment) -> None:
        """Disable reuse because every target attempt requires formal verification."""
        del environment
        return None

    async def setup(self, environment: BaseEnvironment) -> None:
        """Snapshot the shared H0 and record the container's initial project state."""
        workdir = environment.task_env_config.workdir
        if not workdir:
            raise ValueError("HarnessScalingAgent requires a workdir")
        if not self._api_base or not self._api_key:
            raise ValueError("HarnessScalingAgent requires LLM_BASE_URL and LLM_API_KEY")
        self._campaign_root.mkdir(parents=True, exist_ok=True)
        self._target_base_commits = await self._initialize_target_repositories(
            environment,
            workdir=workdir,
        )
        repository_path = self._campaign_root / "runtime" / "repository"
        source = materialize(
            self._harness_source,
            self.logs_dir / "initial-harness",
            revision=self._harness_revision,
        )
        self._repository = RuntimeRepository.initialize(source, repository_path)
        self._active_snapshot = self._repository.validate_head()
        self._runtime = self._load_runtime(self._active_snapshot)
        await self._setup_runtime(environment)
        self._campaign_started_at = time.time()
        self._write_state(stop_reason="running")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run the first target attempt with harness H0."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._task_instruction = instruction
        try:
            await self._start_round(environment, context)
        except BaseException:
            self._write_state(stop_reason="failed", completed_at=time.time())
            raise

    async def resume(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Evolve the harness and restart the target agent on the current workspace."""
        del instruction
        try:
            await self._resume_after_measurement(environment, context)
        except TimeoutError:
            self._skip_to_final_checkpoint = True
            self._write_state(stop_reason="insufficient-time", completed_at=time.time())
        except BaseException:
            self._write_state(stop_reason="failed", completed_at=time.time())
            raise

    async def _resume_after_measurement(
        self,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Evolve once, then run a fresh target agent on the retained workspace."""
        if not self._rounds:
            raise RuntimeError("Harness Scaling cannot resume before a verified round")
        if self._remaining_sec < self._minimum_stage_time_sec:
            self._skip_to_final_checkpoint = True
            self._write_state(stop_reason="insufficient-time", completed_at=time.time())
            return

        if self._pending_runtime_rollback is not None:
            transition_started_at = time.time()
            transition_started = time.monotonic()
            rollback = self._pending_runtime_rollback
            previous = self._rounds[-1]
            failed_runtime = self._active_snapshot
            self._rounds[-1] = previous.model_copy(
                update={
                    "successor_commit": rollback.commit,
                    "transition_started_at": transition_started_at,
                }
            )
            self._round_number = previous.round + 1
            await self._replace_runtime(rollback, environment)
            transition_completed_at = time.time()
            self._rounds[-1] = self._rounds[-1].model_copy(
                update={"transition_completed_at": transition_completed_at}
            )
            write_text_atomic(
                self._campaign_root / "rounds" / f"{previous.round:04d}" / "runtime-rollback.json",
                json.dumps(
                    {
                        "failed_runtime": (
                            failed_runtime.commit if failed_runtime is not None else None
                        ),
                        "rollback_runtime": rollback.commit,
                        "fault": self._round_fault,
                    },
                    indent=2,
                )
                + "\n",
            )
            self._pending_runtime_rollback = None
            self._round_fault = None
            self._remaining_sec = max(
                0.0,
                self._remaining_sec - (time.monotonic() - transition_started),
            )
            self._write_state(stop_reason="running")
            await self._start_round(environment, context)
            return

        evolution_started_at = time.time()
        evolution_started = time.monotonic()
        try:
            outcome = await self._evolve(environment)
            successor = outcome.snapshot
        except TimeoutError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            if self._active_snapshot is None:
                raise RuntimeError("Harness Scaling has no runtime to retain") from exc
            successor = self._active_snapshot
            round_dir = self._campaign_root / "rounds" / f"{self._rounds[-1].round:04d}"
            write_text_atomic(
                round_dir / "evolution-failure.json",
                json.dumps(
                    {
                        "runtime_commit": successor.commit,
                        "failure": f"{type(exc).__name__}: {exc}",
                        "outcome": "retained",
                    },
                    indent=2,
                )
                + "\n",
            )
        evolution_elapsed = time.monotonic() - evolution_started
        evolution_completed_at = time.time()
        self._remaining_sec = max(0.0, self._remaining_sec - evolution_elapsed)
        previous = self._rounds[-1]
        self._rounds[-1] = previous.model_copy(
            update={
                "evolution_started_at": evolution_started_at,
                "evolution_completed_at": evolution_completed_at,
            }
        )
        if self._remaining_sec < self._minimum_stage_time_sec:
            self._skip_to_final_checkpoint = True
            self._write_state(stop_reason="insufficient-time", completed_at=time.time())
            return

        transition_started_at = time.time()
        transition_started = time.monotonic()
        self._round_number = previous.round + 1
        activated = await self._activate_runtime_revision(
            successor,
            fallback=self._last_verified_snapshot or self._active_snapshot,
            environment=environment,
            previous_round=previous.round,
        )
        transition_completed_at = time.time()
        self._rounds[-1] = self._rounds[-1].model_copy(
            update={
                "successor_commit": activated.commit,
                "transition_started_at": transition_started_at,
                "transition_completed_at": transition_completed_at,
            }
        )
        self._remaining_sec = max(
            0.0,
            self._remaining_sec - (time.monotonic() - transition_started),
        )
        self._write_state(stop_reason="running")
        await self._start_round(environment, context)

    async def _activate_runtime_revision(
        self,
        snapshot: RuntimeSnapshot,
        *,
        fallback: RuntimeSnapshot | None,
        environment: BaseEnvironment,
        previous_round: int,
    ) -> RuntimeSnapshot:
        """Activate one revision, falling back before target execution if it is invalid."""
        try:
            await self._replace_runtime(snapshot, environment)
            return snapshot
        except Exception as exc:
            if fallback is None or fallback.commit == snapshot.commit:
                raise
            round_dir = self._campaign_root / "rounds" / f"{previous_round:04d}"
            write_text_atomic(
                round_dir / "runtime-activation-failure.json",
                json.dumps(
                    {
                        "failed_runtime": snapshot.commit,
                        "rollback_runtime": fallback.commit,
                        "failure": f"{type(exc).__name__}: {exc}",
                    },
                    indent=2,
                )
                + "\n",
            )
            await self._replace_runtime(fallback, environment)
            return fallback

    async def _stop_runtime_session(self, environment: BaseEnvironment) -> None:
        """Stop the completed target attempt before starting a fresh session."""
        session = getattr(self._runtime, "_session", None)
        if session is None:
            return
        await session.stop()
        if not await session.is_session_alive():
            return
        session_name = getattr(session, "_session_name", None)
        if not isinstance(session_name, str) or not session_name:
            raise RuntimeError("Harness Scaling runtime session has no valid tmux name")
        result = await environment.exec(
            command=f"tmux kill-session -t {shlex.quote(session_name)}",
            user=environment.default_user,
        )
        if result.return_code not in (0, 1):
            raise RuntimeError(
                "Failed to kill stale Harness Scaling tmux session: "
                f"{result.stderr or result.stdout}"
            )
        for _ in range(20):
            if not await session.is_session_alive():
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"Harness Scaling tmux session {session_name!r} did not stop")

    async def _setup_runtime(self, environment: BaseEnvironment) -> None:
        """Start a fresh runtime session, retrying one tmux cleanup race."""
        if self._runtime is None:
            raise RuntimeError("Harness Scaling runtime is not initialized")
        for attempt in range(2):
            try:
                await self._runtime.setup(environment)
                return
            except RuntimeError as exc:
                if attempt or "Failed to start tmux session" not in str(exc):
                    raise
                await self._stop_runtime_session(environment)
                await asyncio.sleep(1)
        raise AssertionError("unreachable")

    def _complete_pending_tool_calls(self) -> int:
        """Close interrupted tool calls in live and serialized final-round Chat state."""
        if self._runtime is None:
            raise RuntimeError("Harness Scaling runtime is not initialized")

        repaired: set[str] = set()

        def complete(messages: Any) -> set[str]:
            if not isinstance(messages, list):
                return set()
            pending: dict[str, str] = {}
            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("role") == "assistant":
                    for tool_call in message.get("tool_calls") or []:
                        call_id = tool_call.get("id")
                        function = tool_call.get("function") or {}
                        if call_id:
                            pending[str(call_id)] = str(function.get("name") or "tool")
                elif message.get("role") == "tool":
                    pending.pop(str(message.get("tool_call_id") or ""), None)
            for call_id, name in pending.items():
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": (
                            f"{name} was interrupted when the previous Harness Scaling "
                            "target phase ended. Continue final delivery from the current "
                            "workspace and inspect its state before assuming the tool "
                            "completed."
                        ),
                    }
                )
            return set(pending)

        state = getattr(self._runtime, "_pending_chat_state", None)
        state_messages = state.get("messages") if isinstance(state, dict) else None
        repaired.update(complete(state_messages))

        chat = getattr(self._runtime, "_chat", None)
        messages = getattr(chat, "_messages", None)
        live_repaired = complete(messages) if messages is not state_messages else set()
        repaired.update(live_repaired)
        if live_repaired:
            chat.reset_response_chain()
        return len(repaired)

    async def finalize(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run normal final delivery on the active final-round workspace."""
        if self._runtime is None:
            raise RuntimeError("Harness Scaling runtime is not initialized")
        self._final_delivery = True
        repaired_tool_calls = self._complete_pending_tool_calls()
        try:
            await self._runtime.finalize(instruction, environment, context)
        finally:
            metadata = dict(context.metadata or {})
            metadata["harness_scaling"] = {
                "rounds": len(self._rounds),
                "runtime_commit": (
                    self._active_snapshot.commit if self._active_snapshot is not None else None
                ),
                "stop_reason": ("deadline" if self._remaining_sec <= 0 else "insufficient-time"),
                "repaired_pending_tool_calls": repaired_tool_calls,
            }
            context.metadata = metadata
            self._write_state(
                stop_reason="deadline" if self._remaining_sec <= 0 else "insufficient-time",
                completed_at=time.time(),
            )

    async def prepare_final_checkpoint(self, environment: BaseEnvironment) -> None:
        """Restore a verified runtime if needed, then mark the final Measurement."""
        if self._pending_runtime_rollback is not None:
            rollback = self._pending_runtime_rollback
            failed_runtime = self._active_snapshot
            previous_round = self._rounds[-1].round if self._rounds else 0
            self._round_number = previous_round + 1
            await self._replace_runtime(rollback, environment)
            write_text_atomic(
                self._campaign_root / "final-runtime-rollback.json",
                json.dumps(
                    {
                        "failed_runtime": (
                            failed_runtime.commit if failed_runtime is not None else None
                        ),
                        "rollback_runtime": rollback.commit,
                        "fault": self._round_fault,
                    },
                    indent=2,
                )
                + "\n",
            )
            self._pending_runtime_rollback = None
            self._round_fault = None
        self._final_delivery = True
        self._write_state(
            stop_reason="deadline" if self._remaining_sec <= 0 else "insufficient-time",
            completed_at=time.time(),
        )

    async def record_measurement(
        self,
        measurement: Measurement,
        environment: BaseEnvironment,
    ) -> None:
        """Persist one checkpoint measurement and its runtime/workspace evidence."""
        if self._final_delivery:
            write_model_atomic(self._campaign_root / "final-measurement.json", measurement)
            self._write_state(
                stop_reason="deadline" if self._remaining_sec <= 0 else "insufficient-time",
                completed_at=time.time(),
            )
            return
        if self._active_snapshot is None:
            raise RuntimeError("Harness Scaling has no active runtime snapshot")

        overhead_started = time.monotonic()
        try:
            await self._persist_round_evidence(environment, measurement)
        finally:
            overhead_elapsed = time.monotonic() - overhead_started
            self._measurement_overhead_sec += overhead_elapsed
            self._remaining_sec = max(0.0, self._remaining_sec - overhead_elapsed)
        completed_at = time.time()
        round_dir = self._campaign_root / "rounds" / f"{self._round_number:04d}"
        write_model_atomic(round_dir / "measurement.json", measurement)
        record = HarnessScalingRound(
            round=self._round_number,
            runtime_commit=self._active_snapshot.commit,
            measurement=measurement,
            started_at=self._round_started_at,
            completed_at=completed_at,
        )
        self._rounds.append(record)
        if self._round_fault is None:
            self._last_verified_snapshot = self._active_snapshot
        self._write_state(stop_reason="running")

    async def _start_round(
        self,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run one fresh target context on the retained workspace."""
        if self._runtime is None or self._active_snapshot is None:
            raise RuntimeError("Harness Scaling runtime is not initialized")
        if self._task_instruction is None:
            raise RuntimeError("Harness Scaling task instruction is missing")
        if self._remaining_sec < self._minimum_stage_time_sec:
            self._skip_to_final_checkpoint = True
            self._write_state(stop_reason="insufficient-time", completed_at=time.time())
            return

        self._skip_to_final_checkpoint = False
        self._round_started_at = time.time()
        attempt_timeout = min(self._max_attempt_timeout_sec, self._remaining_sec)
        timed_out = False
        self._round_fault = None
        try:
            await asyncio.wait_for(
                self._runtime.run(
                    self._task_instruction,
                    environment,
                    context,
                ),
                timeout=attempt_timeout,
            )
        except TimeoutError:
            timed_out = True
        except BaseException as exc:
            self._round_fault = f"{type(exc).__name__}: {exc}"
            if self._last_verified_snapshot is not None:
                self._pending_runtime_rollback = self._last_verified_snapshot
            raise
        finally:
            metadata = dict(context.metadata or {})
            metadata["harness_scaling"] = {
                "round": self._round_number,
                "runtime_commit": self._active_snapshot.commit,
                "runtime_session_id": getattr(self._runtime, "session_id", None),
                "attempt_timeout_sec": attempt_timeout,
                "attempt_timed_out": timed_out,
                "runtime_fault": self._round_fault,
            }
            context.metadata = metadata
            self._round_context = context.model_dump(mode="json")

    async def _evolve(self, environment: BaseEnvironment) -> EvolutionOutcome:
        """Run and validate one dedicated harness-evolution step."""
        del environment
        if self._repository is None or self._active_snapshot is None or not self._rounds:
            raise RuntimeError("Harness Scaling cannot evolve before a verified round")
        remaining = self._remaining_sec - self._minimum_stage_time_sec
        if remaining <= 0:
            raise TimeoutError("No campaign budget remains after reserving the next stage")

        record = self._rounds[-1]
        round_dir = self._campaign_root / "rounds" / f"{record.round:04d}"
        analysis_dir = round_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        overview_path = analysis_dir / "overview.md"
        write_text_atomic(
            overview_path,
            "\n".join(
                (
                    f"# Harness Scaling round {record.round}",
                    "",
                    f"- Task: `{self._task_id()}`",
                    f"- Runtime: `{record.runtime_commit}`",
                    f"- Verdict: `{record.measurement.verdict}`",
                    f"- Metric: `{record.measurement.metric}`",
                    f"- Value: `{record.measurement.value}` `{record.measurement.unit}`",
                    "",
                    "The target workspace and its Git research state continue into the "
                    "next attempt. The next target runtime, Chat, context, tmux shell, "
                    "and process state restart from the original task instruction.",
                    "",
                    "Evidence:",
                    f"- Target context: `{round_dir / 'target' / 'context.json'}`",
                    f"- Terminal transcript: `{round_dir / 'target' / 'terminal.txt'}`",
                    f"- Workspace evidence: `{round_dir / 'target' / 'workspace'}`",
                )
            )
            + "\n",
        )
        endpoint = MetaAgentEndpoint(
            base_url=self._api_base or "",
            token_proxy_secret="",
            model=self.model_name or "",
            reasoning_effort=self._reasoning_effort,
            session_prefix=self.session_id or "harness-scaling",
            fixed_api_key=self._api_key,
        )
        evolve_kwargs = {
            "repository": self._repository,
            "experiment_root": self._campaign_root,
            "generation_dir": round_dir,
            "iteration": record.round,
            "parent_generation": record.round - 1,
            "parent_commit": record.runtime_commit,
            "overview_path": overview_path,
            "detail_dir": analysis_dir,
            "endpoint": endpoint,
            "agent_config": self._evolver_agent_config,
            "message": (
                f"Evolve the task-specific harness after round {record.round} "
                f"on {self._task_id()}."
            ),
            "history_title": "# Task-specific Harness Scaling history",
            "task_id": self._task_id(),
            "extra_read_roots": (round_dir / "target",),
        }
        deadline = time.monotonic() + remaining
        for retry in range(self._retry_invalid_evolution + 1):
            try:
                timeout_sec = deadline - time.monotonic()
                if timeout_sec <= 0:
                    raise TimeoutError("Harness evolution reached its campaign deadline")
                receive, send = multiprocessing.get_context("spawn").Pipe(duplex=False)
                process = multiprocessing.get_context("spawn").Process(
                    target=_run_evolver_process,
                    args=(send, evolve_kwargs),
                )
                process.start()
                send.close()
                try:
                    await asyncio.to_thread(process.join, timeout_sec)
                    if process.is_alive():
                        process.terminate()
                        await asyncio.to_thread(process.join, 10)
                        raise TimeoutError("Harness evolution reached its campaign deadline")
                    if not receive.poll():
                        raise RuntimeError(
                            f"Harness evolver exited without a result: {process.exitcode}"
                        )
                    status, payload = receive.recv()
                    if status != "ok":
                        raise RuntimeError(str(payload))
                    if not isinstance(payload, EvolutionOutcome):
                        raise RuntimeError("Harness evolver returned an invalid result")
                    return payload
                finally:
                    receive.close()
                    if process.is_alive():
                        process.terminate()
                        await asyncio.to_thread(process.join, 10)
            except TimeoutError:
                self._repository.restore(record.runtime_commit)
                evolve_dir = round_dir / "evolve"
                if evolve_dir.exists() and any(evolve_dir.iterdir()):
                    rotate_failed_output(evolve_dir)
                raise
            except (OSError, RuntimeError, ValueError):
                self._repository.restore(record.runtime_commit)
                evolve_dir = round_dir / "evolve"
                if evolve_dir.exists() and any(evolve_dir.iterdir()):
                    rotate_failed_output(evolve_dir)
                if retry >= self._retry_invalid_evolution:
                    raise
        raise AssertionError("unreachable")

    async def _replace_runtime(
        self,
        snapshot: RuntimeSnapshot,
        environment: BaseEnvironment,
    ) -> None:
        """Stop the completed target process and start a fresh runtime revision."""
        if self._runtime is None:
            raise RuntimeError("Harness Scaling runtime is not initialized")
        await self._stop_runtime_session(environment)
        self._runtime = self._load_runtime(snapshot)
        self._active_snapshot = snapshot
        await self._setup_runtime(environment)

    async def _initialize_target_repositories(
        self,
        environment: BaseEnvironment,
        *,
        workdir: str,
    ) -> dict[str, str]:
        """Create external Git baselines without modifying target workspaces."""
        available = await environment.exec(
            "git --version",
            user=environment.default_user,
            timeout_sec=30,
        )
        if available.return_code != 0:
            raise RuntimeError(
                available.stdout
                or available.stderr
                or "Harness Scaling requires Git in the task environment"
            )
        commits: dict[str, str] = {}
        # Harbor's workdir is the editable project root. The image may contain
        # all sources; no host-side workspace directory is required.
        candidates = [(".", workdir)]
        for index, (entry, path) in enumerate(candidates):
            safe_name = entry.replace("/", "_")
            git_dir = f"/var/lib/perfrace-harness-scaling/target-git/{index:02d}-{safe_name}.git"
            result = await environment.exec(
                (
                    "install -d -m 0700 /var/lib/perfrace-harness-scaling "
                    "/var/lib/perfrace-harness-scaling/target-git && "
                    f"test ! -e {shlex.quote(git_dir)} && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"init -q --bare {shlex.quote(git_dir)} && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} config core.bare false && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} config core.worktree "
                    f"{shlex.quote(path)} && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} config user.email "
                    "'harness-scaling@perfrace.local' && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} config user.name "
                    "'harness-scaling' && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} add -A && "
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} commit -q --allow-empty "
                    "-m 'perfrace: target baseline' && "
                    f"git --git-dir={shlex.quote(git_dir)} rev-parse HEAD"
                ),
                user="root",
                timeout_sec=300,
            )
            lines = (result.stdout or "").strip().splitlines()
            if result.return_code != 0 or not lines or len(lines[-1]) != 40:
                raise RuntimeError(
                    result.stdout
                    or result.stderr
                    or f"failed to initialize external target Git baseline: {path}"
                )
            commits[entry] = lines[-1]
            self._target_git_dirs[entry] = git_dir
        return commits

    async def _persist_round_evidence(
        self,
        environment: BaseEnvironment,
        measurement: Measurement,
    ) -> None:
        """Persist target trajectory, terminal output, and workspace changes."""
        if self._runtime is None:
            raise RuntimeError("Harness Scaling runtime is not initialized")
        workdir = environment.task_env_config.workdir
        if not workdir:
            raise ValueError("HarnessScalingAgent requires a workdir")
        target_dir = self._campaign_root / "rounds" / f"{self._round_number:04d}" / "target"
        workspace_dir = target_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        write_text_atomic(
            target_dir / "context.json",
            json.dumps(self._round_context or {}, indent=2, ensure_ascii=False) + "\n",
        )
        write_model_atomic(target_dir / "measurement.json", measurement)

        session = getattr(self._runtime, "_session", None)
        if session is None:
            write_text_atomic(target_dir / "terminal-error.txt", "Runtime has no session.\n")
        else:
            try:
                terminal = await session.capture_pane(capture_entire=True)
            except Exception as exc:
                write_text_atomic(
                    target_dir / "terminal-error.txt",
                    f"{type(exc).__name__}: {exc}\n",
                )
            else:
                write_text_atomic(target_dir / "terminal.txt", terminal)

        manifest: list[dict[str, Any]] = []
        for entry, base_commit in self._target_base_commits.items():
            path = workdir if entry == "." else f"{workdir.rstrip('/')}/{entry}"
            git_dir = self._target_git_dirs.get(entry)
            if git_dir is None:
                raise RuntimeError(f"Harness Scaling target Git metadata is missing: {entry}")
            status = await environment.exec(
                (
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} "
                    "status --porcelain=v1 --untracked-files=all"
                ),
                user="root",
                timeout_sec=60,
            )
            diff = await environment.exec(
                (
                    f"git -c safe.directory={shlex.quote(path)} "
                    f"--git-dir={shlex.quote(git_dir)} "
                    f"--work-tree={shlex.quote(path)} diff --binary "
                    f"{shlex.quote(base_commit)} -- ."
                ),
                user="root",
                timeout_sec=120,
            )
            if status.return_code != 0 or diff.return_code != 0:
                raise RuntimeError(
                    f"Failed to capture target evidence for {entry}: "
                    f"{status.stderr or diff.stderr or status.stdout or diff.stdout}"
                )
            safe_name = "workspace" if entry == "." else entry.replace("/", "_")
            write_text_atomic(workspace_dir / f"{safe_name}.status.txt", status.stdout or "")
            write_text_atomic(workspace_dir / f"{safe_name}.diff", diff.stdout or "")
            manifest.append(
                {
                    "entry": entry,
                    "base_commit": base_commit,
                    "status": f"{safe_name}.status.txt",
                    "diff": f"{safe_name}.diff",
                }
            )
        write_text_atomic(
            workspace_dir / "manifest.json",
            json.dumps({"repositories": manifest}, indent=2) + "\n",
        )

    def _load_runtime(self, snapshot: RuntimeSnapshot) -> Any:
        """Materialize and construct one committed runtime revision."""
        if self._repository is None:
            raise RuntimeError("Harness Scaling runtime repository is not initialized")
        round_dir = self._campaign_root / "rounds" / f"{self._round_number:04d}"
        runtime_dir = round_dir / "runtime"
        self._repository.materialize_atomic(snapshot.commit, runtime_dir)
        runtime_class = validate_harness_source(runtime_dir, identity=snapshot.commit)
        required = ("setup", "run_until_trap", "configure_target_phase")
        missing = tuple(
            method for method in required if not callable(getattr(runtime_class, method, None))
        )
        if missing:
            raise TypeError(
                "Harness Scaling runtime must implement the lifecycle contract: "
                f"{', '.join(missing)}"
            )
        runtime = runtime_class(
            **self._runtime_constructor_kwargs,
            logs_dir=round_dir / "target",
        )
        try:
            runtime.session_id = (
                f"{self.session_id}-round-{self._round_number:04d}"
                if self.session_id
                else f"harness-scaling-round-{self._round_number:04d}"
            )
            runtime.context_id = self.context_id
        except (AttributeError, TypeError) as exc:
            raise TypeError(
                "Harness Scaling runtime must expose writable session_id and context_id "
                "identity fields"
            ) from exc
        from perfrace.evolution.loader import StaticRuntime

        return StaticRuntime(runtime)

    def _write_state(
        self,
        *,
        stop_reason: Literal["running", "insufficient-time", "deadline", "failed"],
        completed_at: float | None = None,
    ) -> None:
        """Persist the current campaign summary atomically."""
        summary = HarnessScalingSummary(
            task_id=self._task_id(),
            started_at=self._campaign_started_at,
            completed_at=completed_at,
            stop_reason=stop_reason,
            rounds=tuple(self._rounds),
        )
        write_model_atomic(self._campaign_root / "state.json", summary)
        if completed_at is not None:
            write_model_atomic(self._campaign_root / "campaign-summary.json", summary)

    def _task_id(self) -> str:
        """Derive the task identity from Harbor's trial-scoped session name."""
        source = self.session_id or self.logs_dir.parent.name
        task_id = source.split("__", 1)[0].strip()
        if not task_id:
            raise RuntimeError("Harness Scaling could not derive the task identity")
        return task_id
