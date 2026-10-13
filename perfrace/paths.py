"""Shared filesystem locations for PerfRace instances."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTANCE_ROOT_ENV = "PERFRACE_INSTANCE_ROOT"


def resolve_instance_root(explicit: Path | None = None) -> Path:
    """Return the explicit, environment, or repository-default instance root."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    configured = os.environ.get(INSTANCE_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT.parent / "PerfRace-Bench"
