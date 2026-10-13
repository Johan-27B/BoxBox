"""CLI entry point for the localhost verification dashboard."""

from __future__ import annotations

import getpass
import os
import re
import secrets
import socket
import threading
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from perfrace.settings import configured_model
import uvicorn

from perfrace.curate.dashboard.app import create_app
from perfrace.curate.dashboard.manager import DashboardConfig, DashboardManager
from perfrace.curate.dashboard.store import DashboardStore, parse_candidate_jsonl
from perfrace.curate.dashboard.session import (
    DEFAULT_CANDIDATE_AGENT,
    DEFAULT_CANDIDATE_MODEL,
    DEFAULT_CANDIDATE_TIMEOUT_SECONDS,
    DEFAULT_MODEL,
    _normalize_repo_url,
)
from perfrace.paths import PROJECT_ROOT, resolve_instance_root

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
DEFAULT_DASHBOARD_PORT = 8765


def _resolve_run_id(run_id: str | None) -> str:
    """Return a validated explicit ID or a new user-and-UTC-timestamp ID."""
    if run_id is None:
        user = re.sub(r"[^A-Za-z0-9_-]+", "-", getpass.getuser()).strip("_-")
        user = user or "user"
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        return f"{user}-{timestamp}"
    normalized = run_id.strip()
    if not RUN_ID_PATTERN.fullmatch(normalized):
        raise typer.BadParameter(
            "run ID must start with an alphanumeric character and contain only "
            "letters, numbers, '_', or '-' (maximum 128 characters)"
        )
    return normalized


def _bind_dashboard_socket(port: int | None) -> socket.socket:
    """Bind and retain the selected localhost socket for Uvicorn."""
    candidates = (port,) if port is not None else range(DEFAULT_DASHBOARD_PORT, 65536)
    last_error: OSError | None = None
    for candidate in candidates:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", candidate))
        except OSError as exc:
            listener.close()
            last_error = exc
            if port is not None:
                detail = exc.strerror or str(exc)
                raise typer.BadParameter(
                    f"dashboard port {port} is unavailable: {detail}"
                ) from exc
            continue
        listener.set_inheritable(True)
        return listener
    detail = last_error.strerror if last_error is not None else "no ports remain"
    raise typer.BadParameter(f"no localhost dashboard port is available: {detail}")


def _serve_dashboard(app: Any, listener: socket.socket) -> None:
    """Run Uvicorn on an already-bound socket."""
    config = uvicorn.Config(app, host="127.0.0.1", log_level="info")
    uvicorn.Server(config).run(sockets=[listener])


def verify_dashboard(
    candidate_file: Annotated[
        Path | None,
        typer.Option(
            "--candidate-file",
            help="JSONL candidate file. Each object must contain repo_url.",
        ),
    ] = None,
    instance_root: Annotated[
        Path | None,
        typer.Option(
            "--instance-root",
            help="Canonical instance root. Defaults to PERFRACE_INSTANCE_ROOT or repo instances/.",
        ),
    ] = None,
    max_sessions: Annotated[
        int,
        typer.Option("--max-sessions", min=1, help="Maximum unfinished sessions."),
    ] = 4,
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Stable namespace for dashboard state and sessions.",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", help="Model identifier."),
    ] = DEFAULT_MODEL,
    candidate_agent: Annotated[
        str,
        typer.Option("--candidate-agent", help="Candidate Harbor agent for new sessions."),
    ] = DEFAULT_CANDIDATE_AGENT,
    candidate_model: Annotated[
        str,
        typer.Option("--candidate-model", help="Candidate model for new sessions."),
    ] = DEFAULT_CANDIDATE_MODEL,
    candidate_timeout_seconds: Annotated[
        int,
        typer.Option(
            "--candidate-timeout-seconds",
            min=1,
            help="Candidate agent wall-clock budget for new sessions.",
        ),
    ] = DEFAULT_CANDIDATE_TIMEOUT_SECONDS,
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser/--no-open-browser"),
    ] = True,
) -> None:
    """Run the local multi-session Pair Verification dashboard."""
    model = configured_model("pair_verification", model)
    candidate_model = configured_model("candidate", candidate_model)
    resolved_run_id = _resolve_run_id(run_id)
    resolved_instance_root = resolve_instance_root(instance_root)
    dashboard_root = resolved_instance_root / ".dashboard" / resolved_run_id
    state_db_override = os.environ.get("PERFRACE_DASHBOARD_STATE_DB")
    if state_db_override is None:
        state_db = dashboard_root / "state.db"
    else:
        state_db_base = Path(state_db_override).expanduser()
        state_db = state_db_base.parent / resolved_run_id / state_db_base.name
    session_root_override = os.environ.get("PERFRACE_VERIFICATION_SESSION_ROOT")
    if session_root_override is None:
        session_root = dashboard_root / "sessions"
    else:
        session_root = Path(session_root_override).expanduser() / resolved_run_id
    store = DashboardStore(state_db)
    if candidate_file is not None:
        if not candidate_file.is_file():
            raise typer.BadParameter(f"candidate file not found: {candidate_file}")
        content = candidate_file.read_text(encoding="utf-8")
        for payload in parse_candidate_jsonl(content):
            try:
                _normalize_repo_url(payload["repo_url"])
            except ValueError as exc:
                raise typer.BadParameter(str(exc)) from exc
        store.import_jsonl(content)

    try:
        (resolved_instance_root / ".staging" / resolved_run_id).mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise typer.BadParameter(
            f"instance root is not writable: {resolved_instance_root}: {exc}"
        ) from exc

    manager = DashboardManager(
        store,
        DashboardConfig(
            instance_root=resolved_instance_root,
            max_sessions=max_sessions,
            model=model,
            candidate_agent=candidate_agent,
            candidate_model=candidate_model,
            candidate_timeout_seconds=candidate_timeout_seconds,
            run_id=resolved_run_id,
            session_root=session_root,
            release_catalog_path=PROJECT_ROOT / "releases" / "instance-releases.json",
        ),
    )
    listener = _bind_dashboard_socket(port)
    resolved_port = int(listener.getsockname()[1])
    access_token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{resolved_port}"
    url = f"{origin}/?token={access_token}"
    typer.echo(f"Pair Verification dashboard: {url}")
    typer.echo(f"Run ID: {resolved_run_id}")
    typer.echo(f"Instance root: {manager.config.instance_root}")
    typer.echo(f"Session root: {session_root}")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        _serve_dashboard(
            create_app(
                manager,
                access_token=access_token,
                allowed_origin=origin,
            ),
            listener,
        )
    finally:
        listener.close()
