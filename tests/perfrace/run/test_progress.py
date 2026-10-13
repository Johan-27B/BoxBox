from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from perfrace.run.progress import (
    _AVERAGE_TOKEN_AXIS,
    _Point,
    _Series,
    _aggregate_average_token_curve,
    _expected_candidate_attempts,
    _token_timeline,
    _token_total_at,
)


def _write_task(path: Path, name: str) -> None:
    path.mkdir()
    (path / "task.toml").write_text(
        "\n".join(
            [
                "[task]",
                f'name = "perfrace/{name}"',
                "",
                "[perfrace.measurement]",
                'measurement = "wall-clock"',
                'direction = "minimize"',
                'unit = "seconds"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_measurement(path: Path, value: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "verdict": "ACCEPTED",
                "metric": "wall-clock",
                "unit": "seconds",
                "value": value,
            }
        ),
        encoding="utf-8",
    )


def test_average_token_curve_uses_configured_attempt_denominator() -> None:
    time_grouped = {
        "task-a": [
            _Series("task-a", "a1", (_Point(1.0, 2.0),)),
            _Series("task-a", "a2", (_Point(2.0, 4.0),)),
        ],
        "task-b": [
            _Series("task-b", "b1", (_Point(1.0, 1.0),)),
            _Series("task-b", "b2", (_Point(3.0, 2.0),)),
        ],
    }
    token_grouped = {
        "task-a": [
            _Series("task-a", "a1", (_Point(10.0, 2.0),)),
            _Series("task-a", "a2", (_Point(20.0, 4.0),)),
        ],
        "task-b": [
            _Series("task-b", "b1", (_Point(5.0, 1.0),)),
            _Series("task-b", "b2", (_Point(15.0, 2.0),)),
        ],
    }

    tokens, speedups = _aggregate_average_token_curve(
        time_grouped,
        token_grouped,
        expected_instances=("task-a", "task-b"),
        expected_attempts=4,
    )

    assert tokens == [0.0, 3.75, 8.75, 12.5]
    assert speedups == pytest.approx(
        [
            1.0,
            2 / (1 / math.sqrt(2) + 1),
            2 / (1 / math.sqrt(8) + 1),
            2 / (1 / math.sqrt(8) + 1 / math.sqrt(2)),
        ]
    )


def test_expected_candidate_attempts_uses_resolved_job_config(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "n_attempts": 3,
                "agents": [
                    {"name": "nop", "scale_with_attempts": False},
                    {"name": "candidate-a"},
                    {"name": "candidate-b", "scale_with_attempts": False},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _expected_candidate_attempts(tmp_path, instance_count=4) == 16


def test_token_timeline_tracks_authoritative_usage_by_time(tmp_path: Path) -> None:
    audit = tmp_path / "trial__agent.jsonl"
    audit.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "recorded_at": 10.0,
                        "usage": {"input_tokens": 7, "output_tokens": 3},
                    }
                ),
                json.dumps(
                    {
                        "recorded_at": 20.0,
                        "usage": {"input_tokens": 11, "output_tokens": 4},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    timeline = _token_timeline(audit)

    assert timeline == [(10.0, 10), (20.0, 25)]
    assert _token_total_at(timeline, 9.0) == 0
    assert _token_total_at(timeline, 10.0) == 10
    assert _token_total_at(timeline, 19.0) == 10
    assert _token_total_at(timeline, 20.0) == 25
