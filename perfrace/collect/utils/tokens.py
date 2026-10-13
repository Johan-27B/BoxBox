"""GitHub credentials and a rate-limit-aware pool for PerfRace collectors.

Loads owner-only token files and tracks REST and Search limits independently,
with per-token pacing and cooldown. Token values are excluded from object
representations and module log messages.

Token-pool design adapted from Datasmith's ``utils.tokens`` module.
"""

from __future__ import annotations

import json
import random
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from ._constants import (
    DEFAULT_TOKEN_FILE,
    GITHUB_API,
    PERFRACE_GITHUB_COOLDOWN_JITTER_S,
    PERFRACE_GITHUB_COOLDOWN_S,
    PERFRACE_GITHUB_HEALTH_TIMEOUT_S,
    PERFRACE_GITHUB_POLITE_PER_MIN,
    USER_AGENT,
    logger,
)


@dataclass(frozen=True)
class Token:
    """A GitHub credential with optional metadata.

    The ``value`` field is the actual secret. It is never logged or
    printed by this module: ``__repr__`` and ``__str__`` are overridden
    so debuggers, loggers, and traceback formatters cannot leak it.

    ``label``/``type``/``notes`` are free-form metadata read from the
    token JSON file. They're safe to log.
    """

    value: str
    label: str | None = None
    type: str | None = None
    notes: str | None = None

    def __repr__(self) -> str:
        return f"Token(label={self.label!r}, type={self.type!r})"

    def __str__(self) -> str:
        return repr(self)


def load_tokens(path: Path = DEFAULT_TOKEN_FILE) -> list[Token]:
    """Load tokens from a JSON file (schema version 1).

    Schema::

        {
          "version": 1,
          "tokens": [
            {"value": "ghp_...", "label": "...", "type": "...", "notes": "..."}
          ]
        }

    Raises
    ------
    FileNotFoundError
        if ``path`` does not exist.
    PermissionError
        if the file mode allows group or other read/write/exec —
        plaintext secrets must be owner-only.
    ValueError
        if the schema version is unrecognised, the token list is
        empty, or any entry is missing ``value``.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Token file not found: {path}. Run `perfrace discover convert-tokens` to generate it."
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(
            f"Refusing to load {path}: file mode 0o{mode:03o} is too "
            f"permissive. Run `chmod 600 {path}` so only the owner can "
            f"read it."
        )
    data = json.loads(path.read_text())
    version = data.get("version")
    if version != 1:
        raise ValueError(f"Unsupported token schema version: {version!r} (expected 1)")
    raw = data.get("tokens")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path} must contain a non-empty 'tokens' array")
    tokens: list[Token] = []
    for i, t in enumerate(raw):
        if not isinstance(t, dict) or "value" not in t:
            raise ValueError(f"{path} token #{i}: missing 'value'")
        tokens.append(
            Token(
                value=t["value"],
                label=t.get("label"),
                type=t.get("type"),
                notes=t.get("notes"),
            )
        )
    return tokens


@dataclass
class _Bucket:
    """One GitHub rate-limit bucket (e.g. REST core or Search)."""

    remaining: int
    reset_at: float

    def is_exhausted(self, now: float) -> bool:
        # When the reset window has passed, optimistically treat the
        # bucket as available; the next response will refresh state.
        return self.remaining <= 0 and now < self.reset_at


@dataclass
class _TokenState:
    """Per-token limits, cooldown, pacing, and health-check state."""

    core: _Bucket = field(default_factory=lambda: _Bucket(5000, 0.0))
    search: _Bucket = field(default_factory=lambda: _Bucket(30, 0.0))
    cooldown_until: float = 0.0  # set by secondary rate-limit response
    last_used: float = 0.0  # for polite pacing
    valid: bool = True  # set False if health-check fails


class TokenPool:
    """Thread-safe GitHub credential pool with rate-limit awareness.

    Adapted from ``datasmith.utils.tokens.TokenPool``. Tracks REST and Search
    buckets separately, staggers cooldowns, and checks token health at startup.

    Callers acquire a token, make a request, and report the response::

        idx, tok = pool.acquire_blocking("search")
        resp = requests.get(url, headers=pool.auth_headers(tok), ...)
        pool.report_response(idx, resp, "search")
    """

    def __init__(
        self,
        tokens: list[Token],
        polite_per_min: int = PERFRACE_GITHUB_POLITE_PER_MIN,
    ) -> None:
        if not tokens:
            raise ValueError("TokenPool needs at least one token")
        self._tokens = tokens
        self._state = [_TokenState() for _ in tokens]
        self._lock = threading.Lock()
        self._idx = 0
        self._min_interval = 60.0 / max(polite_per_min, 1)

    # -- public read-only views ---------------------------------------------

    @property
    def size(self) -> int:
        return len(self._tokens)

    @property
    def valid_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._state if s.valid)

    def label(self, index: int) -> str:
        """Return the token label for log messages, or ``'#N'`` fallback."""
        t = self._tokens[index]
        return t.label or f"#{index}"

    def status_summary(self) -> list[dict[str, object]]:
        """Per-token state suitable for logging. Token values omitted."""
        now = time.time()
        with self._lock:
            return [
                {
                    "index": i,
                    "label": self._tokens[i].label,
                    "valid": s.valid,
                    "core_remaining": s.core.remaining,
                    "core_reset_in_s": max(0, int(s.core.reset_at - now)),
                    "search_remaining": s.search.remaining,
                    "search_reset_in_s": max(0, int(s.search.reset_at - now)),
                    "cooldown_in_s": max(0, int(s.cooldown_until - now)),
                }
                for i, s in enumerate(self._state)
            ]

    # -- health check --------------------------------------------------------

    def health_check(self) -> tuple[int, int]:
        """Validate every token via ``GET /rate_limit``.

        ``/rate_limit`` does *not* consume budget itself (per GitHub
        docs), so calling it once per token at startup is free. Tokens
        whose call fails are marked ``valid=False`` and skipped by
        future ``acquire`` calls. Token values are never printed.

        Returns ``(valid_count, total_count)``.
        """
        for i, token in enumerate(self._tokens):
            label = self.label(i)
            try:
                r = requests.get(
                    f"{GITHUB_API}/rate_limit",
                    headers=self._auth_headers(token.value),
                    timeout=PERFRACE_GITHUB_HEALTH_TIMEOUT_S,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "token %s: health-check network error: %s",
                    label,
                    type(exc).__name__,
                )
                with self._lock:
                    self._state[i].valid = False
                continue
            if r.status_code != 200:
                logger.warning(
                    "token %s: health-check returned HTTP %d; marking invalid",
                    label,
                    r.status_code,
                )
                with self._lock:
                    self._state[i].valid = False
                continue
            data = r.json().get("resources", {})
            now = time.time()
            core = data.get("core", {})
            search = data.get("search", {})
            with self._lock:
                self._state[i].core.remaining = int(core.get("remaining", 5000))
                self._state[i].core.reset_at = float(core.get("reset", now + 3600))
                self._state[i].search.remaining = int(search.get("remaining", 30))
                self._state[i].search.reset_at = float(search.get("reset", now + 60))
        return self.valid_count, self.size

    # -- acquisition ---------------------------------------------------------

    def acquire(self, endpoint: str) -> tuple[int, Token] | None:
        """Return ``(index, token)`` for the next usable token.

        ``endpoint`` must be ``"search"`` or ``"rest"``. Skips tokens
        that are invalid, in cooldown, with the requested bucket
        exhausted, or with the polite interval since last use not yet
        elapsed. Returns ``None`` if none meet the criteria right now.
        """
        if endpoint not in ("search", "rest"):
            raise ValueError(f"endpoint must be 'search' or 'rest', got {endpoint!r}")
        now = time.time()
        with self._lock:
            n = self.size
            for offset in range(n):
                i = (self._idx + offset) % n
                s = self._state[i]
                if not s.valid:
                    continue
                if now < s.cooldown_until:
                    continue
                bucket = s.search if endpoint == "search" else s.core
                if bucket.is_exhausted(now):
                    continue
                if now - s.last_used < self._min_interval:
                    continue
                self._idx = (i + 1) % n
                s.last_used = now
                return i, self._tokens[i]
        return None

    def acquire_blocking(
        self,
        endpoint: str,
        max_wait_s: float = 300.0,
    ) -> tuple[int, Token]:
        """Block until a token is available, or raise after ``max_wait_s``."""
        start = time.time()
        while True:
            slot = self.acquire(endpoint)
            if slot is not None:
                return slot
            if time.time() - start > max_wait_s:
                raise RuntimeError(
                    f"No token available after {max_wait_s:.0f}s. "
                    f"Pool may be exhausted or all in cooldown."
                )
            time.sleep(min(2.0, self._min_interval))

    # -- feedback ------------------------------------------------------------

    def report_response(
        self,
        index: int,
        response: requests.Response,
        endpoint: str,
    ) -> None:
        """Update per-token state from a response's rate-limit headers.

        Also imposes a cooldown when the response is 403 (treated as
        the secondary, undocumented rate limit).
        """
        if endpoint not in ("search", "rest"):
            raise ValueError(f"endpoint must be 'search' or 'rest', got {endpoint!r}")
        h = response.headers
        try:
            remaining = int(h.get("X-RateLimit-Remaining", "0"))
            reset = float(h.get("X-RateLimit-Reset", time.time() + 60))
        except ValueError:
            remaining, reset = 0, time.time() + 60
        with self._lock:
            s = self._state[index]
            if endpoint == "search":
                s.search.remaining = remaining
                s.search.reset_at = reset
            else:
                s.core.remaining = remaining
                s.core.reset_at = reset
            if response.status_code == 403:
                # Stagger retries to avoid a synchronised storm.
                cooldown = PERFRACE_GITHUB_COOLDOWN_S + random.uniform(
                    0, PERFRACE_GITHUB_COOLDOWN_JITTER_S
                )
                s.cooldown_until = time.time() + cooldown
                logger.warning(
                    "token %s: HTTP 403 (likely secondary rate limit); cooldown %.0fs",
                    self.label(index),
                    cooldown,
                )

    # -- auth helpers --------------------------------------------------------

    def auth_headers(self, token: Token) -> dict[str, str]:
        """Build request headers signed with ``token.value``."""
        return self._auth_headers(token.value)

    @staticmethod
    def _auth_headers(token_value: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token_value}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
