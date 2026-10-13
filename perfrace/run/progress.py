"""Shared progress calculation from existing ``CheckpointTrial`` artifacts."""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
from harbor.models.trial.result import TrialResult

from perfrace.run.types import PerfRaceConfig

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42


_REFRESH_SECONDS = 10
_AVERAGE_TOKEN_AXIS = "average_cumulative_input_output_tokens_per_attempt_at_shared_time"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Point:
    x: float
    speedup: float


@dataclass(frozen=True)
class _Series:
    instance_id: str
    trial_name: str
    points: tuple[_Point, ...]


def _load_completed_job(
    job_dir: Path,
    baselines: dict[str, tuple[float, str]],
) -> tuple[list[_Series], list[_Series]]:
    time_series = []
    token_series = []
    result_paths = []
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir():
            continue
        progress = trial_dir / "progress.json"
        final = trial_dir / "result.json"
        result_path = final if final.is_file() else progress
        if result_path.is_file():
            result_paths.append(result_path)
    for result_path in result_paths:
        try:
            result = TrialResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            if not result.step_results and (result_path.parent / "progress.json").is_file():
                result = TrialResult.model_validate_json(
                    (result_path.parent / "progress.json").read_text()
                )
        except (OSError, ValueError):
            continue
        if result.agent_info.name == "nop" or not result.step_results:
            continue
        instance_id = result.task_name.split("/", 1)[-1]
        if instance_id not in baselines:
            continue
        cumulative_seconds = 0.0
        legacy_cumulative_tokens = 0
        token_log_path = job_dir / "token-proxy" / f"{result.trial_name}__agent.jsonl"
        token_timeline = _token_timeline(token_log_path)
        has_proxy_accounting = any(
            ((step.agent_result.metadata or {}).get("token_accounting") or {}).get("source")
            == "token-proxy"
            for step in result.step_results
            if step.agent_result is not None
        )
        time_points = []
        token_points = []
        for step in result.step_results:
            data = step.model_dump(mode="json")
            cumulative_seconds += _duration(data.get("agent_execution"))
            submission_seconds = cumulative_seconds
            context = data.get("agent_result") or {}
            accounting = (context.get("metadata") or {}).get("token_accounting") or {}
            if not has_proxy_accounting or accounting.get("source") == "token-proxy":
                legacy_cumulative_tokens += int(context.get("n_input_tokens") or 0)
                legacy_cumulative_tokens += int(context.get("n_output_tokens") or 0)
            report_path = (
                result_path.parent
                / "checkpoints"
                / step.step_name
                / "verifier"
                / "measurement.json"
            )
            cumulative_seconds += _duration(data.get("verifier"))
            if not report_path.is_file():
                continue
            measurement = json.loads(report_path.read_text(encoding="utf-8"))
            speedup = _speedup(measurement, baselines[instance_id])
            if speedup is None:
                continue
            finished_at = (data.get("agent_execution") or {}).get("finished_at")
            if token_timeline and finished_at:
                timestamp = datetime.fromisoformat(finished_at.replace("Z", "+00:00")).timestamp()
                cumulative_tokens = _token_total_at(token_timeline, timestamp)
            else:
                cumulative_tokens = legacy_cumulative_tokens
            time_points.append(_Point(submission_seconds / 60.0, speedup))
            token_points.append(_Point(cumulative_tokens / 1_000_000.0, speedup))
        if time_points:
            audited_total = (
                token_timeline[-1][1] if token_timeline else _token_total(token_log_path)
            )
            if audited_total > cumulative_tokens:
                best_speedup = max(point.speedup for point in time_points)
                time_points.append(_Point(time_points[-1].x, best_speedup))
                token_points.append(_Point(audited_total / 1_000_000.0, best_speedup))
            time_series.append(_Series(instance_id, result.trial_name, tuple(time_points)))
            token_series.append(_Series(instance_id, result.trial_name, tuple(token_points)))
    return time_series, token_series


def _aggregate_curve(
    grouped: dict[str, list[_Series]],
    *,
    expected_instances: tuple[str, ...],
) -> tuple[list[float], list[float]]:
    events = sorted(
        {
            0.0,
            *(
                point.x
                for attempts in grouped.values()
                for attempt in attempts
                for point in attempt.points
            ),
        }
    )
    values = []
    for event in events:
        task_values = []
        for instance_id in expected_instances:
            attempt_values = []
            for attempt in grouped.get(instance_id, []):
                best = 1.0
                for point in attempt.points:
                    if point.x > event:
                        break
                    best = max(best, point.speedup)
                attempt_values.append(best)
            task_values.append(
                math.exp(sum(math.log(value) for value in attempt_values) / len(attempt_values))
                if attempt_values
                else 1.0
            )
        values.append(len(task_values) / sum(1.0 / value for value in task_values))
    return events, values


def _aggregate_average_token_curve(
    time_grouped: dict[str, list[_Series]],
    token_grouped: dict[str, list[_Series]],
    *,
    expected_instances: tuple[str, ...],
    expected_attempts: int,
) -> tuple[list[float], list[float]]:
    """Plot aggregate speedup against mean token use at each shared-time event."""
    if expected_attempts <= 0:
        raise ValueError("expected_attempts must be positive")

    token_by_trial = {
        series.trial_name: series for attempts in token_grouped.values() for series in attempts
    }
    events = sorted(
        {
            0.0,
            *(
                point.x
                for attempts in time_grouped.values()
                for attempt in attempts
                for point in attempt.points
            ),
        }
    )
    average_tokens = []
    aggregate_speedups = []
    for event in events:
        task_values = []
        token_total = 0.0
        for instance_id in expected_instances:
            attempt_values = []
            for time_series in time_grouped.get(instance_id, []):
                token_series = token_by_trial.get(time_series.trial_name)
                if token_series is None or len(token_series.points) != len(time_series.points):
                    raise ValueError(f"missing aligned token series for {time_series.trial_name}")
                best = 1.0
                latest_tokens = 0.0
                for time_point, token_point in zip(
                    time_series.points,
                    token_series.points,
                    strict=True,
                ):
                    if time_point.x > event:
                        break
                    best = max(best, time_point.speedup)
                    latest_tokens = token_point.x
                attempt_values.append(best)
                token_total += latest_tokens
            task_values.append(
                math.exp(sum(math.log(value) for value in attempt_values) / len(attempt_values))
                if attempt_values
                else 1.0
            )
        average_tokens.append(token_total / expected_attempts)
        aggregate_speedups.append(len(task_values) / sum(1.0 / value for value in task_values))
    return average_tokens, aggregate_speedups


def _group(series: list[_Series]) -> dict[str, list[_Series]]:
    grouped: dict[str, list[_Series]] = {}
    _extend_grouped(grouped, series)
    return grouped


def _extend_grouped(
    grouped: dict[str, list[_Series]],
    series: list[_Series],
) -> None:
    for item in series:
        grouped.setdefault(item.instance_id, []).append(item)


def _speedup(
    measurement: dict[str, Any],
    baseline: tuple[float, str],
) -> float | None:
    if measurement.get("verdict") != "ACCEPTED":
        return None
    value = measurement.get("value")
    if value is None or float(value) <= 0:
        return None
    baseline_value, direction = baseline
    return (
        float(value) / baseline_value if direction == "maximize" else baseline_value / float(value)
    )


def _current_baselines(job_dir: Path) -> dict[str, tuple[float, str]]:
    expected = _expected_tasks(job_dir)
    if not expected:
        return {}
    baselines: dict[str, tuple[float, str]] = {}
    for trial_dir in job_dir.iterdir():
        if not trial_dir.is_dir():
            continue
        report_path = trial_dir / "verifier" / "measurement.json"
        if not report_path.is_file():
            continue
        config_path = trial_dir / "config.json"
        if config_path.is_file():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                if payload.get("agent", {}).get("name") != "nop":
                    continue
                instance_id = Path(payload["task"]["path"]).name
            except (KeyError, TypeError, ValueError):
                continue
        else:
            stem = trial_dir.name.split("__", 1)[0]
            matches = [instance_id for instance_id in expected if instance_id.startswith(stem)]
            if len(matches) != 1:
                continue
            instance_id = matches[0]
        if instance_id not in expected:
            continue
        try:
            measurement = json.loads(report_path.read_text(encoding="utf-8"))
            value = float(measurement["value"])
        except (KeyError, OSError, TypeError, ValueError):
            continue
        if measurement.get("verdict") != "ACCEPTED" or value <= 0:
            continue
        baselines[instance_id] = (value, expected[instance_id])
    return baselines if len(baselines) == len(expected) else {}


def _run_baselines(job_dir: Path) -> dict[str, tuple[float, str]]:
    expected = _expected_tasks(job_dir)
    summary_path = job_dir / "perfrace" / "run.json"
    if not expected or not summary_path.is_file():
        return _current_baselines(job_dir)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    baselines: dict[str, tuple[float, str]] = {}
    for task in summary.get("tasks", []):
        instance_id = task.get("task_name", "").split("/", 1)[-1]
        measurement = (task.get("baseline") or {}).get("perf_trial") or {}
        value = measurement.get("value")
        if instance_id in expected and value is not None and float(value) > 0:
            baselines[instance_id] = (float(value), expected[instance_id])
    return baselines if len(baselines) == len(expected) else {}


def _expected_tasks(job_dir: Path) -> dict[str, str]:
    try:
        payload = json.loads((job_dir / "config.json").read_text(encoding="utf-8"))
        tasks = payload["tasks"]
    except (OSError, KeyError, TypeError, ValueError):
        return {}
    expected: dict[str, str] = {}
    for task in tasks:
        try:
            task_path = Path(task["path"])
        except (KeyError, TypeError):
            continue
        try:
            config = PerfRaceConfig.from_task_dir(task_path)
        except (OSError, ValueError):
            config = None
        if config is None or config.measurement is None:
            continue
        expected[config.instance_id] = config.measurement.direction
    return expected


def _expected_candidate_attempts(job_dir: Path, instance_count: int) -> int:
    """Return the configured candidate-attempt denominator for average token cost."""
    try:
        payload = json.loads((job_dir / "config.json").read_text(encoding="utf-8"))
        n_attempts = int(payload.get("n_attempts", 1))
        agents = payload.get("agents") or []
    except (OSError, TypeError, ValueError):
        return instance_count

    candidate_attempts_per_task = sum(
        n_attempts if agent.get("scale_with_attempts", True) else 1
        for agent in agents
        if agent.get("name") != "nop"
    )
    if candidate_attempts_per_task <= 0:
        candidate_attempts_per_task = n_attempts
    return instance_count * candidate_attempts_per_task


def _trial_instance(
    trial_dir: Path,
    baselines: dict[str, tuple[float, str]],
) -> str | None:
    try:
        payload = json.loads((trial_dir / "config.json").read_text(encoding="utf-8"))
        task_path = payload["task"]["path"]
    except (OSError, KeyError, TypeError, ValueError):
        return None
    instance_id = Path(task_path).name
    return instance_id if instance_id in baselines else None


def _token_total(path: Path) -> int:
    total = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            usage = json.loads(line).get("usage") or {}
        except ValueError:
            continue
        total += int(usage.get("input_tokens") or 0)
        total += int(usage.get("output_tokens") or 0)
    return total


def _token_timeline(path: Path) -> list[tuple[float, int]]:
    """Return authoritative cumulative token usage keyed by record time."""
    cumulative = 0
    timeline = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            record = json.loads(line)
            recorded_at = float(record["recorded_at"])
            usage = record.get("usage") or {}
        except (KeyError, TypeError, ValueError):
            return []
        cumulative += int(usage.get("input_tokens") or 0)
        cumulative += int(usage.get("output_tokens") or 0)
        timeline.append((recorded_at, cumulative))
    return timeline


def _token_total_at(timeline: list[tuple[float, int]], timestamp: float) -> int:
    """Return cumulative token usage recorded no later than ``timestamp``."""
    total = 0
    for recorded_at, cumulative in timeline:
        if recorded_at > timestamp:
            break
        total = cumulative
    return total


def _duration(timing: dict[str, Any] | None) -> float:
    if not timing or not timing.get("started_at") or not timing.get("finished_at"):
        return 0.0
    start = datetime.fromisoformat(timing["started_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(timing["finished_at"].replace("Z", "+00:00"))
    return (end - start).total_seconds()


def _atomic_save(fig: Any, output: Path) -> None:
    temporary = output.with_suffix(".tmp.png")
    fig.savefig(temporary, dpi=160, bbox_inches="tight")
    os.replace(temporary, output)
