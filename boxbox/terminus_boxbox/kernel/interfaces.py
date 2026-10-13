"""Minimal contract between the fixed Kernel and evolvable TerminusBoxBox runtimes."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


@dataclass(frozen=True)
class RuntimeState:
    """Opaque runtime-owned state copied across activation."""

    data: dict[str, Any]

    @classmethod
    def capture(cls, data: dict[str, Any]) -> RuntimeState:
        """Capture an isolated copy of runtime-owned data."""
        if not isinstance(data, dict):
            raise TypeError("RuntimeState data must be a dictionary")
        return cls(data=copy.deepcopy(data))


@dataclass(frozen=True)
class FaultReport:
    """New fault-journal evidence available to one review."""

    last_reviewed_at: str | None
    latest_event_at: str


@dataclass(frozen=True)
class ReviewResult:
    """Target-trajectory boundary covered by one completed review."""

    context_through_sequence: int = 0
    context_through_offset: int = 0

    def __post_init__(self) -> None:
        if type(self.context_through_sequence) is not int or self.context_through_sequence < 0:
            raise ValueError("ReviewResult context sequence must be a non-negative integer")
        if type(self.context_through_offset) is not int or self.context_through_offset < 0:
            raise ValueError("ReviewResult context offset must be a non-negative integer")


class TaskPhase(str, Enum):
    TASK = "task"
    NO_REVIEW = "no_review"


class RuntimeTrap(str, Enum):
    """Synchronous runtime requests handled by Kernel."""

    COMPLETE = "complete"
    BOXBOX = "boxbox"


@runtime_checkable
class Runtime(Protocol):
    """Behavior Kernel needs from an evolvable runtime."""

    async def review(
        self,
        environment: BaseEnvironment,
        context: AgentContext,
        *,
        sequence: int,
        reviewer: Runtime,
        fault_report: FaultReport | None,
    ) -> ReviewResult:
        """Run evolvable candidate-generation policy."""

    def export_state(self) -> RuntimeState:
        """Export runtime-owned state."""

    def import_state(self, state: RuntimeState) -> None:
        """Import or migrate predecessor state."""

    def release_session(self) -> Any:
        """Release the live target session."""

    def attach_session(self, session: Any) -> Any:
        """Attach the live target session after validation."""

    async def restart_session(self, session: Any) -> Any:
        """Replace a failed runtime's terminal with a fresh shell."""

    def prepare_continuation(self) -> str:
        """Prepare restored state and return a continuation prompt."""

    def reconcile_review_trajectory(self) -> None:
        """Reconcile runtime trajectory counters with the canonical journal."""

    def mark_harness_context_accepted(
        self,
        through_sequence: int,
        through_offset: int,
    ) -> None:
        """Start a new trajectory epoch after Kernel accepts this harness."""

    async def ensure_agent_session(self) -> None:
        """Ensure the target session is usable."""

    def configure_target_phase(self, *, boxbox_enabled: bool) -> None:
        """Configure the next target phase."""

    async def run_until_trap(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> RuntimeTrap | None:
        """Execute target work until a Kernel-visible trap or ordinary return."""
