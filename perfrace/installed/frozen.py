"""Frozen Harness: execute the shared H0 without harness review or replacement."""

from boxbox.terminus_boxbox.kernel.interfaces import TaskPhase

from .terminus_boxbox import TerminusBoxBoxAgent


class FrozenHarnessAgent(TerminusBoxBoxAgent):
    """Preserve the task session across evaluations while keeping the harness fixed."""

    @staticmethod
    def name() -> str:
        return "frozen"

    def task_phase(self) -> TaskPhase:
        return TaskPhase.NO_REVIEW
