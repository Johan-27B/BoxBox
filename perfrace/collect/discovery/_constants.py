"""Constants for project Discovery runs."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils._constants import DEFAULT_TOKEN_FILE

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "discovery"
BOT_ACCOUNTS_PATH = Path(__file__).with_name("ai_bots.txt")
CLICKHOUSE_PLAY_URL = "https://play.clickhouse.com/?user=play"

logger = logging.getLogger("perfrace.discovery")

__all__ = [
    "BOT_ACCOUNTS_PATH",
    "CLICKHOUSE_PLAY_URL",
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_TOKEN_FILE",
    "REPO_ROOT",
    "logger",
]
