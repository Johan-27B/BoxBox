"""Filesystem- and network-restricted NexAU tools for offline evolution."""

from __future__ import annotations

import os
import selectors
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from nexau.archs.tool.builtin import file_tools


SHELL_IMAGE = "ubuntu@sha256:0e0a0fc6d18feda9db1590da249ac93e8d5abfea8f4c3c0c849ce512b5ef8982"
MAX_SHELL_OUTPUT_BYTES = 1_000_000


def _roots(variable: str) -> tuple[Path, ...]:
    """Load one required path-list environment variable."""
    values = tuple(
        Path(value).expanduser().resolve()
        for value in os.environ.get(variable, "").split(os.pathsep)
        if value
    )
    if not values:
        raise ValueError(f"{variable} must contain at least one path")
    return values


def _authorized_path(
    value: str,
    *,
    variable: str,
) -> Path:
    """Resolve a path and require it to stay below an allowed root."""
    roots = _roots(variable)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    resolved = candidate.resolve()
    matching_root = next(
        (root for root in roots if resolved == root or resolved.is_relative_to(root)),
        None,
    )
    if matching_root is None:
        raise PermissionError(f"Path is outside allowed roots: {value}")
    if ".git" in resolved.parts:
        raise PermissionError("Git metadata is controller-owned")
    return resolved


def read_file(
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    agent_state: Any = None,
) -> dict[str, Any]:
    """Read one allowlisted evidence or runtime file."""
    path = _authorized_path(file_path, variable="PERFRACE_META_READ_ROOTS")
    return file_tools.read_file(
        str(path),
        offset=offset,
        limit=limit,
        agent_state=agent_state,
    )


def write_file(
    file_path: str,
    content: str,
    modified_by_user: bool = False,
    ai_proposed_content: str | None = None,
    agent_state: Any = None,
) -> dict[str, Any]:
    """Write one file below an explicitly writable root."""
    path = _authorized_path(file_path, variable="PERFRACE_META_WRITE_ROOTS")
    return file_tools.write_file(
        str(path),
        content,
        modified_by_user=modified_by_user,
        ai_proposed_content=ai_proposed_content,
        agent_state=agent_state,
    )


def replace(
    file_path: str,
    old_string: str,
    new_string: str,
    expected_replacements: int = 1,
    instruction: str | None = None,
    modified_by_user: bool = False,
    ai_proposed_content: str | None = None,
    agent_state: Any = None,
) -> dict[str, Any]:
    """Replace exact text only in an explicitly writable file."""
    path = _authorized_path(file_path, variable="PERFRACE_META_WRITE_ROOTS")
    return file_tools.replace(
        str(path),
        old_string,
        new_string,
        expected_replacements=expected_replacements,
        instruction=instruction,
        modified_by_user=modified_by_user,
        ai_proposed_content=ai_proposed_content,
        agent_state=agent_state,
    )


def search_file_content(
    pattern: str,
    dir_path: str | None = None,
    include: str | None = None,
    agent_state: Any = None,
) -> dict[str, Any]:
    """Search only below configured read roots."""
    path = _authorized_path(
        dir_path or str(_roots("PERFRACE_META_READ_ROOTS")[0]),
        variable="PERFRACE_META_READ_ROOTS",
    )
    return file_tools.search_file_content(
        pattern,
        dir_path=str(path),
        include=include,
        agent_state=agent_state,
    )


def glob(
    pattern: str,
    dir_path: str | None = None,
    case_sensitive: bool = False,
    respect_git_ignore: bool = True,
    agent_state: Any = None,
) -> dict[str, Any]:
    """Glob only below configured read roots."""
    pattern_path = Path(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        raise PermissionError(f"Unsafe glob pattern: {pattern}")
    path = _authorized_path(
        dir_path or str(_roots("PERFRACE_META_READ_ROOTS")[0]),
        variable="PERFRACE_META_READ_ROOTS",
    )
    return file_tools.glob(
        pattern,
        dir_path=str(path),
        case_sensitive=case_sensitive,
        respect_git_ignore=respect_git_ignore,
        agent_state=agent_state,
    )


def list_directory(
    dir_path: str,
    ignore: list[str] | None = None,
    file_filtering_options: dict[str, bool] | None = None,
    show_hidden: bool = True,
    agent_state: Any = None,
) -> dict[str, Any]:
    """List only an allowlisted evidence or runtime directory."""
    path = _authorized_path(dir_path, variable="PERFRACE_META_READ_ROOTS")
    return file_tools.list_directory(
        str(path),
        ignore=ignore,
        file_filtering_options=file_filtering_options,
        show_hidden=show_hidden,
        agent_state=agent_state,
    )


def run_shell_command(
    command: str,
    description: str | None = None,
    is_background: bool = False,
    dir_path: str | None = None,
    timeout_ms: int = 300000,
    update_output: Any = None,
    agent_state: Any = None,
) -> dict[str, Any]:
    """Run a bounded command on a networkless, size-limited runtime copy."""
    del description, agent_state
    if is_background:
        raise ValueError("Background shell commands are not allowed")
    shell_root = _authorized_path(
        dir_path or str(_roots("PERFRACE_META_SHELL_ROOT")[0]),
        variable="PERFRACE_META_SHELL_ROOT",
    )
    runtime_root = _roots("PERFRACE_META_SHELL_ROOT")[0]
    relative_cwd = shell_root.relative_to(runtime_root)
    with tempfile.TemporaryDirectory(prefix="perfrace-meta-source-") as temporary:
        source_root = Path(temporary) / "source"

        def ignore_protected(path: str, names: list[str]) -> set[str]:
            ignored = {name for name in names if name in {".git", "__pycache__"}}
            ignored.update(name for name in names if name.endswith(".pyc"))
            return ignored

        shutil.copytree(
            runtime_root,
            source_root,
            symlinks=True,
            ignore=ignore_protected,
        )
        return _run_shell_container(
            command=command,
            source_root=source_root,
            relative_cwd=relative_cwd,
            timeout_ms=timeout_ms,
            update_output=update_output,
        )


def _run_shell_container(
    *,
    command: str,
    source_root: Path,
    relative_cwd: Path,
    timeout_ms: int,
    update_output: Any,
) -> dict[str, Any]:
    """Execute a command with only a sanitized runtime snapshot mounted."""
    container_name = f"perfrace-meta-{uuid.uuid4().hex[:12]}"
    arguments = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--pids-limit",
        "256",
        "--cpus",
        "2",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--tmpfs",
        "/workspace:rw,nosuid,size=512m",
    ]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/usr/local"):
        if Path(source).exists():
            arguments.extend(["--volume", f"{source}:{source}:ro"])
    arguments.extend(
        [
            "--volume",
            f"{source_root}:/source:ro",
            "--env",
            "HOME=/tmp",
            "--env",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            SHELL_IMAGE,
            "/bin/bash",
            "-c",
            (
                "cp -R --no-preserve=ownership,timestamps /source/. /workspace/ && "
                f"cd {shlex.quote(str(Path('/workspace') / relative_cwd))} && "
                f"exec /bin/bash -c {shlex.quote(command)}"
            ),
        ]
    )
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + max(timeout_ms / 1000, 1)
    failure: tuple[str, str] | None = None
    try:
        while True:
            if time.monotonic() >= deadline:
                failure = ("SHELL_TIMEOUT", f"Command exceeded {timeout_ms} ms")
                break
            events = selector.select(timeout=min(deadline - time.monotonic(), 0.25))
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                remaining = MAX_SHELL_OUTPUT_BYTES - len(output)
                output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    failure = (
                        "SHELL_OUTPUT_LIMIT",
                        f"Command exceeded {MAX_SHELL_OUTPUT_BYTES} output bytes",
                    )
                    break
            if failure is not None:
                break
            if process.poll() is not None and not selector.get_map():
                break
    finally:
        selector.close()
    if failure is not None:
        subprocess.run(
            ["docker", "rm", "--force", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        process.kill()
        process.wait()
        text = output.decode(errors="replace")
        return {
            "content": text or failure[1],
            "returnDisplay": text or failure[1],
            "error": {
                "type": failure[0],
                "message": failure[1],
            },
        }
    return_code = process.wait()
    text = output.decode(errors="replace")
    if update_output is not None and text:
        update_output(text)
    result: dict[str, Any] = {
        "content": text or "(empty)",
        "returnDisplay": text or "(empty)",
    }
    if return_code != 0:
        result["exit_code"] = return_code
        result["error"] = {
            "type": "SHELL_EXIT_ERROR",
            "message": f"Command exited with status {return_code}",
        }
    return result
