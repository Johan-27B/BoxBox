"""Pair Verification session, Copilot, proxy, report, and usage primitives."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml

from perfrace.curate.dashboard.events import read_jsonl, reduce_copilot_events
from perfrace.curate.report import (
    ReportState,
    read_text,
    read_report,
    update_report,
    update_report_metadata,
    write_text,
)
from perfrace.paths import resolve_instance_root
from perfrace.run.services.gateway import load_cost_models

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SESSION_ROOT = (
    Path(
        os.environ.get(
            "PERFRACE_VERIFICATION_SESSION_ROOT",
            PROJECT_ROOT / "data" / "pair-verification-sessions",
        )
    )
    .expanduser()
    .resolve()
)
SKILL_DIR = Path(__file__).resolve().parents[1] / "skill"
DEFAULT_MODEL = None
DEFAULT_CANDIDATE_AGENT = "copilot-cli"
DEFAULT_CANDIDATE_MODEL = None
DEFAULT_CANDIDATE_TIMEOUT_SECONDS = 1800
from perfrace.settings import endpoint, configured_model

HOST_GATEWAY_FILENAME = "host-gateway.yaml"
PROMOTION_FILENAME = "promotion.json"
REJECTION_FILENAME = "rejection.json"
INSTANCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*--[a-z0-9][a-z0-9-]*$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


@dataclass(frozen=True)
class SessionState:
    """Persistent launcher state shared by every invocation of one session."""

    session_id: str
    repo_url: str
    model: str
    started_at: str
    invocation_count: int
    instance_root: str
    workspace_path: str
    initial_workspace_path: str
    run_id: str = "legacy"
    candidate_agent: str = DEFAULT_CANDIDATE_AGENT
    candidate_model: str = DEFAULT_CANDIDATE_MODEL
    candidate_timeout_seconds: int = DEFAULT_CANDIDATE_TIMEOUT_SECONDS
    gateway_port: int = 0


class SessionInvocationLockedError(RuntimeError):
    """Raised when another process already owns a session invocation."""


@contextmanager
def session_invocation_lock(session_dir: Path):
    """Hold the cross-process lock for one complete Copilot invocation."""
    lock_path = session_dir / "invocation.lock"
    lock_file = lock_path.open("a+b")
    try:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SessionInvocationLockedError(
                f"another Pair Verification invocation is active for {session_dir.name}"
            ) from exc
        yield
    finally:
        lock_file.close()


def session_invocation_active(session_dir: Path) -> bool:
    """Return whether another process currently holds the invocation lock."""
    try:
        with session_invocation_lock(session_dir):
            return False
    except SessionInvocationLockedError:
        return True


def _write_session_state(session_dir: Path, state: SessionState) -> None:
    """Atomically persist launcher state."""
    destination = session_dir / "state.json"
    write_text(
        destination,
        json.dumps({"schema_version": 1, **asdict(state)}, indent=2) + "\n",
    )


def _validated_path_under(path: Path, root: Path) -> tuple[Path, tuple[str, ...]]:
    """Return one lexical absolute path beneath a real root with no symlinks."""
    absolute = Path(os.path.abspath(path.expanduser()))
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes the instance root: {absolute}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"path contains a symbolic link: {current}")
    return absolute, relative.parts


def _validate_rejected_source(
    source: Path,
    instance_root: Path,
    state: SessionState,
) -> Path:
    """Require a session-owned staging directory or a direct-child task directory."""
    source, relative_parts = _validated_path_under(source, instance_root)
    if source.exists() and (source.is_symlink() or not source.is_dir()):
        raise ValueError(f"rejected workspace is not a real directory: {source}")
    if len(relative_parts) > 1 and relative_parts[0] == ".staging":
        initial, _ = _validated_path_under(
            Path(state.initial_workspace_path),
            instance_root,
        )
        if source != initial or source.name != state.session_id:
            raise ValueError(f"rejected staging workspace does not belong to session: {source}")
        return source
    if len(relative_parts) == 1 and INSTANCE_ID_PATTERN.fullmatch(source.name):
        return source
    raise ValueError(f"rejected workspace is not a task directory: {source}")


def rejected_workspace_path(
    instance_root: Path,
    run_id: str,
    session_id: str,
) -> Path:
    """Return the only valid archive path for one rejected session."""
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"invalid Pair Verification run id: {run_id}")
    root = instance_root.expanduser().resolve()
    destination, relative = _validated_path_under(
        root / ".reject" / run_id / session_id,
        root,
    )
    if relative != (".reject", run_id, session_id):
        raise ValueError(f"invalid rejection destination: {destination}")
    return destination


def is_rejected_workspace(
    workspace: Path,
    instance_root: Path,
    run_id: str,
    session_id: str,
) -> bool:
    """Return whether ``workspace`` is the real archive directory for a session."""
    try:
        expected = rejected_workspace_path(instance_root, run_id, session_id)
        current, _ = _validated_path_under(
            workspace,
            instance_root.expanduser().resolve(),
        )
    except ValueError:
        return False
    return current == expected and current.is_dir() and not current.is_symlink()


def _reconcile_promotion(state: SessionState, session_dir: Path) -> SessionState:
    """Complete a durable staging rename after success or process interruption."""
    marker = session_dir / PROMOTION_FILENAME
    try:
        payload = json.loads(read_text(marker))
    except FileNotFoundError:
        return state
    if not isinstance(payload, dict):
        raise ValueError(f"invalid promotion marker: {marker}")
    source = Path(str(payload.get("source") or "")).resolve()
    destination = Path(str(payload.get("destination") or "")).resolve()
    instance_root = Path(state.instance_root).resolve()
    staging_root = (instance_root / ".staging").resolve()
    try:
        source.relative_to(staging_root)
        destination.relative_to(instance_root)
    except ValueError as exc:
        raise ValueError(f"promotion marker escapes the instance root: {marker}") from exc
    if destination.parent != instance_root or not INSTANCE_ID_PATTERN.fullmatch(destination.name):
        raise ValueError(f"invalid promotion destination: {destination}")
    if source.exists() and destination.exists():
        raise FileExistsError(f"both promotion paths exist: {source}, {destination}")
    if source.exists():
        source.rename(destination)
    elif not destination.exists():
        raise FileNotFoundError(f"neither promotion path exists: {source}, {destination}")
    updated = replace(state, workspace_path=str(destination))
    _write_run_config(session_dir, updated)
    _write_session_state(session_dir, updated)
    marker.unlink()
    return updated


def _reconcile_rejection(state: SessionState, session_dir: Path) -> SessionState:
    """Complete a durable move into the rejected-candidate archive."""
    marker = session_dir / REJECTION_FILENAME
    try:
        payload = json.loads(read_text(marker))
    except FileNotFoundError:
        return state
    if not isinstance(payload, dict):
        raise ValueError(f"invalid rejection marker: {marker}")
    instance_root = Path(state.instance_root).expanduser().resolve()
    state_workspace, _ = _validated_path_under(
        Path(state.workspace_path),
        instance_root,
    )
    source, _ = _validated_path_under(
        Path(str(payload.get("source") or "")),
        instance_root,
    )
    destination, relative_destination = _validated_path_under(
        Path(str(payload.get("destination") or "")),
        instance_root,
    )
    expected_destination = rejected_workspace_path(
        instance_root,
        state.run_id,
        state.session_id,
    )
    if destination != expected_destination or relative_destination != (
        ".reject",
        state.run_id,
        state.session_id,
    ):
        raise ValueError(f"invalid rejection destination: {destination}")
    if state_workspace == destination:
        if source.exists():
            raise FileExistsError(f"rejection source still exists after archival: {source}")
    elif source != state_workspace:
        raise ValueError(f"rejection source does not match session workspace: {source}")
    else:
        source = _validate_rejected_source(source, instance_root, state)
    if source.exists() and destination.exists():
        raise FileExistsError(f"both rejection paths exist: {source}, {destination}")
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    elif not destination.exists():
        raise FileNotFoundError(f"neither rejection path exists: {source}, {destination}")
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError(f"rejected workspace destination is not a real directory: {destination}")
    updated = replace(state, workspace_path=str(destination))
    _write_run_config(session_dir, updated)
    _write_session_state(session_dir, updated)
    marker.unlink()
    return updated


def _copilot_candidate(candidate_model: str) -> dict[str, object]:
    """Return the Harbor configuration for a Copilot CLI candidate."""
    return {
        "name": DEFAULT_CANDIDATE_AGENT,
        "model_name": candidate_model,
        "n_concurrent": 1,
        "extra_allowed_hosts": ["host.docker.internal"],
        "kwargs": {"reasoning_effort": "high"},
        "env": {
            "COPILOT_PROVIDER_BASE_URL": "${api_gateway.container_base_url}",
            "COPILOT_PROVIDER_API_KEY": "${api_gateway.api_key}",
            "COPILOT_PROVIDER_TYPE": "openai",
            "COPILOT_PROVIDER_WIRE_API": "responses",
            "COPILOT_PROVIDER_MODEL_ID": candidate_model,
            "COPILOT_PROVIDER_WIRE_MODEL": candidate_model,
            "COPILOT_MODEL": candidate_model,
        },
    }


def write_run_config(
    path: Path,
    *,
    instance_path: Path,
    session_id: str,
    candidate_agent: str,
    candidate_model: str,
    candidate_timeout_seconds: int,
    gateway_port: int,
) -> None:
    """Write the complete session-local configuration for the paired run."""
    if not instance_path.is_absolute():
        raise ValueError("paired run instance path must be absolute")
    if not candidate_agent.strip():
        raise ValueError("candidate agent must not be empty")
    if not candidate_model.strip():
        raise ValueError("candidate model must not be empty")
    if candidate_timeout_seconds < 1:
        raise ValueError("candidate timeout must be positive")
    if not 1 <= gateway_port <= 65535:
        raise ValueError("gateway port must be between 1 and 65535")

    agent: dict[str, object]
    environment: dict[str, object] = {"type": "docker"}
    config: dict[str, object] = {"enable_cache": False}
    if candidate_agent == DEFAULT_CANDIDATE_AGENT:
        overlay_path = path.with_name(HOST_GATEWAY_FILENAME)
        write_text(
            overlay_path,
            yaml.safe_dump(
                {
                    "services": {
                        "main": {
                            "extra_hosts": ["host.docker.internal:host-gateway"],
                        }
                    }
                },
                sort_keys=False,
            ),
        )
        environment["extra_docker_compose"] = [str(overlay_path)]
        config["api_gateway"] = _gateway_config(gateway_port)
        agent = _copilot_candidate(candidate_model)
    else:
        agent = {
            "name": candidate_agent,
            "model_name": candidate_model,
            "n_concurrent": 1,
        }
    agent["override_timeout_sec"] = candidate_timeout_seconds

    config["job"] = {
        "job_name": f"pair-verification-{session_id}",
        "jobs_dir": str(PROJECT_ROOT / "data" / "jobs"),
        "n_attempts": 1,
        "n_concurrent_trials": 1,
        "environment": environment,
        "tasks": [{"path": str(instance_path)}],
        "agents": [agent],
    }
    write_text(path, yaml.safe_dump(config, sort_keys=False))


def _write_run_config(session_dir: Path, state: SessionState) -> None:
    """Write the paired run config and fresh-job launcher."""
    config_path = session_dir / "run.yaml"
    write_run_config(
        config_path,
        instance_path=Path(state.workspace_path),
        session_id=state.session_id,
        candidate_agent=state.candidate_agent,
        candidate_model=state.candidate_model,
        candidate_timeout_seconds=state.candidate_timeout_seconds,
        gateway_port=state.gateway_port,
    )
    runner_path = session_dir / "run-pair.sh"
    write_text(
        runner_path,
        "#!/bin/sh\n"
        "set -eu\n\n"
        'job_name="pair-verification-'
        f'{state.session_id}-$(date -u +%Y%m%d-%H%M%S)-$$"\n'
        f"exec perfrace run --config {shlex.quote(str(config_path.resolve()))} "
        '--job-name "$job_name" "$@"\n',
    )
    runner_path.chmod(0o755)


def _normalize_repo_url(repo_url: str) -> tuple[str, str]:
    """Validate a GitHub repository URL and return its canonical URL and slug."""
    parsed = urllib.parse.urlparse(repo_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or len(parts) != 2:
        raise ValueError("repository must be an https://github.com/<owner>/<repo> URL")
    owner, repository = parts
    repository = repository.removesuffix(".git")
    if not owner or not repository:
        raise ValueError("repository URL must include an owner and repository")
    return f"https://github.com/{owner}/{repository}", f"{owner}-{repository}".lower()


def find_session_report(state: SessionState, session_dir: Path) -> Path:
    """Locate the Markdown report at the current or initial workspace path."""
    del session_dir
    current = Path(state.workspace_path) / "report.md"
    if read_report(current) is not None:
        return current
    initial = Path(state.initial_workspace_path) / "report.md"
    if initial != current and read_report(initial) is not None:
        return initial
    return current


def refresh_workspace_path(state: SessionState, session_dir: Path) -> SessionState:
    """Update persisted state when the staging directory was renamed."""
    report_path = find_session_report(state, session_dir)
    workspace_path = report_path.parent
    if str(workspace_path) == state.workspace_path:
        return state
    updated = replace(state, workspace_path=str(workspace_path))
    _write_run_config(session_dir, updated)
    _write_session_state(session_dir, updated)
    return updated


def promote_staging_workspace(
    state: SessionState,
    session_dir: Path,
    instance_id: str,
) -> SessionState:
    """Atomically rename an approved staging workspace to its final instance id."""
    if not INSTANCE_ID_PATTERN.fullmatch(instance_id):
        raise ValueError(f"invalid PerfRace instance id: {instance_id}")
    current = Path(state.workspace_path).resolve()
    staging_root = (Path(state.instance_root) / ".staging").resolve()
    try:
        current.relative_to(staging_root)
    except ValueError:
        return state
    destination = (Path(state.instance_root) / instance_id).resolve()
    if destination.exists():
        raise FileExistsError(f"instance directory already exists: {destination}")
    write_text(
        session_dir / PROMOTION_FILENAME,
        json.dumps(
            {
                "source": str(current),
                "destination": str(destination),
            },
            indent=2,
        )
        + "\n",
    )
    return _reconcile_promotion(state, session_dir)


def archive_rejected_workspace(
    state: SessionState,
    session_dir: Path,
    run_id: str,
) -> SessionState:
    """Move one rejected session workspace to ``.reject/<run-id>/<session-id>``."""
    if run_id != state.run_id:
        raise ValueError(f"rejection run id {run_id} does not match session run id {state.run_id}")
    instance_root = Path(state.instance_root).expanduser().resolve()
    destination = rejected_workspace_path(
        instance_root,
        state.run_id,
        state.session_id,
    )
    current, relative_current = _validated_path_under(
        Path(state.workspace_path),
        instance_root,
    )
    if current == destination:
        if not current.is_dir() or current.is_symlink():
            raise ValueError(f"rejected workspace destination is not a real directory: {current}")
        return state
    if relative_current and relative_current[0] == ".reject":
        raise ValueError(f"rejected workspace has an unexpected archive path: {current}")
    current = _validate_rejected_source(current, instance_root, state)
    if destination.exists():
        raise FileExistsError(f"rejected workspace already exists: {destination}")
    write_text(
        session_dir / REJECTION_FILENAME,
        json.dumps(
            {
                "source": str(current),
                "destination": str(destination),
            },
            indent=2,
        )
        + "\n",
    )
    return _reconcile_rejection(state, session_dir)


def _infer_run_id(
    *,
    instance_root: Path,
    workspace_path: Path,
    initial_workspace_path: Path,
    session_root: Path,
    session_id: str,
) -> str:
    """Infer the run namespace from workspace paths, falling back to ``legacy``."""
    root = instance_root.expanduser().resolve()
    for path, namespace in (
        (workspace_path, ".reject"),
        (initial_workspace_path, ".staging"),
    ):
        absolute = Path(os.path.abspath(path.expanduser()))
        try:
            relative = absolute.relative_to(root / namespace)
        except ValueError:
            continue
        if (
            len(relative.parts) == 2
            and relative.parts[1] == session_id
            and RUN_ID_PATTERN.fullmatch(relative.parts[0])
        ):
            return relative.parts[0]
    if session_root.name != "pair-verification-sessions" and RUN_ID_PATTERN.fullmatch(
        session_root.name
    ):
        return session_root.name
    return "legacy"


def create_session(
    repo_url: str,
    model: str,
    instance_root: Path | None = None,
    *,
    candidate_agent: str = DEFAULT_CANDIDATE_AGENT,
    candidate_model: str = DEFAULT_CANDIDATE_MODEL,
    candidate_timeout_seconds: int = DEFAULT_CANDIDATE_TIMEOUT_SECONDS,
    session_id: str | None = None,
    run_id: str | None = None,
    session_root: Path | None = None,
) -> tuple[SessionState, Path]:
    """Create isolated launcher and Copilot state for a new verification session."""
    model = configured_model("pair_verification", model)
    candidate_model = configured_model("candidate", candidate_model)
    canonical_url, slug = _normalize_repo_url(repo_url)
    session_id = str(uuid.UUID(session_id)) if session_id is not None else str(uuid.uuid4())
    resolved_run_id = run_id or "legacy"
    if not RUN_ID_PATTERN.fullmatch(resolved_run_id):
        raise ValueError(f"invalid Pair Verification run id: {resolved_run_id}")
    session_dir = (session_root or SESSION_ROOT) / session_id
    if (session_dir / "state.json").exists():
        raise FileExistsError(f"Pair Verification session already exists: {session_id}")
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "copilot-home").mkdir(exist_ok=True)
    resolved_instance_root = resolve_instance_root(instance_root)
    staging_root = resolved_instance_root / ".staging"
    if run_id is not None:
        staging_root /= resolved_run_id
    workspace_path = staging_root / session_id
    workspace_path.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    state = SessionState(
        session_id=session_id,
        repo_url=canonical_url,
        model=model,
        started_at=started_at,
        invocation_count=0,
        instance_root=str(resolved_instance_root),
        workspace_path=str(workspace_path),
        initial_workspace_path=str(workspace_path),
        run_id=resolved_run_id,
        candidate_agent=candidate_agent,
        candidate_model=candidate_model,
        candidate_timeout_seconds=candidate_timeout_seconds,
        gateway_port=_find_free_port(),
    )

    report_path = workspace_path / "report.md"
    write_text(report_path, read_text(SKILL_DIR / "REPORT_TEMPLATE.md"))
    update_report(
        report_path,
        ReportState(
            schema=1,
            instance=f"{slug}--pending",
            status="IN_PROGRESS",
            realism="PENDING",
            integrity="PENDING",
            reliability="PENDING",
            updated=started_at,
        ),
    )
    update_report_metadata(
        report_path,
        {"Source": canonical_url, "Started": started_at},
        updated=started_at,
    )
    _write_run_config(session_dir, state)
    _write_session_state(session_dir, state)
    return state, session_dir


def load_session(
    session_id: str,
    *,
    session_root: Path | None = None,
) -> tuple[SessionState, Path]:
    """Load a prior Pair Verification session by UUID."""
    try:
        normalized_id = str(uuid.UUID(session_id))
    except ValueError as exc:
        raise ValueError(f"invalid session UUID: {session_id}") from exc
    session_dir = (session_root or SESSION_ROOT) / normalized_id
    state_path = session_dir / "state.json"
    if not state_path.is_file():
        raise FileNotFoundError(f"Pair Verification session not found: {normalized_id}")
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    migrated = any(
        field not in raw
        for field in (
            "candidate_agent",
            "candidate_model",
            "candidate_timeout_seconds",
            "gateway_port",
            "run_id",
        )
    )
    instance_root = Path(raw.get("instance_root", str(resolve_instance_root())))
    workspace_path = Path(raw.get("workspace_path", str(session_dir)))
    initial_workspace_path = Path(
        raw.get(
            "initial_workspace_path",
            raw.get("workspace_path", str(session_dir)),
        )
    )
    run_id = str(
        raw.get("run_id")
        or _infer_run_id(
            instance_root=instance_root,
            workspace_path=workspace_path,
            initial_workspace_path=initial_workspace_path,
            session_root=session_dir.parent,
            session_id=normalized_id,
        )
    )
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"invalid Pair Verification run id in {state_path}: {run_id}")
    state = SessionState(
        session_id=raw["session_id"],
        repo_url=raw["repo_url"],
        model=raw["model"],
        started_at=raw["started_at"],
        invocation_count=int(raw["invocation_count"]),
        instance_root=str(instance_root),
        workspace_path=str(workspace_path),
        initial_workspace_path=str(initial_workspace_path),
        run_id=run_id,
        candidate_agent=str(raw.get("candidate_agent", DEFAULT_CANDIDATE_AGENT)),
        candidate_model=str(raw.get("candidate_model", DEFAULT_CANDIDATE_MODEL)),
        candidate_timeout_seconds=int(
            raw.get("candidate_timeout_seconds", DEFAULT_CANDIDATE_TIMEOUT_SECONDS)
        ),
        gateway_port=int(raw.get("gateway_port") or _find_free_port()),
    )
    if state.session_id != normalized_id:
        raise ValueError(f"state UUID mismatch in {state_path}")
    state = _reconcile_promotion(state, session_dir)
    state = _reconcile_rejection(state, session_dir)
    _write_run_config(session_dir, state)
    if migrated:
        _write_session_state(session_dir, state)
    return state, session_dir


def copilot_session_exists(state: SessionState, session_dir: Path) -> bool:
    """Return whether Copilot persisted enough state for ``--resume``."""
    events_path = (
        session_dir / "copilot-home" / "session-state" / state.session_id / "events.jsonl"
    )
    return events_path.is_file() and events_path.stat().st_size > 0


def register_skill(copilot_home: Path) -> None:
    """Register this checkout's verification skill without changing user settings."""
    copilot = shutil.which("copilot")
    if copilot is None:
        raise RuntimeError("copilot CLI is not available on PATH")
    env = {**os.environ, "COPILOT_HOME": str(copilot_home)}
    subprocess.run(
        [copilot, "skill", "add", str(SKILL_DIR)],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _find_free_port() -> int:
    """Ask the kernel for an unused localhost TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _initial_prompt(state: SessionState, session_dir: Path) -> str:
    """Build the standard first user turn for a new Pair Verification session."""
    draft_report = Path(state.initial_workspace_path) / "report.md"
    run_config = (session_dir / "run.yaml").resolve()
    run_command = (session_dir / "run-pair.sh").resolve()
    return f"""Invoke the perfrace-pair-verification skill before acting.

Pair-verify this repository with me:
{state.repo_url}

Pair Verification session UUID: {state.session_id}
Verification started at: {state.started_at}
Draft report: {draft_report}
Paired run config: {run_config}
Paired run command: {run_command}

Run Explore & Design first, then prepare a concise Realism brief. Use Chinese
for human-facing reviews and report conclusions. Before requesting Realism
review, inspect {state.instance_root}, choose an unused final
<repo>--<workload> id, and set it in report.md. Do not build the instance until
I approve Realism. Do not move the staging directory.
PerfRace performs the atomic rename only after final ACCEPT and worker exit.
Treat the repository's instances/ directory as pivot experiments unless it is
the configured instance root.
Use `"$PERFRACE_RUNNER"` for paired runs; it creates a fresh job name and
PerfRace automatically prepends the nop baseline.
Pause for Reliability and Integrity reviews at their construction nodes. Final
ACCEPT authorizes one GHCR instance release containing the image and attached
task artifact. From the staging workspace, use `perfrace publish . --image
<exact-local-image> --repository <ghcr-repo>`; do not manually tag or push the
image. Do not commit, push Git, register a Harbor task, or publish a dataset
without separate instructions."""


def _perfrace_cli_dir() -> Path:
    """Return the directory that guarantees a bare ``perfrace`` executable."""
    workspace_cli = PROJECT_ROOT / ".venv" / "bin" / "perfrace"
    if workspace_cli.is_file() and os.access(workspace_cli, os.X_OK):
        return workspace_cli.parent
    discovered = shutil.which("perfrace")
    if discovered is None:
        raise RuntimeError(
            f"perfrace CLI is unavailable; expected an executable at {workspace_cli} or on PATH"
        )
    return Path(discovered).resolve().parent


def build_copilot_command(
    state: SessionState,
    session_dir: Path,
    usage_path: Path,
    *,
    proxy_url: str,
    resume: bool,
) -> tuple[list[str], dict[str, str]]:
    """Build the interactive Copilot CLI command and BYOK environment."""
    copilot = shutil.which("copilot")
    if copilot is None:
        raise RuntimeError("copilot CLI is not available on PATH")
    perfrace_cli_dir = _perfrace_cli_dir()
    command = [
        copilot,
        "-C",
        state.workspace_path,
        "--add-dir",
        state.workspace_path,
        "--yolo",
        "--model",
        state.model,
        "--no-auto-update",
        "--log-level",
        "info",
        "--usage-output-file",
        str(usage_path),
        "--no-remote",
        "--secret-env-vars=COPILOT_PROVIDER_API_KEY,LLM_API_KEY",
    ]
    if resume:
        command.extend(["--resume", state.session_id])
    else:
        _, slug = _normalize_repo_url(state.repo_url)
        command.extend(
            [
                "--session-id",
                state.session_id,
                "--name",
                f"verify-{slug}-{state.session_id[:8]}",
                "-i",
                _initial_prompt(state, session_dir),
            ]
        )

    env = {
        **os.environ,
        "COPILOT_HOME": str(session_dir / "copilot-home"),
        "COPILOT_PROVIDER_BASE_URL": proxy_url,
        "COPILOT_PROVIDER_TYPE": "openai",
        "COPILOT_PROVIDER_API_KEY": endpoint()["api_key"],
        "COPILOT_PROVIDER_WIRE_API": "responses",
        "COPILOT_PROVIDER_MODEL_ID": state.model,
        "COPILOT_PROVIDER_WIRE_MODEL": state.model,
        "COPILOT_MODEL": state.model,
        "COPILOT_OTEL_FILE_EXPORTER_PATH": str(
            session_dir / f"otel-{state.invocation_count:04d}.jsonl"
        ),
        "PERFRACE_INSTANCE_ROOT": state.instance_root,
        "PERFRACE_REPO_ROOT": str(PROJECT_ROOT),
        "PERFRACE_RUN_CONFIG": str((session_dir / "run.yaml").resolve()),
        "PERFRACE_RUNNER": str((session_dir / "run-pair.sh").resolve()),
    }
    env["PATH"] = f"{perfrace_cli_dir}:{env.get('PATH', '')}"
    return command, env


def aggregate_usage(session_dir: Path) -> tuple[int, int] | None:
    """Return total billed tokens and provider-reported requests."""
    usage_paths = sorted(session_dir.glob("usage-*.json"))
    if not usage_paths:
        return None
    token_total = 0
    human_comments = 0
    for usage_path in usage_paths:
        payload = json.loads(usage_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"usage payload must be an object in {usage_path}")
        requests = payload.get("totalUserRequests")
        if not isinstance(requests, int) or requests < 0:
            raise ValueError(f"invalid totalUserRequests in {usage_path}")
        human_comments += requests
        model_metrics = payload.get("modelMetrics")
        if not isinstance(model_metrics, dict):
            raise ValueError(f"missing modelMetrics in {usage_path}")
        for metrics in model_metrics.values():
            usage = metrics.get("usage") if isinstance(metrics, dict) else None
            if not isinstance(usage, dict):
                raise ValueError(f"invalid model usage in {usage_path}")
            for field in (
                "inputTokens",
                "outputTokens",
                "cacheReadTokens",
                "cacheWriteTokens",
            ):
                value = usage.get(field, 0)
                if not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field} in {usage_path}")
                token_total += value
    return token_total, human_comments


def estimate_session_cost_usd(session_dir: Path) -> float | None:
    """Estimate session USD cost from configured model rates and usage files."""
    usage_paths = sorted(session_dir.glob("usage-*.json"))
    if not usage_paths:
        return None
    cost_models = load_cost_models()
    total = 0.0
    for usage_path in usage_paths:
        payload = json.loads(usage_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"usage payload must be an object in {usage_path}")
        model_metrics = payload.get("modelMetrics")
        if not isinstance(model_metrics, dict):
            raise ValueError(f"missing modelMetrics in {usage_path}")
        for model, metrics in model_metrics.items():
            cost_model = cost_models.get(str(model))
            if cost_model is None:
                return None
            usage = metrics.get("usage") if isinstance(metrics, dict) else None
            if not isinstance(usage, dict):
                raise ValueError(f"invalid model usage in {usage_path}")
            values: dict[str, int] = {}
            for field in (
                "inputTokens",
                "outputTokens",
                "cacheReadTokens",
                "cacheWriteTokens",
            ):
                value = usage.get(field, 0)
                if not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field} in {usage_path}")
                values[field] = value
            total += (
                max(values["inputTokens"] - values["cacheReadTokens"], 0)
                * cost_model.input_cost_per_token
                + values["cacheReadTokens"] * cost_model.cached_input_cost_per_token
                + values["outputTokens"] * cost_model.output_cost_per_token
            )
    return total


def count_human_interactions(state: SessionState, session_dir: Path) -> int | None:
    """Count persisted human messages and completed review responses."""
    events_path = (
        session_dir / "copilot-home" / "session-state" / state.session_id / "events.jsonl"
    )
    if not events_path.is_file():
        return None
    snapshot = reduce_copilot_events(
        read_jsonl(events_path),
        automatic_prompt=_initial_prompt(state, session_dir),
    )
    return snapshot.human_interactions


def sync_report_metrics(state: SessionState, session_dir: Path) -> list[Path]:
    """Write final usage totals into this session's Markdown report."""
    agent_cost_usd = estimate_session_cost_usd(session_dir)
    human_interactions = count_human_interactions(state, session_dir)
    report_path = find_session_report(state, session_dir)
    if read_report(report_path) is None:
        return []
    updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    update_report_metadata(
        report_path,
        {
            "Agent cost": (
                f"${agent_cost_usd:.6f}" if agent_cost_usd is not None else "Unavailable"
            ),
            "Human interactions": (
                human_interactions if human_interactions is not None else "Unavailable"
            ),
        },
        updated=updated_at,
    )
    return [report_path]


def _run_session_invocation_unlocked(
    state: SessionState,
    session_dir: Path,
    *,
    resume: bool,
) -> int:
    """Run one interactive Copilot invocation and synchronize final metrics."""
    state = refresh_workspace_path(state, session_dir)
    _perfrace_cli_dir()
    register_skill(session_dir / "copilot-home")
    state = replace(state, invocation_count=state.invocation_count + 1)
    _write_session_state(session_dir, state)
    usage_path = session_dir / f"usage-{state.invocation_count:04d}.json"
    proxy_url = endpoint()["base_url"]
    command, env = build_copilot_command(
        state,
        session_dir,
        usage_path,
        proxy_url=proxy_url,
        resume=resume,
    )

    env["LLM_API_KEY"] = endpoint()["api_key"]
    print(f"Pair Verification session: {state.session_id}")
    print(f"Model endpoint model: {state.model}")
    print(f"Instance root: {state.instance_root}")
    print(f"Workspace: {state.workspace_path}")
    print(f"Session data: {session_dir}")
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False)
        return_code = result.returncode
    except KeyboardInterrupt:
        return_code = 130

    state, _ = load_session(state.session_id)
    updated_reports = sync_report_metrics(state, session_dir)
    totals = aggregate_usage(session_dir)
    if totals is not None:
        human_interactions = count_human_interactions(state, session_dir)
        interactions_text = (
            str(human_interactions) if human_interactions is not None else "Unavailable"
        )
        cost = estimate_session_cost_usd(session_dir)
        cost_text = f"${cost:.6f}" if cost is not None else "Unavailable"
        print(f"Session totals: {cost_text} agent cost, {interactions_text} human interactions")
    if updated_reports:
        for report_path in updated_reports:
            try:
                display_path = report_path.relative_to(PROJECT_ROOT)
            except ValueError:
                display_path = report_path
            print(f"Updated report: {display_path}")
    else:
        print(f"Usage retained for later report sync: {usage_path}")
    return return_code


def run_session_invocation(
    state: SessionState,
    session_dir: Path,
    *,
    resume: bool,
) -> int:
    """Run one exclusive interactive Copilot invocation."""
    with session_invocation_lock(session_dir):
        return _run_session_invocation_unlocked(
            state,
            session_dir,
            resume=resume,
        )


def _write_worker_state(session_dir: Path, **values: object) -> None:
    """Persist the dashboard worker's current supervision state."""
    write_text(
        session_dir / "worker-state.json",
        json.dumps(values, indent=2) + "\n",
    )


def _disposition(session_id: str) -> str | None:
    """Return the final report status when the session has completed."""
    state, session_dir = load_session(session_id)
    state = refresh_workspace_path(state, session_dir)
    report = read_report(find_session_report(state, session_dir))
    if report is None:
        return None
    return report.status if report.status in {"ACCEPT", "REJECT"} else None


def _wait_for_resume() -> bool:
    """Wait for the explicit terminal command that resumes supervision."""
    print("\nPair Verification is paused.")
    print("Type resume and press Enter to continue this session.")
    try:
        while input("> ").strip().lower() != "resume":
            print("Type resume to continue.")
    except EOFError:
        return False
    return True


def supervise(session_id: str, *, wait_for_resume: bool = False) -> int:
    """Run Copilot and wait for explicit terminal resume after an early exit."""
    if wait_for_resume:
        _, session_dir = load_session(session_id)
        _write_worker_state(
            session_dir,
            state="needs_human",
            return_code=None,
            message="Resume required after dashboard restart.",
        )
        if not _wait_for_resume():
            return 0
    while True:
        state, session_dir = load_session(session_id)
        resume = copilot_session_exists(state, session_dir)
        _write_worker_state(
            session_dir,
            state="running",
            return_code=None,
            message=None,
        )
        try:
            return_code = run_session_invocation(state, session_dir, resume=resume)
        except SessionInvocationLockedError as exc:
            _write_worker_state(
                session_dir,
                state="needs_human",
                return_code=None,
                message=str(exc),
            )
            print(f"\n{exc}")
            if not _wait_for_resume():
                return 1
            continue
        except (
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
            TimeoutError,
            ValueError,
        ) as exc:
            message = f"Pair Verification invocation failed: {exc}"
            _write_worker_state(
                session_dir,
                state="needs_human",
                return_code=None,
                message=message,
            )
            print(f"\n{message}")
            if not _wait_for_resume():
                return 1
            continue
        disposition = _disposition(session_id)
        if disposition is not None:
            _write_worker_state(
                session_dir,
                state="completed",
                return_code=return_code,
                message=disposition,
            )
            print(f"\nPair Verification completed: {disposition}")
            return return_code

        _write_worker_state(
            session_dir,
            state="needs_human",
            return_code=return_code,
            message="Copilot exited before Pair Verification completed.",
        )
        if not _wait_for_resume():
            return return_code


def main(argv: list[str] | None = None) -> int:
    """Run an internal Pair Verification session command."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker_parser = subparsers.add_parser("worker")
    worker_parser.add_argument("session_id")
    worker_parser.add_argument("--wait-for-resume", action="store_true")
    args = parser.parse_args(argv)
    if not (SESSION_ROOT / args.session_id / "state.json").is_file():
        worker_parser.error(f"unknown Pair Verification session: {args.session_id}")
    return supervise(args.session_id, wait_for_resume=args.wait_for_resume)


if __name__ == "__main__":
    raise SystemExit(main())


def _gateway_config(gateway_port: int) -> dict[str, object]:
    """Reference an externally managed endpoint; never persist its credential."""
    from perfrace.settings import endpoint

    connection = endpoint()
    return {
        "port": gateway_port,
        "base_url": connection["base_url"],
        "api_key": "${env:LLM_API_KEY}",
    }
