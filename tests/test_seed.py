"""Source selection, isolation, and failure behavior shared by harness methods."""

import os
import subprocess
from pathlib import Path

import pytest

from boxbox.terminus_boxbox.seed import fingerprint, materialize


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def commit(repository: Path) -> str:
    git(repository, "add", "-A")
    git(repository, "commit", "-q", "-m", "test revision")
    return git(repository, "rev-parse", "HEAD")


@pytest.fixture
def repository(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "Test")
    git(source, "config", "user.email", "test@example.invalid")
    return source


def test_source_layout_is_not_prescribed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "custom-agent.txt").write_text("original implementation")
    first = materialize(source, tmp_path / "first")
    second = materialize(source, tmp_path / "second")
    assert fingerprint(first) == fingerprint(second) == fingerprint(source)
    (first / "custom-agent.txt").write_text("one run's update")
    assert (second / "custom-agent.txt").read_text() == "original implementation"
    assert (source / "custom-agent.txt").read_text() == "original implementation"
    assert fingerprint(first) != fingerprint(second)


def test_selected_commit_ignores_dirty_files_and_export_filters(repository, tmp_path):
    (repository / "agent.txt").write_text("first version")
    (repository / "keep.txt").write_text("required committed file")
    (repository / ".gitattributes").write_text("keep.txt export-ignore\n")
    first = commit(repository)
    (repository / "agent.txt").write_text("second version")
    second = commit(repository)
    (repository / "agent.txt").write_text("uncommitted edit")
    (repository / "extra.txt").write_text("untracked")
    before = git(repository, "status", "--porcelain")

    copy = materialize(repository, tmp_path / "copy", revision=first)

    assert (copy / "agent.txt").read_text() == "first version"
    assert (copy / "keep.txt").read_text() == "required committed file"
    assert not (copy / "extra.txt").exists()
    assert not (copy / ".git").exists()
    assert (repository / "agent.txt").read_text() == "uncommitted edit"
    assert git(repository, "rev-parse", "HEAD") == second
    assert git(repository, "status", "--porcelain") == before


def test_existing_destination_is_never_overwritten(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "work.txt").write_text("keep this work")
    with pytest.raises(FileExistsError):
        materialize(source, destination)
    assert (destination / "work.txt").read_text() == "keep this work"


def test_invalid_revision_leaves_no_partial_copy(repository, tmp_path):
    (repository / "agent.txt").write_text("work")
    commit(repository)
    destination = tmp_path / "destination"
    with pytest.raises(ValueError):
        materialize(repository, destination, revision="missing-revision")
    assert not destination.exists()


@pytest.mark.parametrize("from_commit", [False, True])
def test_nonportable_link_is_rejected_without_leaving_partial_copy(repository, tmp_path, from_commit):
    (repository / "first.txt").write_text("safe file")
    outside = tmp_path / "outside.txt"
    outside.write_text("not part of the harness")
    (repository / "link.txt").symlink_to(outside)
    revision = commit(repository) if from_commit else None
    destination = tmp_path / "destination"
    with pytest.raises(ValueError):
        materialize(repository, destination, revision=revision)
    assert not destination.exists()
    assert outside.read_text() == "not part of the harness"


@pytest.mark.parametrize("from_commit", [False, True])
def test_executable_behavior_survives_copy(repository, tmp_path, from_commit):
    command = repository / "hello"
    command.write_text("#!/bin/sh\nprintf 'hello from harness'\n")
    command.chmod(0o755)
    revision = commit(repository) if from_commit else None
    copied = materialize(repository, tmp_path / "copy", revision=revision)
    result = subprocess.run([str(copied / "hello")], capture_output=True, text=True, check=True)
    assert result.stdout == "hello from harness"
    before = fingerprint(copied)
    (copied / "hello").chmod(0o644)
    assert not os.access(copied / "hello", os.X_OK)
    assert fingerprint(copied) != before


def test_generated_files_do_not_change_source_identity(repository, tmp_path):
    (repository / "agent.txt").write_text("implementation")
    before = fingerprint(repository)
    cache = repository / "__pycache__"
    cache.mkdir()
    (cache / "cache.pyc").write_bytes(b"generated")
    (repository / "unused.pyc").write_bytes(b"generated")
    assert fingerprint(repository) == before
    copy = materialize(repository, tmp_path / "copy")
    assert fingerprint(copy) == before
    assert not (copy / "__pycache__").exists()


def test_existing_harness_is_copied_unchanged(repository, tmp_path):
    relative = Path("settings/instructions.txt")
    (repository / relative).parent.mkdir(parents=True)
    (repository / relative).write_text("evolved instructions")
    revision = commit(repository)
    for name in ("test-run", "next-attempt"):
        copied = materialize(repository, tmp_path / name, revision=revision)
        assert fingerprint(copied) == fingerprint(repository)
        assert (copied / relative).read_text() == "evolved instructions"


@pytest.mark.parametrize("from_commit", [False, True])
def test_overlay_copies_arbitrary_files_by_relative_path(repository, tmp_path, from_commit):
    (repository / "settings").mkdir()
    (repository / "settings/value.txt").write_text("old value")
    (repository / "keep.txt").write_text("unchanged")
    revision = commit(repository) if from_commit else None
    before = fingerprint(repository)
    overlay = tmp_path / "extra-files"
    (overlay / "settings").mkdir(parents=True)
    (overlay / "settings/value.txt").write_text("new value")
    (overlay / "assets").mkdir()
    (overlay / "assets/data.bin").write_bytes(b"\x00\x01\xff")
    command = overlay / "hello"
    command.write_text("#!/bin/sh\nprintf 'overlay command'\n")
    command.chmod(0o755)
    overlay_before = fingerprint(overlay)

    copied = materialize(
        repository, tmp_path / "copy", revision=revision, overlay=overlay
    )
    assert (copied / "settings/value.txt").read_text() == "new value"
    assert (copied / "keep.txt").read_text() == "unchanged"
    assert (copied / "assets/data.bin").read_bytes() == b"\x00\x01\xff"
    result = subprocess.run([str(copied / "hello")], capture_output=True, check=True)
    assert result.stdout == b"overlay command"
    assert fingerprint(repository) == before
    assert fingerprint(overlay) == overlay_before


def test_invalid_overlay_removes_partial_copy(repository, tmp_path):
    (repository / "keep.txt").write_text("original")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "first.txt").write_text("added")
    (overlay / "link").symlink_to(repository / "keep.txt")
    destination = tmp_path / "copy"
    with pytest.raises(ValueError):
        materialize(repository, destination, overlay=overlay)
    assert not destination.exists()
    assert (repository / "keep.txt").read_text() == "original"


def test_overlay_file_directory_conflict_removes_partial_copy(repository, tmp_path):
    (repository / "entry").write_text("original")
    overlay = tmp_path / "overlay"
    (overlay / "entry").mkdir(parents=True)
    (overlay / "entry/nested.txt").write_text("added")
    destination = tmp_path / "copy"
    with pytest.raises(FileExistsError):
        materialize(repository, destination, overlay=overlay)
    assert not destination.exists()
    assert (repository / "entry").read_text() == "original"


def test_overlay_cannot_replace_directory_with_file(repository, tmp_path):
    (repository / "entry").mkdir()
    (repository / "entry/keep.txt").write_text("original")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "entry").write_text("replacement")
    destination = tmp_path / "copy"
    with pytest.raises(IsADirectoryError):
        materialize(repository, destination, overlay=overlay)
    assert not destination.exists()
    assert (repository / "entry/keep.txt").read_text() == "original"


def test_destination_inside_overlay_is_rejected(repository, tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    destination = overlay / "copy"
    with pytest.raises(ValueError):
        materialize(repository, destination, overlay=overlay)
    assert not destination.exists()
