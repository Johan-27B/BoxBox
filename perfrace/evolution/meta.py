"""Shared connection settings for offline meta-agent calls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from perfrace.run.services.session_identity import token_proxy_api_key


@dataclass(frozen=True)
class MetaAgentEndpoint:
    """Experiment-scoped LLM endpoint used by debugger and evolve agents."""

    base_url: str
    token_proxy_secret: str
    model: str
    reasoning_effort: str
    session_prefix: str
    fixed_api_key: str | None = None

    def api_key_for(self, session_id: str) -> str:
        """Return the signed token-proxy identity for one meta-agent session."""
        if self.fixed_api_key is not None:
            return self.fixed_api_key
        return token_proxy_api_key(
            session_id,
            self.model,
            secret=self.token_proxy_secret,
        )


def rotate_failed_output(path: Path) -> Path:
    """Preserve one incomplete meta-agent output directory for retry."""
    index = 1
    while True:
        destination = path.with_name(f"{path.name}-failed-{index:02d}")
        if not destination.exists():
            path.rename(destination)
            return destination
        index += 1
