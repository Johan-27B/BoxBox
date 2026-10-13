"""Frozen campaign aggregation for harness generations."""

from __future__ import annotations

import math
from collections.abc import Iterable

from perfrace.evolution.types import AggregateScore
from perfrace.run.types import RunSummary


def select_agent_summary(summary: RunSummary, agent_name: str) -> RunSummary:
    """Project one multi-agent run onto a single candidate identity."""
    tasks = [
        task.model_copy(
            update={
                "candidates": [
                    candidate for candidate in task.candidates if candidate.agent == agent_name
                ]
            }
        )
        for task in summary.tasks
    ]
    return summary.model_copy(
        update={
            "trial_count": sum(
                (1 if task.baseline is not None else 0) + len(task.candidates) for task in tasks
            ),
            "tasks": tasks,
        }
    )


def aggregate_run_summary(
    summary: RunSummary,
    *,
    expected_attempts: int,
) -> AggregateScore:
    """Aggregate one single-agent run using the frozen campaign protocol."""
    if expected_attempts < 1:
        raise ValueError("expected_attempts must be positive")
    attempt_rewards: dict[str, tuple[float, ...]] = {}
    task_scores: dict[str, float] = {}
    raw_task_scores: dict[str, float] = {}
    for task in summary.tasks:
        if len(task.candidates) != expected_attempts:
            raise ValueError(
                f"Task {task.task_name} has {len(task.candidates)} candidate attempts; "
                f"expected {expected_attempts}"
            )
        rewards: list[float] = []
        for candidate in task.candidates:
            if candidate.reward is None:
                raise ValueError(
                    f"Task {task.task_name} trial {candidate.trial_name} has no reward"
                )
            if candidate.reward < 0:
                raise ValueError(
                    f"Task {task.task_name} trial {candidate.trial_name} has negative reward"
                )
            rewards.append(candidate.reward)
        raw = tuple(rewards)
        effective = tuple(1.0 if reward == 0 else reward for reward in raw)
        attempt_rewards[task.task_name] = raw
        task_scores[task.task_name] = _geometric_mean(effective)
        raw_task_scores[task.task_name] = (
            0.0 if any(reward == 0 for reward in raw) else _geometric_mean(raw)
        )

    official_score = _harmonic_mean(task_scores.values())
    raw_zero_sensitive_score = (
        0.0
        if any(score == 0 for score in raw_task_scores.values())
        else _harmonic_mean(raw_task_scores.values())
    )
    return AggregateScore(
        official_score=official_score,
        raw_zero_sensitive_score=raw_zero_sensitive_score,
        task_scores=task_scores,
        raw_task_scores=raw_task_scores,
        attempt_rewards=attempt_rewards,
    )


def _geometric_mean(values: Iterable[float]) -> float:
    """Return the geometric mean of positive values."""
    items = tuple(values)
    if not items or any(value <= 0 for value in items):
        raise ValueError("geometric mean requires non-empty positive values")
    return math.exp(math.fsum(math.log(value) for value in items) / len(items))


def _harmonic_mean(values: Iterable[float]) -> float:
    """Return the harmonic mean of positive values."""
    items = tuple(values)
    if not items or any(value <= 0 for value in items):
        raise ValueError("harmonic mean requires non-empty positive values")
    return len(items) / math.fsum(1.0 / value for value in items)
