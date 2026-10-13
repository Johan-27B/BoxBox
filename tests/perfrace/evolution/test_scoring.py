import pytest

from perfrace.evolution.scoring import aggregate_run_summary
from perfrace.run.types import RunSummary


def test_aggregate_run_summary_uses_frozen_campaign_rules() -> None:
    summary = RunSummary.model_validate(
        {
            "job_name": "validation",
            "enable_cache": True,
            "used_api_gateway": True,
            "trial_count": 8,
            "tasks": [
                {
                    "task_name": "task-a",
                    "baseline": None,
                    "candidates": [
                        {
                            "trial_name": f"a-{index}",
                            "agent": "offline-harness",
                            "trial_uri": "file:///tmp/a",
                            "artifact": "a.json",
                            "reward": reward,
                        }
                        for index, reward in enumerate((2.0, 8.0, 4.0), start=1)
                    ],
                },
                {
                    "task_name": "task-b",
                    "baseline": None,
                    "candidates": [
                        {
                            "trial_name": f"b-{index}",
                            "agent": "offline-harness",
                            "trial_uri": "file:///tmp/b",
                            "artifact": "b.json",
                            "reward": reward,
                        }
                        for index, reward in enumerate((0.0, 0.5, 2.0), start=1)
                    ],
                },
            ],
        }
    )

    score = aggregate_run_summary(summary, expected_attempts=3)

    assert score.task_scores["task-a"] == pytest.approx(4.0)
    assert score.task_scores["task-b"] == pytest.approx(1.0)
    assert score.official_score == pytest.approx(1.6)
    assert score.raw_task_scores["task-b"] == 0.0
    assert score.raw_zero_sensitive_score == 0.0
