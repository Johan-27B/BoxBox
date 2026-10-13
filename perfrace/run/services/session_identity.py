"""Self-describing, signed session identity tokens shared by every
PerfRace host-side service.

A "session" here is a repetition of PerfRace's abstract measurement unit
that specifically invokes an LLM agent, and therefore needs its own
token-proxy identity to track its usage. One trial
mints one session identity for its own primary container
(``perfrace.run.services.gateway`` uses it to sign that trial's
``LLM_API_KEY``); a trial that fans out into concurrent shadow containers
mints one additional, independent session identity per shadow, so each
shadow's own LLM usage is tracked in isolation.

These four functions are pure and stateless -- no server, no mutable
registry -- so any host-side service can import them without depending on
another. A session identity is entirely self-describing: ``session_id``
(and ``model``) are encoded directly into the signed token, verified
against a shared per-run secret on decode, with no prior registration step
required to mint or verify an arbitrary new ``session_id``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_API_KEY_PREFIX = "sk-token-proxy-"


def generate_token_proxy_secret() -> str:
    """Generate a fresh per-run signing secret for session identity tokens.

    Called once when a run's host-side services start. The same secret is
    handed to every service that needs to mint or verify a session identity
    (the token proxy, and any shadow-container fan-out) — as a plain
    string, it travels safely through ``VerifierConfig.kwargs`` and
    Harbor's own JSON job-config persistence, unlike a live server/state
    object reference.
    """
    return secrets.token_hex(32)


def token_proxy_api_key(session_id: str, model: str, *, secret: str) -> str:
    """Build a self-describing, signed identity token for one session.

    The token encodes ``session_id`` and ``model`` directly (base64) plus
    an HMAC-SHA256 signature over that payload. Any consumer verifies and
    decodes it on each incoming request with no prior registration step —
    there is no shared mutable session/model registry to keep in sync
    between the minter and the verifying service.
    """
    payload = f"{session_id}:{model}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    signature = _sign_token_payload(payload, secret=secret)
    return f"{_API_KEY_PREFIX}{payload_b64}.{signature}"


def decode_token_proxy_api_key(api_key: str | None, *, secret: str) -> tuple[str, str] | None:
    """Decode and verify a signed identity token, returning ``(session_id, model)``.

    Returns ``None`` for anything malformed, unsigned, or signed with a
    different secret, rather than raising — callers treat this the same as
    "no session found for this request".
    """
    if api_key is None or not api_key.startswith(_API_KEY_PREFIX):
        return None
    body = api_key[len(_API_KEY_PREFIX) :]
    payload_b64, separator, signature = body.partition(".")
    if not separator:
        return None
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    session_id, separator, model = payload.partition(":")
    if not separator:
        return None
    if not hmac.compare_digest(signature, _sign_token_payload(payload, secret=secret)):
        return None
    return session_id, model


def _sign_token_payload(payload: str, *, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[
        :32
    ]
