from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from perfrace.release.archive import (
    create_task_archive,
    extract_task_archive,
    verify_task_archive,
)


def _task_files(root: Path) -> None:
    (root / "environment" / "workspace" / "project").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "task.toml").write_text('[task]\nname = "perfrace/project--workload"\n')
    (root / "instruction.md").write_text("Optimize the project.\n")
    (root / "report.md").write_text("report\n")
    script = root / "tests" / "test.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)


def test_task_archive_is_deterministic_and_preserves_modes(tmp_path: Path) -> None:
    task = tmp_path / "task"
    _task_files(task)

    first = create_task_archive(task, tmp_path / "first.tar.gz")
    second = create_task_archive(task, tmp_path / "second.tar.gz")

    assert first.content_hash == second.content_hash
    assert first.archive_digest == second.archive_digest
    extracted = tmp_path / "extracted"
    count = verify_task_archive(
        first.path,
        extracted,
        expected_content_hash=first.content_hash,
        expected_archive_digest=first.archive_digest,
    )
    assert count == first.file_count
    assert (extracted / "tests" / "test.sh").stat().st_mode & 0o111


def test_task_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        content = b"bad"
        info = tarfile.TarInfo("../outside")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))

    with pytest.raises(ValueError, match="unsafe task archive entry"):
        extract_task_archive(archive_path, tmp_path / "output")


def test_task_archive_rejects_external_symlinks(tmp_path: Path) -> None:
    task = tmp_path / "task"
    _task_files(task)
    outside = tmp_path / "outside"
    outside.write_text("secret\n")
    (task / "environment" / "workspace" / "project" / "linked").symlink_to(outside)

    with pytest.raises(ValueError, match="must be relative|escapes the task root"):
        create_task_archive(task, tmp_path / "task.tar.gz")


def test_task_archive_preserves_safe_file_symlinks(tmp_path: Path) -> None:
    task = tmp_path / "task"
    _task_files(task)
    project = task / "environment" / "workspace" / "project"
    target = project / "LICENSE.txt"
    target.write_text("license\n")
    (project / "license-link.txt").symlink_to("LICENSE.txt")

    archive = create_task_archive(task, tmp_path / "task.tar.gz")
    extracted = tmp_path / "extracted"
    verify_task_archive(
        archive.path,
        extracted,
        expected_content_hash=archive.content_hash,
        expected_archive_digest=archive.archive_digest,
    )

    link = extracted / "environment" / "workspace" / "project" / "license-link.txt"
    assert link.is_symlink()
    assert link.readlink() == Path("LICENSE.txt")


def test_task_archive_rejects_symlinked_gitignore(tmp_path: Path) -> None:
    task = tmp_path / "task"
    _task_files(task)
    outside = tmp_path / "outside-gitignore"
    outside.write_text("environment/\n")
    (task / ".gitignore").symlink_to(outside)

    with pytest.raises(ValueError, match="cannot contain symlinks"):
        create_task_archive(task, tmp_path / "task.tar.gz")
