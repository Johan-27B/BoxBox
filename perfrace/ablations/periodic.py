"""Scheduled review at completed interaction boundaries, separate from BOXBOX."""

from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harbor.models.trajectories import ToolCall

from boxbox.terminus_boxbox.kernel.interfaces import RuntimeTrap, TaskPhase
from boxbox.terminus_boxbox.kernel.lifecycle import RESUME_ITERATION_GUIDANCE, Kernel


class ReviewSchedule:
    """Wall-clock schedule shared across submissions and runtime replacements."""

    def __init__(self, interval_sec: float = 1800) -> None:
        if (
            isinstance(interval_sec, bool)
            or not isinstance(interval_sec, (int, float))
            or not math.isfinite(interval_sec)
            or interval_sec <= 0
        ):
            raise ValueError("review_interval_sec must be finite and positive")
        self.interval_sec = interval_sec
        self.deadline: float | None = None
        self.scheduled_at: str | None = None
        self.pending: dict | None = None

    def start(self) -> None:
        if self.deadline is None:
            self.reset()

    def reset(self) -> None:
        self.deadline = time.monotonic() + self.interval_sec
        self.scheduled_at = (datetime.now(UTC) + timedelta(seconds=self.interval_sec)).isoformat()
        self.pending = None

    def due(self) -> bool:
        now = time.monotonic()
        if self.deadline is None or now < self.deadline:
            return False
        if self.pending is None:
            self.pending = {
                "interval_sec": self.interval_sec,
                "scheduled_at": self.scheduled_at,
                "triggered_at": datetime.now(UTC).isoformat(),
                "safe_point_delay_sec": now - self.deadline,
            }
        return True


class PeriodicReview:
    """Replace voluntary review with a scheduled trap after tool results."""

    _scheduled_phase = False
    _review_schedule: ReviewSchedule

    def configure_target_phase(self, *, boxbox_enabled: bool) -> None:
        # The core kernel supplies True for ordinary task work, False for
        # final delivery. Only this variant interprets it as scheduled review.
        self._scheduled_phase = boxbox_enabled
        if self._scheduled_phase:
            self._review_schedule.start()
        super().configure_target_phase(boxbox_enabled=False)

    def configure_review_phase(self, *, policy: str) -> None:
        self._scheduled_phase = False
        super().configure_review_phase(policy=policy)

    def _resolve_completion_request(self, trap, output):
        # H0 calls this only after receiving the current tool's result.
        # A requested official evaluation takes precedence over a due review.
        if trap is None and self._scheduled_phase and self._review_schedule.due():
            trap = RuntimeTrap.BOXBOX
        return super()._resolve_completion_request(trap, output)

    def _trajectory_action_name(self, trap):
        if trap == RuntimeTrap.BOXBOX and self._review_schedule.pending is not None:
            return "periodic_review"
        return super()._trajectory_action_name(trap)

    async def _run_agent_loop(self, *args, **kwargs):
        count = await super()._run_agent_loop(*args, **kwargs)
        if (
            self._runtime_trap == RuntimeTrap.BOXBOX
            and self._review_schedule.pending is not None
            and self._trajectory_steps
        ):
            # The schedule, not a model tool call, ended this interaction.
            # Record that event before run_until_trap archives the trajectory.
            step = self._trajectory_steps[-1]
            calls = step.tool_calls or []
            if not any(call.function_name == "periodic_review" for call in calls):
                step.tool_calls = [
                    *calls,
                    ToolCall(
                        tool_call_id=f"periodic-{step.step_id}",
                        function_name="periodic_review",
                        arguments={},
                    ),
                ]
                self._dump_trajectory()
        return count

    async def review(self, *args, **kwargs):
        # There is no voluntary request/feedback handoff in this ablation.
        trap = self._runtime_trap
        self._runtime_trap = None
        try:
            return await super().review(*args, **kwargs)
        finally:
            self._runtime_trap = trap


class PeriodicKernel(Kernel):
    """Keep the core transition implementation and supply an external schedule."""

    def __init__(self, *, review_interval_sec=1800, **kwargs):
        self.schedule = ReviewSchedule(review_interval_sec)
        super().__init__(**kwargs)

    def _create_runtime(self, runtime_class, *, logs_dir=None):
        if not issubclass(runtime_class, PeriodicReview):
            runtime_class = type(
                f"Periodic{runtime_class.__name__}", (PeriodicReview, runtime_class), {}
            )
        runtime = super()._create_runtime(runtime_class, logs_dir=logs_dir)
        runtime._review_schedule = self.schedule
        return runtime

    async def resume(self, instruction, environment, context, *, phase=TaskPhase.TASK):
        # Continue normally without advertising an unavailable boxbox() tool.
        await self.run_active_runtime(
            f"{instruction}\n\n{RESUME_ITERATION_GUIDANCE}",
            environment,
            context,
            phase=phase,
        )

    async def transition(self, runtime, environment, **kwargs):
        result = await super().transition(runtime, environment, **kwargs)
        # Same interval after either a scheduled review or fault recovery.
        self.schedule.reset()
        return result

    def _write_transition(self, transition_dir: Path, **kwargs):
        super()._write_transition(transition_dir, **kwargs)
        path = transition_dir / "transition.json"
        payload = json.loads(path.read_text())
        if payload["trigger"] == RuntimeTrap.BOXBOX.value:
            payload["trigger"] = "periodic_review"
            payload["trigger_metadata"] = self.schedule.pending
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
