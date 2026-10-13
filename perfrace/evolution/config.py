"""Configuration loading for native offline harness evolution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from perfrace.run.config import REPO_ROOT


class HarnessEvolutionConfigError(ValueError):
    """Raised when an offline harness-evolution config is invalid."""


class StrictConfig(BaseModel):
    """Base configuration model with strict unknown-field rejection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SplitConfig(StrictConfig):
    """Deterministic split parameters for the final 100-instance universe."""

    expected_total: int = Field(default=100, ge=1)
    early_test_count: int = Field(default=32, ge=0)
    train_count: int = Field(default=40, ge=1)
    validation_count: int = Field(default=10, ge=1)
    test_count: int | None = Field(default=None, ge=0)
    train_seed: int = 42
    validation_seed: int = 43
    allow_empty_test: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> SplitConfig:
        """Require a held-out test unless an explicit canary opts out."""
        assigned = self.early_test_count + self.train_count + self.validation_count
        if assigned > self.expected_total or (
            assigned == self.expected_total and not self.allow_empty_test
        ):
            raise ValueError("split counts must leave at least one later test instance")
        return self


class EvolutionProtocolConfig(StrictConfig):
    """Generation, attempt, and active-work budgets."""

    generations: int = Field(default=5, ge=2)
    train_batch_size: int | None = Field(default=None, ge=1)
    train_batch_seed: int = 44
    validation_generations: tuple[int, ...] = ()
    train_attempts: int = Field(default=1, ge=1)
    validation_attempts: int = Field(default=3, ge=1)
    test_attempts: int = Field(default=3, ge=1)
    train_timeout_sec: int = Field(default=2700, gt=300)
    validation_timeout_sec: int = Field(default=14400, gt=300)
    test_timeout_sec: int = Field(default=14400, gt=300)
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "high"
    trust_evolved_code: bool = False

    @field_validator("validation_generations", mode="before")
    @classmethod
    def normalize_validation_generations(cls, value: object) -> object:
        """Accept YAML lists while storing one immutable ordered tuple."""
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_validation_generations(self) -> EvolutionProtocolConfig:
        """Require an ordered, unique subset of configured generations."""
        generations = self.validation_generations
        if generations and (
            tuple(sorted(set(generations))) != generations
            or generations[0] < 0
            or generations[-1] > self.generations
        ):
            raise ValueError(
                "protocol.validation_generations must be unique, ordered, and within "
                "protocol.generations"
            )
        return self


class ConcurrencyConfig(StrictConfig):
    """Qualified stage-specific concurrency limits."""

    qualified_max: int = Field(default=24, ge=1, le=40)
    debugger_max_workers: int = Field(default=20, ge=1, le=40)
    train: int = Field(default=20, ge=1, le=40)
    baseline: int = Field(default=24, ge=1, le=40)
    validation: int = Field(default=24, ge=1, le=40)
    test: int = Field(default=24, ge=1, le=40)

    @model_validator(mode="after")
    def require_qualified_limits(self) -> ConcurrencyConfig:
        """Keep every stage at or below the frozen qualification result."""
        stages = {
            "debugger_max_workers": self.debugger_max_workers,
            "train": self.train,
            "baseline": self.baseline,
            "validation": self.validation,
            "test": self.test,
        }
        over = [name for name, value in stages.items() if value > self.qualified_max]
        if over:
            raise ValueError(
                "stage concurrency exceeds concurrency.qualified_max: " + ", ".join(over)
            )
        return self


class HarnessEvolutionConfig(StrictConfig):
    """Complete user configuration for one offline evolution experiment."""

    experiment_name: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    artifact_root: Path = Path("data/harness-evolution")
    release_catalog: Path = Path("releases/instance-releases.json")
    split_manifest: Path | None = None
    early_test_manifest: Path | None = None
    instance_root: Path
    base_run_config: Path
    harness_source: Path = Path("boxbox/terminus_boxbox/harness")
    model_name: str = Field(min_length=1)
    split: SplitConfig = SplitConfig()
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    protocol: EvolutionProtocolConfig = EvolutionProtocolConfig()

    @field_validator(
        "artifact_root",
        "release_catalog",
        "split_manifest",
        "early_test_manifest",
        "instance_root",
        "base_run_config",
        "harness_source",
        mode="before",
    )
    @classmethod
    def normalize_paths(cls, value: object) -> Path | None:
        """Convert YAML path strings before strict field validation."""
        if value is None:
            return value
        if not isinstance(value, (str, Path)):
            raise TypeError("path values must be strings or Path instances")
        return Path(value)

    @model_validator(mode="after")
    def require_split_source(self) -> HarnessEvolutionConfig:
        """Require either one frozen split manifest or inputs for deterministic split generation."""
        if self.split_manifest is None and self.early_test_manifest is None:
            raise ValueError("Harness evolution requires split_manifest or early_test_manifest")
        return self


@dataclass(frozen=True)
class LoadedHarnessEvolutionConfig:
    """Resolved harness-evolution config and its source identity."""

    source_path: Path
    source_sha256: str
    config: HarnessEvolutionConfig


def load_harness_evolution_config(
    path: Path | str,
) -> LoadedHarnessEvolutionConfig:
    """Load, validate, and workspace-resolve one evolution YAML config."""
    source_path = Path(path).expanduser().resolve()
    try:
        raw_bytes = source_path.read_bytes()
        payload = yaml.safe_load(raw_bytes) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise HarnessEvolutionConfigError(
            f"Failed to read harness evolution config {source_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise HarnessEvolutionConfigError("Harness evolution config must be a mapping")
    try:
        config = HarnessEvolutionConfig.model_validate(payload)
    except ValidationError as exc:
        raise HarnessEvolutionConfigError(str(exc)) from exc
    resolved = config.model_copy(
        update={
            "artifact_root": _workspace_path(config.artifact_root),
            "release_catalog": _workspace_path(config.release_catalog),
            "split_manifest": (
                _workspace_path(config.split_manifest)
                if config.split_manifest is not None
                else None
            ),
            "early_test_manifest": (
                _workspace_path(config.early_test_manifest)
                if config.early_test_manifest is not None
                else None
            ),
            "instance_root": _workspace_path(config.instance_root),
            "base_run_config": _workspace_path(config.base_run_config),
            "harness_source": _workspace_path(config.harness_source),
        }
    )
    return LoadedHarnessEvolutionConfig(
        source_path=source_path,
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        config=resolved,
    )


def _workspace_path(path: Path) -> Path:
    """Resolve repository-owned paths consistently with `perfrace run`."""
    expanded = path.expanduser()
    return (expanded if expanded.is_absolute() else REPO_ROOT / expanded).resolve()
