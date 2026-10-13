"""Host-side non-streaming OpenAI-compatible token proxy.

The token proxy is a transparent forwarding and audit layer for target-agent LLM
traffic inside PerfRace trials::

    container target agent
        -> PerfRace token proxy
        -> upstream LLM gateway/provider

Target agents see a normal OpenAI-compatible endpoint and authenticate with a
trial/session API key injected by the PerfRace verifier::

    LLM_BASE_URL = http://host.docker.internal:<proxy-port>/v1
    LLM_API_KEY  = <trial-specific token proxy key>
    LLM_MODEL    = <resolved instance model>

The proxy has two surfaces:

1. Data plane for target agents: non-streaming ``/v1/chat/completions`` and
   ``/v1/responses`` requests are forwarded to ``api_gateway.base_url`` using the
   upstream gateway credential. Responses are returned unchanged except that the
   proxy records usage metadata from the response JSON.
2. Control plane for PerfRace: session-scoped ``/sessions/<id>/reset`` and
    ``/sessions/<id>/summary`` endpoints let the verifier reset counters before
    a workload run and read audited token usage afterwards.

Accounting is isolated by API key. ``TokenProxyState`` maps each injected
trial/session key to a session id, then stores token counters and request logs
under that session. Multiple Harbor trials in the same PerfRace run can share
one host-side proxy process without mixing token usage.

The upstream LLM gateway is separate from this proxy. It owns provider-specific
behavior such as API routing, model aliases, and credential
refresh. ``start_gateway`` is a small convenience context manager for launching
that upstream gateway command for a run before the token proxy forwards traffic
to it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import subprocess
import threading
import time
import tomllib
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Generator
from urllib.parse import urlparse

from perfrace.run.config import ApiGatewayConfig
from perfrace.run.services.session_identity import (
    decode_token_proxy_api_key,
    generate_token_proxy_secret,
    token_proxy_api_key,
)

__all__ = [
    "decode_token_proxy_api_key",
    "generate_token_proxy_secret",
    "read_token_proxy_summary",
    "token_proxy_api_key",
]


logger = logging.getLogger(__name__)

# Keep request logs in a separate file so background HTTP threads do not
# interfere with Harbor's terminal progress display. Lifecycle events use logger.
_REQUEST_LOG_NAME = f"{__name__}.requests"
request_logger = logging.getLogger(_REQUEST_LOG_NAME)
request_logger.propagate = False
request_logger.setLevel(logging.INFO)


async def read_token_proxy_summary(
    host_base_url: str,
    session_id: str,
) -> dict[str, Any]:
    """Read one session's audited usage from the host-only token proxy."""
    url = f"{host_base_url.rstrip('/')}/sessions/{session_id}/summary"

    def read() -> dict[str, Any]:
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            json.JSONDecodeError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
        ) as exc:
            raise TokenProxyServiceError(
                f"failed to read token-proxy summary for {session_id}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise TokenProxyServiceError(f"token-proxy summary for {session_id} is not an object")
        return payload

    return await asyncio.to_thread(read)


def _configure_request_logger(log_dir: Path) -> None:
    """Attach a file handler for `request_logger`, once per process.

    Safe to call more than once (e.g. if `create_server` is ever called
    again in the same process) -- only adds a handler the first time.
    """
    if request_logger.handlers:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "token-proxy-requests.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    request_logger.addHandler(handler)


class TokenProxyServiceError(RuntimeError):
    """Raised when a token-proxy-adjacent host service cannot be used."""


@contextmanager
def start_gateway(gateway: ApiGatewayConfig | None) -> Generator[None, None, None]:
    """Start a configured gateway command and wait for its resolved healthcheck.

    ``ApiGatewayConfig`` substitutes its explicit port reference before the
    command is tokenized, so this service has no proxy-specific environment
    variable or command-argument contract.
    """
    process: subprocess.Popen | None = None
    try:
        command = gateway.resolved_command() if gateway is not None else None
        if command is not None:
            logger.info("Starting LLM gateway command: %s", command)
            process = subprocess.Popen(shlex.split(command))
        healthcheck = gateway.resolved_healthcheck() if gateway is not None else None
        if healthcheck:
            logger.info("Waiting for LLM gateway healthcheck: %s", healthcheck)
            _wait_for_healthcheck(healthcheck, process)
            logger.info("LLM gateway healthcheck passed: %s", healthcheck)
        yield
    finally:
        if process is not None and process.poll() is None:
            logger.info("Stopping LLM gateway command")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("LLM gateway did not stop after terminate; killing process")
                process.kill()
                process.wait(timeout=5)


def _wait_for_healthcheck(
    healthcheck: str,
    process: subprocess.Popen | None,
    *,
    ready_timeout_sec: float = 30.0,
    poll_interval_sec: float = 1.0,
) -> None:
    deadline = time.monotonic() + ready_timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            logger.error(
                "LLM gateway command exited before healthcheck passed: code=%s",
                process.returncode,
            )
            raise TokenProxyServiceError(
                f"api_gateway.command exited before healthcheck passed (code={process.returncode})"
            )
        try:
            with urllib.request.urlopen(healthcheck, timeout=5) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(poll_interval_sec)

    logger.error("LLM gateway healthcheck timed out: %s", healthcheck)
    raise TokenProxyServiceError(
        f"api_gateway healthcheck did not pass at {healthcheck} within {ready_timeout_sec}s"
    ) from last_error


@dataclass
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    models: set[str] = field(default_factory=set)

    def add(self, model: str, usage: dict[str, Any]) -> None:
        input_tokens = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("input_token_count")
            or 0
        )
        cached_input_tokens = _cached_input_tokens(usage)
        output_tokens = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("output_token_count")
            or 0
        )
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

        self.input_tokens += input_tokens
        self.cached_input_tokens += cached_input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        self.requests += 1
        self.models.add(model)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
            "models": sorted(self.models),
        }


class TokenProxyState:
    def __init__(
        self,
        *,
        upstream_base_url: str,
        upstream_api_key: str | None,
        log_dir: Path,
        secret: str,
    ):
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        self._usage: dict[str, TokenUsage] = {}
        self._lock = threading.Lock()

    def session_for_api_key(self, api_key: str | None) -> str | None:
        decoded = decode_token_proxy_api_key(api_key, secret=self.secret)
        return decoded[0] if decoded is not None else None

    def model_for_api_key(self, api_key: str | None) -> str | None:
        decoded = decode_token_proxy_api_key(api_key, secret=self.secret)
        return decoded[1] if decoded is not None else None

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._usage[session_id] = TokenUsage()
            self._log_path(session_id).write_text("")
        # Counter resets use the file-only request log.
        request_logger.info("Reset token proxy session: session=%s", session_id)

    def summary(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            usage = self._usage.setdefault(session_id, TokenUsage())
            data = usage.to_json_dict()
            data["session_id"] = session_id
            data["log_path"] = str(self._log_path(session_id))
            data["model"] = _single_model(usage.models)
            data["cost_usd"] = estimate_cost_usd(data["model"], usage)
            request_logger.info(
                "Summarized token proxy session: session=%s requests=%s total_tokens=%s model=%s",
                session_id,
                data["requests"],
                data["total_tokens"],
                data["model"],
            )
            return data

    def record(
        self,
        session_id: str,
        model: str,
        request_body: dict[str, Any],
        response_body: dict[str, Any],
    ) -> None:
        usage = response_body.get("usage") or {}
        with self._lock:
            aggregate = self._usage.setdefault(session_id, TokenUsage())
            aggregate.add(model, usage)
            record = {
                "session_id": session_id,
                "model": model,
                "usage": usage,
                "request_model": request_body.get("model"),
                "recorded_at": time.time(),
            }
            with self._log_path(session_id).open("a") as f:
                f.write(json.dumps(record, sort_keys=True) + "\n")
            # Record each model call in the file-only request log.
            request_logger.info(
                "Recorded token proxy usage: session=%s model=%s total_tokens=%s requests=%s",
                session_id,
                model,
                aggregate.total_tokens,
                aggregate.requests,
            )

    def _log_path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in session_id)
        return self.log_dir / f"{safe}.jsonl"


def make_handler(state: TokenProxyState) -> type[BaseHTTPRequestHandler]:
    class TokenProxyHandler(BaseHTTPRequestHandler):
        server_version = "PerfRaceTokenProxy/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = _request_session_and_suffix(state, self.path, self.headers)
            if not parsed or not _is_summary_suffix(parsed[1]):
                self._send_json(404, {"error": "not found"})
                return
            request_logger.info("Token proxy summary request: session=%s", parsed[0])
            self._send_json(200, state.summary(parsed[0]))

        def do_POST(self) -> None:  # noqa: N802
            parsed = _request_session_and_suffix(state, self.path, self.headers)
            if not parsed:
                self._send_json(404, {"error": "not found"})
                return

            session_id, suffix = parsed
            if _is_reset_suffix(suffix):
                request_logger.info("Token proxy reset request: session=%s", session_id)
                state.reset(session_id)
                self._send_json(200, {"ok": True, "session_id": session_id})
                return

            if not suffix.startswith("v1/"):
                self._send_json(404, {"error": "not found"})
                return

            body = self._read_json()
            if body.get("stream") is True:
                logger.warning("Rejected streaming request: session=%s", session_id)
                self._send_json(
                    400,
                    {"error": "Streaming is disabled for PerfRace token-proxy runs"},
                )
                return

            model = str(body.get("model") or "")
            allowed_model = state.model_for_api_key(_bearer_token(self.headers))
            if allowed_model and model != allowed_model:
                logger.warning(
                    "Rejected token proxy model: session=%s model=%s allowed_model=%s",
                    session_id,
                    model,
                    allowed_model,
                )
                self._send_json(
                    403,
                    {
                        "error": "model is not allowed for this PerfRace session",
                        "model": model,
                        "allowed_model": allowed_model,
                    },
                )
                return

            try:
                # Forwarded calls use the file-only request log.
                request_logger.info(
                    "Forwarding token proxy request: session=%s model=%s path=%s",
                    session_id,
                    model,
                    suffix,
                )
                response = _forward_json(
                    state=state,
                    session_id=session_id,
                    suffix=suffix,
                    body=body,
                )
            except urllib.error.HTTPError as exc:
                logger.warning(
                    "Upstream LLM gateway returned HTTP error: session=%s status=%s path=%s",
                    session_id,
                    exc.code,
                    suffix,
                )
                self._send_bytes(exc.code, exc.read(), dict(exc.headers))
                return
            except Exception as exc:
                logger.exception(
                    "Failed to forward token proxy request: session=%s path=%s", session_id, suffix
                )
                self._send_json(502, {"error": str(exc)})
                return

            response_body = json.loads(response)
            state.record(session_id, model, body, response_body)
            self._send_json(200, response_body)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, status: int, data: dict[str, Any]) -> None:
            encoded = json.dumps(data).encode("utf-8")
            self._send_bytes(status, encoded, {"Content-Type": "application/json"})

        def _send_bytes(
            self,
            status: int,
            data: bytes,
            headers: dict[str, str],
        ) -> None:
            self.send_response(status)
            for key, value in headers.items():
                if key.lower() in {
                    "content-length",
                    "transfer-encoding",
                    "connection",
                }:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return TokenProxyHandler


def create_server(
    *,
    host: str,
    port: int,
    upstream_base_url: str,
    upstream_api_key: str | None,
    log_dir: Path,
) -> tuple[ThreadingHTTPServer, TokenProxyState]:
    _configure_request_logger(log_dir)
    state = TokenProxyState(
        upstream_base_url=upstream_base_url,
        upstream_api_key=upstream_api_key,
        log_dir=log_dir,
        secret=generate_token_proxy_secret(),
    )
    server = ThreadingHTTPServer((host, port), make_handler(state))
    logger.info(
        "Created token proxy server: host=%s port=%s upstream=%s log_dir=%s",
        server.server_address[0],
        server.server_address[1],
        state.upstream_base_url,
        log_dir,
    )
    return server, state


@contextmanager
def run_gateway(
    gateway: ApiGatewayConfig | None,
) -> Generator[dict[str, object], None, None]:
    """Own the entire optional LLM gateway lifecycle for one PerfRace run.

    Starts the optional upstream gateway process (``start_gateway``) and, if
    ``gateway.base_url`` is set, the token-accounting server's thread, and
    tears both down on exit -- the caller only ever sees one context manager,
    not the accounting server's own start/stop/join sequence.

    Yields the verifier kwargs (``container_token_proxy_base_url``/
    ``token_proxy_secret``) needed to reach the accounting server from inside
    a trial's container, or ``{}`` when no gateway is configured.
    """
    token_server: ThreadingHTTPServer | None = None
    token_thread: threading.Thread | None = None

    try:
        with start_gateway(gateway):
            if gateway is not None and gateway.base_url is not None:
                assert gateway.log_dir is not None, (
                    "ApiGatewayConfig.log_dir must be set by load_run() before run_gateway() runs"
                )
                token_server, token_state = create_server(
                    host="0.0.0.0",
                    port=0,
                    upstream_base_url=gateway.base_url,
                    upstream_api_key=gateway.api_key,
                    log_dir=gateway.log_dir / "token-proxy",
                )
                port = int(token_server.server_address[1])
                token_thread = threading.Thread(
                    target=token_server.serve_forever,
                    name="perfrace-token-proxy",
                    daemon=True,
                )
                token_thread.start()
                logger.info("Token proxy listening: port=%s", port)
                yield {
                    "container_token_proxy_base_url": f"http://host.docker.internal:{port}",
                    "host_token_proxy_base_url": f"http://127.0.0.1:{port}",
                    "token_proxy_secret": token_state.secret,
                }
            else:
                logger.info("No API gateway configured; trials get no LLM_* env injection")
                yield {}
    finally:
        if token_server is not None:
            logger.info("Stopping token proxy")
            token_server.shutdown()
            token_server.server_close()
        if token_thread is not None:
            token_thread.join(timeout=5)


@dataclass(frozen=True)
class CostModel:
    input_cost_per_token: float
    cached_input_cost_per_token: float
    output_cost_per_token: float


def estimate_cost_usd(model: str | None, usage: TokenUsage) -> float | None:
    if model is None:
        return None
    cost_model = load_cost_models().get(model)
    if cost_model is None:
        return None
    uncached_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    return (
        uncached_input_tokens * cost_model.input_cost_per_token
        + usage.cached_input_tokens * cost_model.cached_input_cost_per_token
        + usage.output_tokens * cost_model.output_cost_per_token
    )


def load_cost_models() -> dict[str, CostModel]:
    from perfrace.settings import settings

    configured = settings().get("cost_models_file")
    path = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[1] / "resources" / "cost-models.toml"
    )
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    result: dict[str, CostModel] = {}
    for name, values in data.get("cost_models", {}).items():
        result[str(name)] = CostModel(
            input_cost_per_token=float(values["input_cost_per_token"]),
            cached_input_cost_per_token=float(values["cached_input_cost_per_token"]),
            output_cost_per_token=float(values["output_cost_per_token"]),
        )
    return result


def _cached_input_tokens(usage: dict[str, Any]) -> int:
    details = (
        usage.get("prompt_tokens_details")
        or usage.get("input_tokens_details")
        or usage.get("input_token_details")
        or {}
    )
    if not isinstance(details, dict):
        return 0
    return int(details.get("cached_tokens") or 0)


def _single_model(models: set[str]) -> str | None:
    if len(models) != 1:
        return None
    return next(iter(models))


def _parse_session_path(path: str) -> tuple[str, str] | None:
    parsed = urlparse(path)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "sessions":
        return None
    return parts[1], "/".join(parts[2:])


def _request_session_and_suffix(
    state: TokenProxyState,
    path: str,
    headers: Any,
) -> tuple[str, str] | None:
    parsed = _parse_session_path(path)
    if parsed:
        return parsed

    suffix = _parse_default_path(path)
    if suffix is None:
        return None
    session_id = state.session_for_api_key(_bearer_token(headers))
    if session_id is None:
        return None
    return session_id, suffix


def _parse_default_path(path: str) -> str | None:
    parsed = urlparse(path)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 1 and parts[0] == "v1":
        return "/".join(parts)
    return None


def _is_reset_suffix(suffix: str) -> bool:
    return suffix == "reset"


def _is_summary_suffix(suffix: str) -> bool:
    return suffix == "summary"


def _bearer_token(headers: Any) -> str | None:
    auth = headers.get("Authorization") if hasattr(headers, "get") else None
    if not auth:
        return None
    prefix = "Bearer "
    if auth.startswith(prefix):
        return auth[len(prefix) :]
    return None


def _forward_json(
    *,
    state: TokenProxyState,
    session_id: str,
    suffix: str,
    body: dict[str, Any],
) -> bytes:
    if state.upstream_base_url.endswith("/v1") and suffix.startswith("v1/"):
        url = f"{state.upstream_base_url}/{suffix.removeprefix('v1/')}"
    else:
        url = f"{state.upstream_base_url}/{suffix}"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    request.add_header("X-PerfRace-Session", session_id)

    if state.upstream_api_key:
        request.add_header("Authorization", f"Bearer {state.upstream_api_key}")

    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()
