"""Persistence helpers for PerfRace baseline trial artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from perfrace.run.types import Measurement

__all__ = [
    "baseline_cache_key",
    "baseline_cache_root",
    "baseline_trial_path",
    "read_baseline_trial",
    "write_baseline_trial",
]


def baseline_cache_root(jobs_dir: Path) -> Path:
    return jobs_dir / ".cache" / "baselines"


def baseline_cache_key(fields: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(fields), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def baseline_trial_path(cache_root: Path, instance_id: str, cache_key: str) -> Path:
    safe_instance = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in instance_id)
    return cache_root / safe_instance / f"{cache_key}.measurement.json"


def write_baseline_trial(
    cache_root: Path,
    instance_id: str,
    cache_key: str,
    trial: Measurement,
) -> Path:
    path = baseline_trial_path(cache_root, instance_id, cache_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trial.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_baseline_trial(
    cache_root: Path,
    instance_id: str,
    cache_key: str,
) -> Measurement | None:
    path = baseline_trial_path(cache_root, instance_id, cache_key)
    if not path.exists():
        return None
    return Measurement.model_validate_json(path.read_text(encoding="utf-8"))
