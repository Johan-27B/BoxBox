"""Evaluate an offline-selected harness without further harness optimization."""

from pathlib import Path

from .frozen import FrozenHarnessAgent


class EvolvedHarnessAgent(FrozenHarnessAgent):
    """Use the same task lifecycle as Frozen Harness with a selected source snapshot."""

    def __init__(self, *args, **kwargs):
        source = kwargs.get("harness_source")
        if not isinstance(source, (str, Path)):
            raise ValueError("EvolvedHarnessAgent requires harness_source")
        self._harness_identity = kwargs.pop("harness_identity", None)
        if not isinstance(self._harness_identity, str) or not self._harness_identity:
            raise ValueError("EvolvedHarnessAgent requires harness_identity")
        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "harness-evolution"

    def version(self) -> str:
        return self._harness_identity
