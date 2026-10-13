"""PerfRace entry point for the separately implemented bounded ablation."""

from boxbox.terminus_boxbox import TerminusBoxBox
from perfrace.ablations.bounded import BoundedKernel

from .terminus_boxbox import TerminusBoxBoxAgent


class BoundedTerminusBoxBoxAgent(TerminusBoxBoxAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reuse the adapter's provider/tool configuration, not a second H0.
        self._kernel = BoundedKernel(
            runtime_class=TerminusBoxBox,
            logs=self.logs_dir,
            constructor=self._kernel._constructor,
        )

    @staticmethod
    def name() -> str:
        return "bounded-boxbox"
