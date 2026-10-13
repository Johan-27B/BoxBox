"""Progressive-disclosure indexes over completed PerfRace train jobs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from perfrace.evolution.types import (
    AttemptEvidence,
    GenerationEvidence,
    TaskEvidence,
    TrainBatch,
)
from perfrace.run.types import RunSummary


def build_generation_evidence(
    run_summary_path: Path,
    *,
    batch: TrainBatch,
    harness_generation: int,
    train_schedule_sha256: str,
    expected_attempts: int,
) -> GenerationEvidence:
    """Build a raw-artifact index for one complete train generation."""
    resolved_summary = run_summary_path.expanduser().resolve()
    summary = RunSummary.model_validate_json(resolved_summary.read_text(encoding="utf-8"))
    run_dir = resolved_summary.parent
    tasks: list[TaskEvidence] = []
    for task in summary.tasks:
        if len(task.candidates) != expected_attempts:
            raise ValueError(
                f"Task {task.task_name} has {len(task.candidates)} attempts; "
                f"expected {expected_attempts}"
            )
        attempts: list[AttemptEvidence] = []
        for candidate in task.candidates:
            if candidate.reward is None:
                raise ValueError(
                    f"Task {task.task_name} trial {candidate.trial_name} has no reward"
                )
            parsed = urlparse(candidate.trial_uri)
            if parsed.scheme != "file":
                raise ValueError(f"Unsupported trial URI: {candidate.trial_uri}")
            trial_dir = Path(parsed.path).resolve()
            selected_measurement = (run_dir / candidate.artifact).resolve()
            if not selected_measurement.is_file():
                raise ValueError(
                    f"Selected measurement is missing for {candidate.trial_name}: "
                    f"{selected_measurement}"
                )
            checkpoint_measurements = tuple(
                sorted(
                    trial_dir.glob("checkpoints/*/verifier/measurement.json"),
                    key=lambda path: path.as_posix(),
                )
            )
            trajectories = tuple(
                sorted(
                    (path for path in trial_dir.rglob("trajectory.json") if path.is_file()),
                    key=lambda path: path.as_posix(),
                )
            )
            attempts.append(
                AttemptEvidence(
                    trial_name=candidate.trial_name,
                    reward=candidate.reward,
                    trial_dir=trial_dir,
                    selected_measurement=selected_measurement,
                    checkpoint_measurements=checkpoint_measurements,
                    trajectories=trajectories,
                )
            )
        tasks.append(TaskEvidence(task_name=task.task_name, attempts=tuple(attempts)))
    return GenerationEvidence(
        iteration=batch.generation,
        generation=harness_generation,
        epoch=batch.epoch,
        batch_index=batch.batch_index,
        task_ids=batch.task_ids,
        train_schedule_sha256=train_schedule_sha256,
        run_summary_path=resolved_summary,
        tasks=tuple(tasks),
    )
