from __future__ import annotations

from pathlib import Path

from perfrace.run.cache import (
    baseline_cache_key,
    baseline_cache_root,
    read_baseline_trial,
    write_baseline_trial,
)
from perfrace.run.types import Measurement


def test_baseline_cache_key_digest_is_stable() -> None:
    fields = {
        "instance_id": "terminus-kira--demo",
        "task_checksum": "abc",
        "metric": "llm-tokens",
        "unit": "total_tokens",
        "direction": "minimize",
        "llm_model": "gpt-5.5",
        "trial_schema_version": 1,
        "runner_version": "0.1",
    }

    assert baseline_cache_key(fields) == baseline_cache_key(fields)
    assert len(baseline_cache_key(fields)) == 64


def test_baseline_cache_root_uses_jobs_dir() -> None:
    assert baseline_cache_root(Path("data/jobs")) == Path("data/jobs/.cache/baselines")


def test_writes_and_reads_baseline_trial(tmp_path: Path) -> None:
    trial = Measurement(
        verdict="ACCEPTED",
        metric="llm-tokens",
        unit="total_tokens",
        value=11,
        details={"trials": [{"total_tokens": 10}, {"total_tokens": 12}]},
    )

    path = write_baseline_trial(tmp_path, "terminus-kira--demo", "abc", trial)
    loaded = read_baseline_trial(tmp_path, "terminus-kira--demo", "abc")

    assert path.exists()
    assert loaded == trial
