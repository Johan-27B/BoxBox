"""Build PerfRace's own audit report for one finished Harbor ``Job``.

Every trial in a Harbor ``Job`` shares one ``VerifierConfig``, so
``PerfRaceVerifier`` never knows whether it is measuring the nop baseline or
a candidate agent -- it only ever reads and returns one trial's
``Measurement``. Pairing each task's baseline with its candidate trial(s) and
computing reward can only happen here, once ``Job.run()`` has produced every
trial's ``TrialResult`` and this module can see the whole job at once.

Writes, beside Harbor's own job outputs:

- ``run.json`` -- ``RunSummary`` (schema in ``types.py``).
- ``job.yaml`` -- the resolved Harbor job config, for reproducibility.
- ``trials/NNNN-<trial_name>.measurement.json`` -- a copy of each
  trial's ``Measurement``.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from harbor.models.job.config import JobConfig

from perfrace.run.config import REPO_ROOT, LoadedRun
from perfrace.run.types import PerfRaceConfig, Measurement, RunSummary, RunTaskSummary
from perfrace.run.types import RunTrialSummary, ScoringDirection
from perfrace.run.verifier import MEASUREMENT_FILENAME

logger = logging.getLogger(__name__)

NOP_AGENT_NAME = "nop"


@dataclass(frozen=True)
class RunPaths:
    """Where PerfRace writes its own audit artifacts for one Harbor job.

    Mirrors Harbor's own ``TrialPaths``/``EnvironmentPaths`` convention: one
    small frozen dataclass owns every derived path so callers never inline
    ``jobs_dir / job_name / "perfrace" / ...`` themselves.

        <jobs_dir>/<job_name>/perfrace/run.json
        <jobs_dir>/<job_name>/perfrace/job.yaml
        <jobs_dir>/<job_name>/perfrace/trials/0001-<trial_name>.measurement.json
    """

    jobs_dir: Path
    job_name: str

    @property
    def run_dir(self) -> Path:
        return self.jobs_dir / self.job_name / "perfrace"

    @property
    def trials_dir(self) -> Path:
        return self.run_dir / "trials"

    @property
    def summary_path(self) -> Path:
        return self.run_dir / "run.json"

    @property
    def job_config_path(self) -> Path:
        return self.run_dir / "job.yaml"

    def trial_artifact_path(self, index: int, trial_name: str) -> Path:
        stem = _safe_artifact_stem(trial_name)
        return self.trials_dir / f"{index:04d}-{stem}.measurement.json"

    def mkdir(self) -> None:
        self.trials_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class _PairingRecord:
    """A parsed ``RunTrialSummary`` plus the context needed to pair/score it.

    Not part of the ``run.json`` schema (``types.py`` owns that) -- purely an
    in-memory grouping key (``task_name``/``is_baseline``) and a lookup path
    for the task's declared scoring direction (``task_dir``), alongside the
    already-built summary that goes straight into the written output.
    """

    task_name: str
    is_baseline: bool
    task_dir: Path
    summary: RunTrialSummary
    use_neutral_reward: bool


def write_run_artifacts(
    loaded: LoadedRun,
    job: JobConfig,
    job_result: Any,
) -> Path:
    """Pair baseline/candidate trials, compute reward, and write the run summary."""
    paths = RunPaths(jobs_dir=job.jobs_dir, job_name=job.job_name)
    paths.mkdir()

    records = [
        _read_pairing_record(trial_result, index, paths)
        for index, trial_result in enumerate(job_result.trial_results, start=1)
    ]

    summary = RunSummary(
        job_name=job.job_name,
        note=loaded.note,
        agent_tag=loaded.agent_tag,
        enable_cache=loaded.enable_cache,
        used_api_gateway=loaded.api_gateway is not None,
        git_commit=_git_commit(),
        trial_count=len(records),
        stats={"n_errored_trials": job_result.stats.n_errored_trials},
        tasks=_group_and_score(records),
    )
    paths.summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    paths.job_config_path.write_text(
        yaml.safe_dump(job.model_dump(mode="json", exclude={"verifier"}), sort_keys=True),
        encoding="utf-8",
    )
    logger.info(
        "Wrote run summary: %s (%d trials, %d tasks)",
        paths.summary_path,
        len(records),
        len(summary.tasks),
    )
    return paths.run_dir


def _read_pairing_record(trial_result: Any, index: int, paths: RunPaths) -> _PairingRecord:
    artifact_path = paths.trial_artifact_path(index, trial_result.trial_name)
    trial_dir = _trial_dir_from_uri(trial_result.trial_uri)
    task_dir = trial_result.task_id.get_local_path()
    is_baseline = trial_result.agent_info.name == NOP_AGENT_NAME
    step_results = getattr(trial_result, "step_results", None)

    perf_trial: Measurement | None = None
    error: str | None = None
    try:
        perf_trial = _read_perf_trial(
            trial_dir,
            step_results=step_results,
            direction=None if is_baseline else _scoring_direction(task_dir),
        )
    except (OSError, ValueError) as exc:
        error = str(exc)
        logger.warning(
            "Trial has no readable measurement.json: trial=%s error=%s",
            trial_result.trial_name,
            error,
        )
    else:
        artifact_path.write_text(perf_trial.model_dump_json(indent=2), encoding="utf-8")

    summary = RunTrialSummary(
        trial_name=trial_result.trial_name,
        agent=trial_result.agent_info.name,
        trial_uri=trial_result.trial_uri,
        artifact=str(artifact_path.relative_to(paths.run_dir)),
        perf_trial=perf_trial,
        error=error,
    )
    return _PairingRecord(
        task_name=trial_result.task_name,
        is_baseline=is_baseline,
        task_dir=task_dir,
        summary=summary,
        use_neutral_reward=(
            not is_baseline
            and bool(step_results)
            and perf_trial is not None
            and (
                perf_trial.verdict != "ACCEPTED"
                or perf_trial.value is None
                or float(perf_trial.value) <= 0
            )
        ),
    )


def _group_and_score(records: list[_PairingRecord]) -> list[RunTaskSummary]:
    """Group trial records by task and compute each candidate's reward.

    Each task has at most one baseline record (the nop trial,
    ``scale_with_attempts=False`` keeps it singular even with
    ``n_attempts > 1``) and zero or more candidate records.
    """
    task_names: list[str] = []
    baselines: dict[str, _PairingRecord] = {}
    candidates: dict[str, list[_PairingRecord]] = {}
    for record in records:
        if record.task_name not in candidates:
            task_names.append(record.task_name)
            candidates[record.task_name] = []
        if record.is_baseline:
            baselines[record.task_name] = record
        else:
            candidates[record.task_name].append(record)

    tasks_summary: list[RunTaskSummary] = []
    for task_name in task_names:
        baseline = baselines.get(task_name)
        direction = (
            _scoring_direction(baseline.task_dir)
            if baseline is not None
            else _scoring_direction(candidates[task_name][0].task_dir)
        )
        candidate_summaries = [
            _score_candidate(candidate, baseline, direction) for candidate in candidates[task_name]
        ]
        tasks_summary.append(
            RunTaskSummary(
                task_name=task_name,
                baseline=baseline.summary if baseline is not None else None,
                candidates=candidate_summaries,
            )
        )
    return tasks_summary


def _score_candidate(
    candidate: _PairingRecord,
    baseline: _PairingRecord | None,
    direction: ScoringDirection | None,
) -> RunTrialSummary:
    summary = candidate.summary
    if baseline is None or baseline.summary.perf_trial is None:
        return summary
    if summary.perf_trial is None or direction is None:
        return summary
    if candidate.use_neutral_reward:
        logger.info(
            "Assigned neutral reward to candidate with no selectable checkpoint: task=%s trial=%s",
            candidate.task_name,
            summary.trial_name,
        )
        return summary.model_copy(update={"reward": 1.0})
    try:
        reward = summary.perf_trial.reward_against(baseline.summary.perf_trial, direction)
    except ValueError as exc:
        logger.warning(
            "Reward computation failed: task=%s trial=%s error=%s",
            candidate.task_name,
            summary.trial_name,
            exc,
        )
        return summary.model_copy(update={"reward_error": str(exc)})
    logger.info(
        "Scored candidate: task=%s trial=%s reward=%.4f",
        candidate.task_name,
        summary.trial_name,
        reward,
    )
    return summary.model_copy(update={"reward": reward})


def _scoring_direction(task_dir: Path) -> ScoringDirection | None:
    config = PerfRaceConfig.from_task_dir(task_dir)
    if config is None or config.measurement is None:
        return None
    return config.measurement.direction


def _trial_dir_from_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Unsupported Harbor trial URI: {uri}")
    return Path(parsed.path)


def _read_perf_trial(
    trial_dir: Path,
    *,
    step_results: list[Any] | None = None,
    direction: ScoringDirection | None = None,
) -> Measurement:
    """Read a trial's ``measurement.json``.

    Single-step trials write it directly under ``verifier/``. Multi-checkpoint
    trials (PerfRace's own ``CheckpointTrial``) never populate that
    top-level path -- each checkpoint's own result is archived under
    ``checkpoints/<name>/verifier/`` instead. Candidate trials select the best
    correctness-passing checkpoint for the task's scoring direction. Baselines
    retain the latest scoreable checkpoint behavior. If no checkpoint was
    scoreable, retain the last recorded failure measurement for audit and
    assign the candidate a neutral reward of 1.0 during pairing.
    """
    report_path = trial_dir / "verifier" / MEASUREMENT_FILENAME
    if report_path.is_file():
        return Measurement.model_validate_json(report_path.read_text(encoding="utf-8"))

    step_report_path = _checkpoint_perf_trial_path(
        trial_dir,
        step_results,
        direction=direction,
    )
    if step_report_path is not None:
        return Measurement.model_validate_json(step_report_path.read_text(encoding="utf-8"))

    # No multi-checkpoint fallback applies (or none of it panned out) --
    # re-attempt the original top-level path so the caller sees the expected
    # error.
    return Measurement.model_validate_json(report_path.read_text(encoding="utf-8"))


def _checkpoint_perf_trial_path(
    trial_dir: Path,
    step_results: list[Any] | None,
    *,
    direction: ScoringDirection | None,
) -> Path | None:
    """Return the selected checkpoint measurement for one trial.

    Candidate trials provide a scoring direction and select their best
    correctness-passing checkpoint. Baselines provide no direction and retain
    the latest scoreable checkpoint. If the attempt never produced a scoreable
    checkpoint, return its last recorded measurement for audit. Pairing assigns
    a neutral reward of 1.0 to that all-unselectable multi-checkpoint attempt.
    """
    if not step_results:
        return None
    last_recorded: Path | None = None
    selected: tuple[float, Path] | None = None
    for step_result in reversed(step_results):
        candidate = (
            trial_dir / "checkpoints" / step_result.step_name / "verifier" / MEASUREMENT_FILENAME
        )
        if not candidate.is_file():
            continue
        if last_recorded is None:
            last_recorded = candidate
        try:
            measurement = Measurement.model_validate_json(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if measurement.verdict != "ACCEPTED" or measurement.value is None:
            continue
        value = float(measurement.value)
        if value <= 0:
            continue
        if direction is None:
            return candidate
        if selected is None:
            selected = (value, candidate)
            continue
        selected_value, _ = selected
        if (direction == "minimize" and value < selected_value) or (
            direction == "maximize" and value > selected_value
        ):
            selected = (value, candidate)
    return selected[1] if selected is not None else last_recorded


def _git_commit() -> str | None:
    """Return the PerfRace repo's current commit hash, or ``None`` if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _safe_artifact_stem(value: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value.strip())
    return stem or "trial"
