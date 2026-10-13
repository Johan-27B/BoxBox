from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from perfrace.release.oci import OrasClient


def test_oras_preflight_requires_pinned_version(monkeypatch) -> None:
    monkeypatch.setattr("perfrace.release.oci.shutil.which", lambda _name: "/usr/bin/oras")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout="Version: 1.3.2\n",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="ORAS 1.3.3 is required"):
        OrasClient().preflight()


def test_oras_attach_uses_image_subject_and_task_media_type(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(command, *, cwd=None, **_kwargs):
        calls.append((command, cwd))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Digest: sha256:" + "b" * 64 + "\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    archive = tmp_path / "task.tar.gz"
    archive.write_bytes(b"archive")

    artifact = OrasClient().attach_task(
        image_reference="ghcr.io/example/task@sha256:" + "a" * 64,
        archive_path=archive,
        instance_id="project--workload",
        content_hash="c" * 64,
        created_at="2026-09-02T00:00:00Z",
    )

    assert artifact.reference == "ghcr.io/example/task@sha256:" + "b" * 64
    command, cwd = calls[0]
    assert command[:2] == ["oras", "attach"]
    assert command[-2] == "ghcr.io/example/task@sha256:" + "a" * 64
    assert command[-1].startswith("task.tar.gz:")
    assert cwd == tmp_path
