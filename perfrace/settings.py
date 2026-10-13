"""Local operator settings. Credentials are resolved from the environment at use time."""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any
import yaml


def expand_environment(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: expand_environment(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_environment(v) for v in value]
    if isinstance(value, str):

        def replacement(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(f"Required environment variable is not set: {name}")
            return os.environ[name]

        return re.sub(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}", replacement, value)
    return value


def settings() -> dict[str, Any]:
    path = os.environ.get("PERFRACE_SETTINGS")
    if not path:
        return {}
    data = yaml.safe_load(Path(path).expanduser().read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("Settings must be a YAML mapping")
    return expand_environment(data)


def configured_model(stage: str, explicit: str | None = None) -> str:
    value = explicit or settings().get("models", {}).get(stage)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Specify a model for {stage} in settings or with --model")
    return value


def endpoint() -> dict[str, str]:
    config = settings().get("api_gateway", {})
    url = config.get("base_url") or os.environ.get("LLM_BASE_URL")
    key = config.get("api_key") or os.environ.get("LLM_API_KEY")
    if not url or not key:
        raise ValueError("Configure api_gateway.base_url/api_key or LLM_BASE_URL/LLM_API_KEY")
    return {"base_url": url, "api_key": key}
