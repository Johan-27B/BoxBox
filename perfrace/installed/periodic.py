"""PerfRace entry point for the separately implemented periodic ablation."""

from boxbox.terminus_boxbox import TerminusBoxBox
from perfrace.ablations.periodic import PeriodicKernel

from .terminus_boxbox import TerminusBoxBoxAgent


class PeriodicTerminusBoxBoxAgent(TerminusBoxBoxAgent):
    def __init__(self, *args, review_interval_sec=1800, **kwargs):
        super().__init__(*args, **kwargs)
        self._kernel = PeriodicKernel(
            runtime_class=TerminusBoxBox,
            logs=self.logs_dir,
            constructor=self._kernel._constructor,
            review_interval_sec=review_interval_sec,
        )

    @staticmethod
    def name() -> str:
        return "periodic-boxbox"
