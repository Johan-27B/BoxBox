"""Versioned serialized records for offline harness evolution."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvolutionStage(StrEnum):
    """Durable outer-loop stages."""

    INITIALIZED = "initialized"
    BASELINING = "baselining"
    TRAINING = "training"
    ANALYZING = "analyzing"
    EVOLVING = "evolving"
    VALIDATING = "validating"
    SELECTING = "selecting"
    TEST_READY = "test-ready"
    COMPLETE = "complete"


class StrictRecord(BaseModel):
    """Base model for persisted, forward-versioned experiment records."""

    model_config = ConfigDict(extra="forbid", strict=True)


class SplitManifest(StrictRecord):
    """Deterministic task split derived from one immutable release catalog."""

    schema_version: int = Field(default=2, ge=1)
    catalog_sha256: str = Field(min_length=64, max_length=64)
    source_manifest_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    python_version: str = Field(min_length=1)
    train_seed: int
    validation_seed: int
    early_test: tuple[str, ...]
    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]


class TrainBatch(StrictRecord):
    """One frozen mini-batch assigned to a training generation."""

    schema_version: int = Field(default=1, ge=1)
    generation: int = Field(ge=1)
    epoch: int = Field(ge=1)
    batch_index: int = Field(ge=1)
    task_ids: tuple[str, ...]


class ResolvedEvolutionPlan(StrictRecord):
    """Side-effect-free resolved split and configured compute totals."""

    schema_version: int = Field(default=3, ge=1)
    experiment_name: str = Field(min_length=1)
    harness_source_sha256: str = Field(min_length=64, max_length=64)
    base_run_config_sha256: str = Field(min_length=64, max_length=64)
    controller_source_sha256: str = Field(min_length=64, max_length=64)
    task_checksums: dict[str, str]
    split: SplitManifest
    generations: int = Field(ge=2)
    train_batch_size: int = Field(ge=1)
    train_batch_seed: int
    train_batches: tuple[TrainBatch, ...]
    train_schedule_sha256: str = Field(min_length=64, max_length=64)
    validation_generations: tuple[int, ...]
    train_attempts: int = Field(ge=1)
    validation_attempts: int = Field(ge=1)
    test_attempts: int = Field(ge=1)
    train_timeout_sec: int = Field(ge=1)
    validation_timeout_sec: int = Field(ge=1)
    test_timeout_sec: int = Field(ge=1)
    debugger_max_workers: int = Field(ge=1, le=40)
    train_concurrency: int = Field(ge=1, le=40)
    baseline_concurrency: int = Field(ge=1, le=40)
    validation_concurrency: int = Field(ge=1, le=40)
    test_concurrency: int = Field(ge=1, le=40)
    train_candidate_attempts: int = Field(ge=1)
    validation_candidate_attempts: int = Field(ge=1)
    test_candidate_attempts: int = Field(ge=0)
    validation_trial_hours: float = Field(gt=0)
    test_trial_hours: float = Field(ge=0)
    configured_trial_hours: float = Field(gt=0)


class StageSpec(StrictRecord):
    """Immutable identity of one train or validation PerfRace stage."""

    schema_version: int = Field(default=3, ge=1)
    stage: Literal["train", "validation"]
    iteration: int = Field(ge=1)
    generation: int = Field(ge=0)
    epoch: int | None = Field(default=None, ge=1)
    batch_index: int | None = Field(default=None, ge=1)
    train_schedule_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    task_ids: tuple[str, ...]
    task_checksums: dict[str, str]
    harness_identity: str = Field(min_length=40, max_length=40)
    harness_source_sha256: str = Field(min_length=64, max_length=64)
    base_run_config_sha256: str = Field(min_length=64, max_length=64)
    controller_source_sha256: str = Field(min_length=64, max_length=64)
    attempts: int = Field(ge=1)
    timeout_sec: int = Field(ge=1)
    n_concurrent_trials: int = Field(ge=1)
    effective_concurrency: int = Field(ge=1)
    job_name: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_stage_metadata(self) -> StageSpec:
        """Require batch identity only for Train and bound effective concurrency."""
        batch_fields = (self.epoch, self.batch_index, self.train_schedule_sha256)
        if self.stage == "train" and any(value is None for value in batch_fields):
            raise ValueError("Train stage identity requires epoch, batch, and schedule hash")
        if self.stage == "validation" and any(value is not None for value in batch_fields):
            raise ValueError("Validation stage identity cannot contain Train batch metadata")
        if self.effective_concurrency > self.n_concurrent_trials:
            raise ValueError("effective concurrency cannot exceed configured concurrency")
        return self


class ValidationCandidateSpec(StrictRecord):
    """One frozen runtime exposed as a uniquely named Validation agent."""

    generation: int = Field(ge=0)
    agent_name: str = Field(min_length=1)
    harness_identity: str = Field(min_length=40, max_length=40)
    harness_source: Path
    harness_source_sha256: str = Field(min_length=64, max_length=64)


class ValidationCampaignSpec(StrictRecord):
    """Identity of one globally scheduled multi-generation Validation job."""

    schema_version: int = Field(default=1, ge=1)
    candidates: tuple[ValidationCandidateSpec, ...]
    task_ids: tuple[str, ...]
    task_checksums: dict[str, str]
    base_run_config_sha256: str = Field(min_length=64, max_length=64)
    controller_source_sha256: str = Field(min_length=64, max_length=64)
    attempts: int = Field(ge=1)
    timeout_sec: int = Field(ge=1)
    n_concurrent_trials: int = Field(ge=1, le=40)
    effective_concurrency: int = Field(ge=1, le=40)
    job_name: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidates(self) -> ValidationCampaignSpec:
        """Require deterministic unique candidate and agent identities."""
        generations = tuple(candidate.generation for candidate in self.candidates)
        agent_names = tuple(candidate.agent_name for candidate in self.candidates)
        if not generations or tuple(sorted(set(generations))) != generations:
            raise ValueError("Validation candidates must have unique ordered generations")
        if len(set(agent_names)) != len(agent_names):
            raise ValueError("Validation candidate agent names must be unique")
        expected_effective = min(
            self.n_concurrent_trials,
            len(self.candidates) * len(self.task_ids) * self.attempts,
        )
        if self.effective_concurrency != expected_effective:
            raise ValueError("Validation effective concurrency does not match campaign work")
        return self


class BaselineSpec(StrictRecord):
    """Immutable identity of the required fresh nop-baseline campaign."""

    schema_version: int = Field(default=1, ge=1)
    task_ids: tuple[str, ...]
    task_checksums: dict[str, str]
    base_run_config_sha256: str = Field(min_length=64, max_length=64)
    controller_source_sha256: str = Field(min_length=64, max_length=64)
    n_concurrent_trials: int = Field(ge=1, le=40)
    job_name: str = Field(min_length=1)


class DebuggerWorkerSpec(StrictRecord):
    """Immutable, secret-free specification for one debugger subprocess."""

    schema_version: int = Field(default=1, ge=1)
    config_path: Path
    workspace: Path
    output_dir: Path
    model: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    reasoning_effort: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    context: dict[str, str | int]
    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    shell_root: Path


class FrozenTestSpec(StrictRecord):
    """Identity lock for the generated, not-yet-executed final test."""

    schema_version: int = Field(default=2, ge=1)
    experiment_name: str = Field(min_length=1)
    config_source_path: Path
    config_source_sha256: str = Field(min_length=64, max_length=64)
    base_run_config_sha256: str = Field(min_length=64, max_length=64)
    controller_source_sha256: str = Field(min_length=64, max_length=64)
    model_name: str = Field(min_length=1)
    reasoning_effort: str = Field(min_length=1)
    selected_generation: int = Field(ge=0)
    selected_commit: str = Field(min_length=40, max_length=40)
    selected_source_sha256: str = Field(min_length=64, max_length=64)
    selected_tree_sha256: str = Field(min_length=64, max_length=64)
    harness_source: Path
    task_ids: tuple[str, ...]
    task_checksums: dict[str, str]
    split_manifest_sha256: str = Field(min_length=64, max_length=64)
    test_manifest_sha256: str = Field(min_length=64, max_length=64)
    run_config_sha256: str = Field(min_length=64, max_length=64)
    attempts: int = Field(ge=1)
    timeout_sec: int = Field(ge=1)
    n_concurrent_trials: int = Field(ge=1, le=40)
    job_name: str = Field(min_length=1)


class AggregateScore(StrictRecord):
    """Frozen campaign aggregation for one harness over one task split."""

    schema_version: int = Field(default=1, ge=1)
    official_score: float = Field(ge=0)
    raw_zero_sensitive_score: float = Field(ge=0)
    task_scores: dict[str, float]
    raw_task_scores: dict[str, float]
    attempt_rewards: dict[str, tuple[float, ...]]


class AttemptEvidence(StrictRecord):
    """Pointers to one completed candidate attempt and its raw artifacts."""

    trial_name: str = Field(min_length=1)
    reward: float = Field(ge=0)
    trial_dir: Path
    selected_measurement: Path
    checkpoint_measurements: tuple[Path, ...] = ()
    trajectories: tuple[Path, ...] = ()


class TaskEvidence(StrictRecord):
    """All completed attempts for one training task."""

    task_name: str = Field(min_length=1)
    attempts: tuple[AttemptEvidence, ...]


class GenerationEvidence(StrictRecord):
    """Progressive-disclosure index for one generation's train run."""

    schema_version: int = Field(default=3, ge=1)
    iteration: int = Field(ge=1)
    generation: int = Field(ge=0)
    epoch: int = Field(ge=1)
    batch_index: int = Field(ge=1)
    task_ids: tuple[str, ...]
    train_schedule_sha256: str = Field(min_length=64, max_length=64)
    run_summary_path: Path
    tasks: tuple[TaskEvidence, ...]


class HarnessChange(StrictRecord):
    """One evidence-backed modification declared by the evolve agent."""

    id: str = Field(min_length=1)
    type: Literal["new", "improvement", "rollback"]
    description: str = Field(min_length=1)
    files: tuple[str, ...]
    evidence: tuple[str, ...]
    behavior_pattern: str = Field(min_length=1)
    predicted_benefits: tuple[str, ...]
    regression_risks: tuple[str, ...]
    component: Literal[
        "prompt",
        "tool",
        "context",
        "control",
        "completion",
        "recovery",
        "skill",
        "middleware",
        "subagent",
    ]


class ChangeManifest(StrictRecord):
    """Structured evolve-agent declaration for one lineage transition."""

    schema_version: int = Field(default=2, ge=1)
    iteration: int = Field(ge=1)
    parent_commit: str = Field(min_length=40, max_length=40)
    changes: tuple[HarnessChange, ...]


class GenerationRecord(StrictRecord):
    """Durable identity and artifacts for one evaluated harness generation."""

    generation: int = Field(ge=0)
    commit: str = Field(min_length=40, max_length=40)
    source_sha256: str = Field(min_length=64, max_length=64)
    train_run_dir: Path | None = None
    train_score_path: Path | None = None
    analysis_dir: Path | None = None
    evolve_dir: Path | None = None
    successor_commit: str | None = Field(default=None, min_length=40, max_length=40)


class SelectionRecord(StrictRecord):
    """Validation scores and the deterministically selected frozen generation."""

    schema_version: int = Field(default=2, ge=1)
    selected_generation: int = Field(ge=0)
    selected_commit: str = Field(min_length=40, max_length=40)
    validation_scores: dict[int, AggregateScore]


class EvolutionState(StrictRecord):
    """Resumable state for one offline harness-evolution experiment."""

    schema_version: int = Field(default=2, ge=1)
    experiment_name: str = Field(min_length=1)
    config_sha256: str = Field(min_length=64, max_length=64)
    stage: EvolutionStage = EvolutionStage.INITIALIZED
    active_generation: int = Field(default=0, ge=0)
    generations: tuple[GenerationRecord, ...] = ()
    split_manifest_path: Path
    selection_path: Path | None = None
