from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from perfrace.run.types import LlmPricingConfig, MeasurementConfig, PerfRaceConfig, Measurement


def _report(**overrides: object) -> Measurement:
    values = {
        "verdict": "ACCEPTED",
        "metric": "llm-tokens",
        "unit": "total_tokens",
        "value": 100,
    }
    values.update(overrides)
    return Measurement.model_validate(values)


def test_perf_trial_preserves_details() -> None:
    report = _report(details={"trials": [{"total_tokens": 100}]})

    assert report.model_dump(mode="json") == {
        "schema_version": 1,
        "verdict": "ACCEPTED",
        "metric": "llm-tokens",
        "unit": "total_tokens",
        "value": 100,
        "details": {"trials": [{"total_tokens": 100}]},
    }


def test_llm_pricing_estimates_cached_and_uncached_input_cost() -> None:
    pricing = LlmPricingConfig(
        input_usd_per_million_tokens=5.0,
        cached_input_usd_per_million_tokens=0.5,
        output_usd_per_million_tokens=30.0,
    )

    assert pricing.estimate_usd(
        input_tokens=1_000_000,
        cached_input_tokens=400_000,
        output_tokens=100_000,
    ) == pytest.approx(6.2)


def test_correct_trial_requires_value() -> None:
    with pytest.raises(ValidationError, match="ACCEPTED measurements must include value"):
        _report(value=None)


def test_incorrect_trial_allows_missing_value() -> None:
    report = _report(verdict="WRONG_ANSWER", value=None)

    assert report.value is None


def test_reward_against_minimize_baseline() -> None:
    assert _report(value=80).reward_against(_report(value=100), "minimize") == 1.25


def test_reward_against_maximize_baseline() -> None:
    baseline = _report(metric="throughput", unit="requests_per_second", value=100)
    candidate = _report(metric="throughput", unit="requests_per_second", value=125)

    assert candidate.reward_against(baseline, "maximize") == 1.25


def test_incorrect_candidate_reward_is_zero() -> None:
    reward = _report(verdict="WRONG_ANSWER", value=None).reward_against(
        _report(value=100), "minimize"
    )

    assert reward == 0.0


def test_reward_against_rejects_mismatched_metric() -> None:
    with pytest.raises(ValueError, match="metric mismatch"):
        _report(metric="wall-clock", unit="seconds", value=80).reward_against(
            _report(value=100),
            "minimize",
        )


def test_reward_against_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="positive measurement values"):
        _report(value=0).reward_against(_report(value=100), "minimize")


def test_measurement_config_accepts_machine_readable_metadata() -> None:
    measurement = MeasurementConfig.model_validate(
        {
            "measurement": "wall-clock",
            "direction": "minimize",
            "workload": "visible-suite",
            "unit": "seconds",
            "n_warmup": 1,
            "n_repetitions": 3,
        }
    )

    assert measurement.direction == "minimize"
    assert measurement.n_repetitions == 3


def test_perfrace_config_loads_measurement_and_llm_from_task_toml(tmp_path) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """
[perfrace.measurement]
measurement = "llm-tokens"
unit = "total_tokens"
direction = "minimize"

[perfrace.llm]
model = "gpt-5.5"
"""
    )

    config = PerfRaceConfig.from_task_dir(task_dir)

    assert config is not None
    assert config.measurement is not None
    assert config.measurement.measurement == "llm-tokens"
    assert config.llm is not None
    assert config.llm.model == "gpt-5.5"
    assert config.requires_llm_token_proxy is True


def test_perfrace_config_loads_llm_cost_pricing(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """
[perfrace.measurement]
measurement = "llm-cost"
unit = "USD"
direction = "minimize"

[perfrace.llm]
model = "gpt-5.5"

[perfrace.llm.pricing]
currency = "USD"
input_usd_per_million_tokens = 5.0
cached_input_usd_per_million_tokens = 0.5
output_usd_per_million_tokens = 30.0
"""
    )

    config = PerfRaceConfig.from_task_dir(task_dir)

    assert config is not None
    assert config.llm is not None
    assert config.llm.pricing is not None
    assert config.requires_llm_token_proxy is True


def test_perfrace_config_tolerates_unrelated_top_level_perfrace_tables(tmp_path) -> None:
    """Validate measurement and LLM sub-tables independently of unrelated metadata."""
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """
[perfrace]
task_id = "task-a"
title = "Some title"

[perfrace.tags]
source = "upstream-pin"

[perfrace.measurement]
measurement = "wall-clock"
unit = "seconds"
direction = "minimize"
"""
    )

    config = PerfRaceConfig.from_task_dir(task_dir)

    assert config is not None
    assert config.measurement is not None
    assert config.measurement.direction == "minimize"


def test_perfrace_config_returns_none_for_missing_task_toml(tmp_path) -> None:
    assert PerfRaceConfig.from_task_dir(tmp_path / "missing") is None


def test_perfrace_config_task_identity_from_task_table(tmp_path) -> None:
    task_dir = tmp_path / "some-dir-name"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """
[task]
name = "perfrace/some-dir-name"

[perfrace.measurement]
measurement = "wall-clock"
unit = "seconds"
direction = "minimize"
"""
    )

    config = PerfRaceConfig.from_task_dir(task_dir)

    assert config is not None
    assert config.task_name == "perfrace/some-dir-name"
    assert config.instance_id == "some-dir-name"


def test_perfrace_config_task_identity_falls_back_to_directory_name(tmp_path) -> None:
    task_dir = tmp_path / "some-dir-name"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """
[perfrace.measurement]
measurement = "wall-clock"
unit = "seconds"
direction = "minimize"
"""
    )

    config = PerfRaceConfig.from_task_dir(task_dir)

    assert config is not None
    assert config.task_name == "some-dir-name"
    assert config.instance_id == "some-dir-name"


def test_perfrace_config_cache_fields_requires_checksum_and_unit(tmp_path) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """
[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
"""
    )

    without_checksum = PerfRaceConfig.from_task_dir(task_dir)
    assert without_checksum is not None
    assert without_checksum.cache_fields is None  # no include_checksum, and unit is missing

    with_checksum = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert with_checksum is not None
    assert with_checksum.cache_fields is None  # still no unit
