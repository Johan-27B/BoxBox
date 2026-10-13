"""Derived filesystem paths for one harness-evolution experiment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HarnessEvolutionPaths:
    """Own every durable path below one experiment artifact directory."""

    artifact_root: Path
    experiment_name: str

    @property
    def root(self) -> Path:
        return self.artifact_root / self.experiment_name

    @property
    def resolved_config(self) -> Path:
        return self.root / "resolved-config.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def splits(self) -> Path:
        return self.root / "splits"

    @property
    def runtime_repository(self) -> Path:
        return self.root / "runtime" / "repository"

    @property
    def frozen_runtime(self) -> Path:
        return self.root / "runtime" / "frozen"

    @property
    def frozen_runtime_marker(self) -> Path:
        return self.root / "runtime" / "frozen-runtime.json"

    @property
    def baseline(self) -> Path:
        return self.root / "baseline"

    @property
    def generations(self) -> Path:
        return self.root / "generations"

    @property
    def validation(self) -> Path:
        return self.root / "validation"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def selection(self) -> Path:
        return self.root / "selection.json"

    @property
    def usage_report(self) -> Path:
        return self.root / "usage.json"

    @property
    def usage_markdown(self) -> Path:
        return self.root / "usage.md"

    @property
    def test(self) -> Path:
        return self.root / "test"

    @property
    def test_manifest(self) -> Path:
        return self.test / "test-manifest.txt"

    @property
    def test_config(self) -> Path:
        return self.test / "offline-hstar.yaml"

    @property
    def test_spec(self) -> Path:
        return self.test / "stage.json"

    @property
    def test_run_script(self) -> Path:
        return self.test / "run.sh"

    @property
    def test_score_script(self) -> Path:
        return self.test / "score.sh"

    def generation(self, number: int) -> Path:
        """Return the directory for one train generation."""
        return self.generations / f"{number:04d}"

    def train_batch(self, number: int) -> Path:
        """Return the frozen Train batch manifest for one generation."""
        return self.splits / "train-batches" / f"generation-{number:04d}.txt"

    def validation_generation(self, number: int) -> Path:
        """Return the directory for one validation generation."""
        return self.validation / f"{number:04d}"
