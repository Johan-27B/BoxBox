"""Shared constants and tunable knobs for ``perfrace.collect.utils``.

All tunables are prefixed ``PERFRACE_GITHUB_`` and can be overridden
via environment variables without a code change. They control
behaviour shared across every PerfRace collector that hits the
GitHub API.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Three levels up: perfrace/collect/utils/_constants.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TOKEN_FILE = REPO_ROOT / "config" / "tokens.json"

GITHUB_API = "https://api.github.com"
USER_AGENT = "perfrace-collect/0.1 (PerfRace research)"

# Tunables shared by every collector. Override via env var.
PERFRACE_GITHUB_POLITE_PER_MIN: int = int(os.environ.get("PERFRACE_GITHUB_POLITE_PER_MIN", "10"))
PERFRACE_GITHUB_COOLDOWN_S: float = float(os.environ.get("PERFRACE_GITHUB_COOLDOWN_S", "60"))
PERFRACE_GITHUB_COOLDOWN_JITTER_S: float = float(
    os.environ.get("PERFRACE_GITHUB_COOLDOWN_JITTER_S", "30")
)
PERFRACE_GITHUB_HEALTH_TIMEOUT_S: float = float(
    os.environ.get("PERFRACE_GITHUB_HEALTH_TIMEOUT_S", "15")
)

logger = logging.getLogger("perfrace.collect.utils.tokens")
