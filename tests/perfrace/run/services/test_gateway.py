from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from perfrace.run.config import ApiGatewayConfig
from perfrace.run.services.gateway import (
    TokenProxyServiceError,
    TokenProxyState,
    TokenUsage,
    decode_token_proxy_api_key,
    estimate_cost_usd,
    read_token_proxy_summary,
    run_gateway,
    start_gateway,
    token_proxy_api_key,
    _forward_json,
    _request_session_and_suffix,
)


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


def test_token_usage_accepts_chat_and_responses_usage_shapes() -> None:
    usage = TokenUsage()
    usage.add(
        "gpt-5.4",
        {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "prompt_tokens_details": {"cached_tokens": 4},
        },
    )
    usage.add("gpt-5.4", {"input_tokens": 7, "output_tokens": 5, "total_tokens": 20})

    assert usage.to_json_dict() == {
        "input_tokens": 17,
        "cached_input_tokens": 4,
        "output_tokens": 8,
        "total_tokens": 33,
        "requests": 2,
        "models": ["gpt-5.4"],
    }


def test_token_proxy_state_resets_and_summarizes(tmp_path: Path) -> None:
    state = TokenProxyState(
        upstream_base_url="http://localhost:4000/v1",
        upstream_api_key="sk-test",
        log_dir=tmp_path,
        secret="test-secret",
    )
    state.record(
        "session-1",
        "gpt-5.5",
        {"model": "gpt-5.5"},
        {
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 4},
            }
        },
    )

    summary = state.summary("session-1")
    assert summary["input_tokens"] == 11
    assert summary["cached_input_tokens"] == 4
    assert summary["output_tokens"] == 2
    assert summary["total_tokens"] == 13
    assert summary["requests"] == 1
    assert summary["model"] == "gpt-5.5"
    assert Path(summary["log_path"]).exists()
    record = json.loads(Path(summary["log_path"]).read_text(encoding="utf-8"))
    assert isinstance(record["recorded_at"], float)

    state.reset("session-1")
    assert state.summary("session-1")["total_tokens"] == 0


def test_read_token_proxy_summary_uses_host_control_plane(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class SummaryResponse(_Response):
        def read(self) -> bytes:
            return b'{"session_id":"trial-1","input_tokens":10}'

    def fake_urlopen(url: str, timeout: int):
        captured["url"] = url
        captured["timeout"] = str(timeout)
        return SummaryResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    summary = asyncio.run(read_token_proxy_summary("http://127.0.0.1:44071/", "trial-1"))

    assert captured == {
        "url": "http://127.0.0.1:44071/sessions/trial-1/summary",
        "timeout": "30",
    }
    assert summary == {"session_id": "trial-1", "input_tokens": 10}


def test_estimate_cost_uses_short_alias_cost_model() -> None:
    usage = TokenUsage(input_tokens=11, cached_input_tokens=4, output_tokens=2)

    assert estimate_cost_usd("gpt-5.5", usage) == (7 * 5.0e-6 + 4 * 0.5e-6 + 2 * 30.0e-6)


def test_forward_json_does_not_duplicate_v1_prefix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["timeout"] = str(timeout)
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    state = TokenProxyState(
        upstream_base_url="http://localhost:4000/v1",
        upstream_api_key=None,
        log_dir=tmp_path,
        secret="test-secret",
    )

    _forward_json(
        state=state,
        session_id="trial-1",
        suffix="v1/chat/completions",
        body={"model": "gpt-5.2"},
    )

    assert captured["url"] == "http://localhost:4000/v1/chat/completions"


def test_forward_json_does_not_forward_trial_authorization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout: int):
        captured.update(dict(request.header_items()))
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    state = TokenProxyState(
        upstream_base_url="http://localhost:4000/v1",
        upstream_api_key=None,
        log_dir=tmp_path,
        secret="test-secret",
    )

    _forward_json(
        state=state,
        session_id="trial-1",
        suffix="v1/chat/completions",
        body={"model": "gpt-5.2"},
    )

    assert "Authorization" not in captured
    assert captured["X-perfrace-session"] == "trial-1"


def test_default_paths_resolve_session_from_bearer_token(tmp_path: Path) -> None:
    secret = "test-secret"
    state = TokenProxyState(
        upstream_base_url="http://localhost:4000/v1",
        upstream_api_key=None,
        log_dir=tmp_path,
        secret=secret,
    )
    token = token_proxy_api_key("trial-1", "gpt-5.5", secret=secret)

    parsed = _request_session_and_suffix(
        state,
        "/v1/chat/completions",
        {"Authorization": f"Bearer {token}"},
    )

    assert parsed == ("trial-1", "v1/chat/completions")
    assert decode_token_proxy_api_key(token, secret=secret) == ("trial-1", "gpt-5.5")


def test_session_paths_support_restful_control_aliases(tmp_path: Path) -> None:
    state = TokenProxyState(
        upstream_base_url="http://localhost:4000/v1",
        upstream_api_key=None,
        log_dir=tmp_path,
        secret="test-secret",
    )

    assert _request_session_and_suffix(state, "/sessions/trial-1/summary", {}) == (
        "trial-1",
        "summary",
    )
    assert _request_session_and_suffix(state, "/sessions/trial-1/reset", {}) == (
        "trial-1",
        "reset",
    )


def test_start_gateway_accepts_ready_healthcheck(monkeypatch) -> None:
    calls = []

    def fake_urlopen(url: str, timeout: int):
        calls.append((url, timeout))
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with start_gateway(ApiGatewayConfig(healthcheck="http://127.0.0.1:4000/health")):
        pass

    assert calls == [("http://127.0.0.1:4000/health", 5)]


def test_start_gateway_rejects_process_exit(monkeypatch) -> None:
    class ExitedProcess:
        returncode = 2

        def poll(self) -> int:
            return self.returncode

        def terminate(self) -> None:
            raise AssertionError("already exited process should not be terminated")

    monkeypatch.setattr("subprocess.Popen", lambda command: ExitedProcess())

    try:
        with start_gateway(
            ApiGatewayConfig(command="false", healthcheck="http://127.0.0.1:4000/health")
        ):
            pass
    except TokenProxyServiceError as exc:
        assert "exited before healthcheck" in str(exc)
    else:
        raise AssertionError("expected TokenProxyServiceError")


def test_start_gateway_substitutes_port_before_launching(monkeypatch) -> None:
    commands: list[list[str]] = []

    class RunningProcess:
        returncode = None

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: int) -> None:
            return None

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda command: commands.append(command) or RunningProcess(),
    )

    with start_gateway(
        ApiGatewayConfig(
            port=4100,
            command="proxy --port ${api_gateway.port}",
        )
    ):
        pass

    assert commands == [["proxy", "--port", "4100"]]


def test_run_gateway_yields_empty_kwargs_without_a_gateway_config(tmp_path: Path) -> None:
    with run_gateway(None) as kwargs:
        assert kwargs == {}


def test_run_gateway_yields_empty_kwargs_without_a_base_url(tmp_path: Path) -> None:
    gateway = ApiGatewayConfig(base_url=None, log_dir=tmp_path)

    with run_gateway(gateway) as kwargs:
        assert kwargs == {}


def test_run_gateway_starts_and_cleanly_stops_the_token_proxy_server(tmp_path: Path) -> None:
    gateway = ApiGatewayConfig(
        base_url="http://localhost:9999/v1", api_key="upstream-secret", log_dir=tmp_path
    )

    with run_gateway(gateway) as kwargs:
        assert kwargs["container_token_proxy_base_url"].startswith("http://host.docker.internal:")
        assert kwargs["host_token_proxy_base_url"].startswith("http://127.0.0.1:")
        assert isinstance(kwargs["token_proxy_secret"], str) and kwargs["token_proxy_secret"]

    # Exiting the context must shut the server thread down without hanging;
    # reaching this line at all is the assertion.
