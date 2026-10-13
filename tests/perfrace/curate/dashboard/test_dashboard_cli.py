from __future__ import annotations

import socket
from pathlib import Path

import pytest

from perfrace.curate import cli


def test_dashboard_cli_generates_user_timestamp_run_id(monkeypatch) -> None:
    monkeypatch.setattr(cli.getpass, "getuser", lambda: "collaborator")

    run_id = cli._resolve_run_id(None)

    assert cli.RUN_ID_PATTERN.fullmatch(run_id)
    assert run_id.startswith("collaborator-")


@pytest.mark.parametrize("run_id", ["../shared", "review.with.dot"])
def test_dashboard_cli_rejects_unsafe_run_id(run_id: str) -> None:
    with pytest.raises(cli.typer.BadParameter, match="run ID"):
        cli._resolve_run_id(run_id)


def test_dashboard_cli_rejects_occupied_port_before_startup() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        with pytest.raises(cli.typer.BadParameter, match=f"dashboard port {port} is unavailable"):
            cli._bind_dashboard_socket(port)


def test_dashboard_cli_selects_next_available_default_port(monkeypatch) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        occupied_port = int(occupied.getsockname()[1])
        monkeypatch.setattr(cli, "DEFAULT_DASHBOARD_PORT", occupied_port)

        selected = cli._bind_dashboard_socket(None)
        try:
            assert selected.getsockname()[1] != occupied_port
        finally:
            selected.close()


def test_dashboard_cli_defaults_runtime_under_instance_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeManager:
        def __init__(self, _store, config):
            self.config = config
            captured["config"] = config

    monkeypatch.delenv("PERFRACE_DASHBOARD_STATE_DB", raising=False)
    monkeypatch.delenv("PERFRACE_VERIFICATION_SESSION_ROOT", raising=False)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    monkeypatch.setattr(cli, "_bind_dashboard_socket", lambda _port: listener)
    monkeypatch.setattr(cli, "DashboardManager", FakeManager)
    monkeypatch.setattr(cli, "create_app", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "_serve_dashboard", lambda _app, _listener: None)

    cli.verify_dashboard(
        instance_root=tmp_path / "instances",
        run_id="review-run",
        open_browser=False,
    )

    dashboard_root = tmp_path / "instances" / ".dashboard" / "review-run"
    config = captured["config"]
    assert config.session_root == dashboard_root / "sessions"
    assert config.release_catalog_path == cli.PROJECT_ROOT / "releases" / "instance-releases.json"
    assert (dashboard_root / "state.db").is_file()
    assert listener.fileno() == -1


def test_dashboard_cli_propagates_candidate_options(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeManager:
        def __init__(self, _store, config):
            self.config = config
            captured["config"] = config

    monkeypatch.setenv("PERFRACE_DASHBOARD_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv(
        "PERFRACE_VERIFICATION_SESSION_ROOT",
        str(tmp_path / "pair-verification-sessions"),
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    monkeypatch.setattr(cli, "_bind_dashboard_socket", lambda _port: listener)
    monkeypatch.setattr(cli, "DashboardManager", FakeManager)
    monkeypatch.setattr(cli, "create_app", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        cli,
        "_serve_dashboard",
        lambda _app, selected: captured.update(listener=selected),
    )

    cli.verify_dashboard(
        candidate_file=None,
        instance_root=tmp_path / "instances",
        max_sessions=2,
        run_id="collaborator-20260830",
        port=8765,
        model="gpt-5.6-sol",
        candidate_agent="claude-code",
        candidate_model="claude-sonnet-4-5",
        candidate_timeout_seconds=900,
        open_browser=False,
    )

    config = captured["config"]
    assert config.candidate_agent == "claude-code"
    assert config.candidate_model == "claude-sonnet-4-5"
    assert config.candidate_timeout_seconds == 900
    assert config.run_id == "collaborator-20260830"
    assert config.session_root == tmp_path / "pair-verification-sessions" / (
        "collaborator-20260830"
    )
    assert (tmp_path / "collaborator-20260830" / "state.db").is_file()
    assert captured["listener"] is listener
    assert listener.fileno() == -1
