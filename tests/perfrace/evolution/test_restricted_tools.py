import os
from pathlib import Path

import pytest

pytest.importorskip("nexau")

from perfrace.evolution import restricted_tools


def test_restricted_tools_deny_paths_and_sandbox_shell(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = tmp_path / "runtime"
    output = tmp_path / "output"
    runtime.mkdir()
    output.mkdir()
    (runtime / ".git").mkdir()
    (runtime / ".git" / "config").write_text("secret\n", encoding="utf-8")
    (runtime / "visible.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setenv("PERFRACE_META_READ_ROOTS", str(runtime))
    monkeypatch.setenv(
        "PERFRACE_META_WRITE_ROOTS",
        f"{runtime}:{output}",
    )
    monkeypatch.setenv("PERFRACE_META_SHELL_ROOT", str(runtime))
    with pytest.raises(PermissionError):
        restricted_tools._authorized_path(
            "/home/user/private",
            variable="PERFRACE_META_READ_ROOTS",
        )
    with pytest.raises(PermissionError, match="Git metadata"):
        restricted_tools._authorized_path(
            str(runtime / ".git" / "config"),
            variable="PERFRACE_META_READ_ROOTS",
        )
    with pytest.raises(PermissionError, match="Git metadata"):
        restricted_tools._authorized_path(
            str(runtime / ".git" / "config"),
            variable="PERFRACE_META_WRITE_ROOTS",
        )
    (tmp_path / "kernel").mkdir(parents=True)
    (tmp_path / "kernel" / "control.py").write_text(
        "SECRET = True\n",
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="outside allowed roots"):
        restricted_tools._authorized_path(
            str(tmp_path / "kernel" / "control.py"),
            variable="PERFRACE_META_READ_ROOTS",
        )
    with pytest.raises(PermissionError, match="outside allowed roots"):
        restricted_tools._authorized_path(
            str(tmp_path / "kernel" / "control.py"),
            variable="PERFRACE_META_WRITE_ROOTS",
        )
    captured = {}

    class FakeProcess:
        def __init__(self, arguments, **kwargs) -> None:
            captured["arguments"] = arguments
            captured["kwargs"] = kwargs
            source_mount = next(
                argument for argument in arguments if argument.endswith(":/source:ro")
            )
            source = Path(source_mount.removesuffix(":/source:ro"))
            captured["source"] = source
            captured["source_visible"] = (source / "visible.py").read_text(encoding="utf-8")
            captured["source_has_git"] = (source / ".git").exists()
            captured["source_has_kernel"] = (source / "kernel").exists()
            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"ok")
            os.close(write_fd)
            self.stdout = os.fdopen(read_fd, "rb")

        def poll(self):
            return 0

        def wait(self):
            return 0

        def kill(self):
            return None

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        raise AssertionError("cleanup should not run")

    monkeypatch.setattr(restricted_tools.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(restricted_tools.subprocess, "run", fake_run)

    result = restricted_tools.run_shell_command(
        command="python3 -m compileall -q harness",
        dir_path=str(runtime),
    )

    arguments = captured["arguments"]
    assert result["content"] == "ok"
    assert arguments[arguments.index("--network") + 1] == "none"
    assert "--read-only" in arguments
    assert arguments[arguments.index("--cpus") + 1] == "2"
    assert arguments[arguments.index("--memory") + 1] == "2g"
    assert arguments[arguments.index("--memory-swap") + 1] == "2g"
    assert ["--cap-drop", "ALL"] == arguments[
        arguments.index("--cap-drop") : arguments.index("--cap-drop") + 2
    ]
    assert not any("LLM_API_KEY" in argument for argument in arguments)
    assert f"{captured['source']}:/source:ro" in arguments
    assert captured["source"] != runtime
    assert captured["source_visible"] == "VALUE = 1\n"
    assert captured["source_has_git"] is False
    assert captured["source_has_kernel"] is False
    assert "/workspace:rw,nosuid,size=512m" in arguments
