"""Versioned runtime repository owned by offline harness evolution."""

from __future__ import annotations

import hashlib

from boxbox.terminus_boxbox.seed import fingerprint, materialize
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path


def hash_source_tree(source: Path) -> str:
    """Identify a harness source with the same content hash used for the shared H0."""
    return fingerprint(source)


def _git_text(
    repository: Path,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> str:
    """Run one Git command and return stripped text output."""
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise ValueError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"Git command failed: {' '.join(arguments)}"
        )
    return result.stdout.strip()


def _archive_bytes(repository: Path, commit: str) -> tuple[bytes, str]:
    """Return deterministic Git archive bytes and their SHA-256 digest."""
    result = subprocess.run(
        ["git", "-C", str(repository), "archive", "--format=tar", commit],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            result.stderr.decode(errors="replace").strip()
            or f"Failed to archive runtime commit {commit}"
        )
    payload = result.stdout
    return payload, hashlib.sha256(payload).hexdigest()


def _worktree_tree(repository: Path, commit: str) -> str:
    """Build a fresh index tree so hidden worktree changes cannot evade validation."""
    descriptor, index_name = tempfile.mkstemp(prefix="perfrace-offline-runtime-index-")
    os.close(descriptor)
    Path(index_name).unlink()
    environment = {**os.environ, "GIT_INDEX_FILE": index_name}
    try:
        _git_text(repository, "read-tree", commit, env=environment)
        _git_text(repository, "add", "-A", env=environment)
        return _git_text(repository, "write-tree", env=environment)
    finally:
        Path(index_name).unlink(missing_ok=True)
        Path(f"{index_name}.lock").unlink(missing_ok=True)


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Identity of one validated committed harness generation."""

    commit: str
    tree: str
    source_sha256: str


class RuntimeRepository:
    """Initialize, validate, and materialize the offline runtime lineage."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        if not (self.path / ".git").exists():
            raise ValueError(f"Runtime repository is not initialized: {self.path}")

    @classmethod
    def initialize(cls, source: Path, destination: Path) -> RuntimeRepository:
        """Create the Runtime 0 repository from the package-owned source tree."""
        resolved_source = source.expanduser().resolve()
        resolved_destination = destination.expanduser().resolve()
        if not (resolved_source / "__init__.py").is_file():
            raise ValueError(f"Harness source has no __init__.py: {resolved_source}")
        if resolved_destination.exists():
            raise FileExistsError(f"Runtime repository already exists: {resolved_destination}")
        resolved_destination.parent.mkdir(parents=True, exist_ok=True)
        materialize(resolved_source, resolved_destination)
        _git_text(resolved_destination, "init", "-q", "-b", "main")
        (resolved_destination / ".git" / "info" / "exclude").write_text(
            "__pycache__/\n*.pyc\n", encoding="utf-8"
        )
        _git_text(
            resolved_destination,
            "config",
            "user.email",
            "offline-harness@perfrace.local",
        )
        _git_text(resolved_destination, "config", "user.name", "offline-harness")
        _git_text(resolved_destination, "add", "-A")
        _git_text(
            resolved_destination,
            "commit",
            "-q",
            "-m",
            "runtime: initial offline harness",
        )
        _git_text(resolved_destination, "tag", "runtime0")
        repository = cls(resolved_destination)
        repository.validate_head()
        return repository

    def validate_head(self) -> RuntimeSnapshot:
        """Validate and identify the clean committed candidate at HEAD."""
        status = _git_text(
            self.path,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            raise ValueError("Runtime repository must have a clean committed HEAD")
        commit = _git_text(self.path, "rev-parse", "HEAD^{commit}")
        tree = _git_text(self.path, "rev-parse", f"{commit}^{{tree}}")
        if _worktree_tree(self.path, commit) != tree:
            raise ValueError("Runtime worktree differs from its committed HEAD")
        self.validate_commit_entries(commit)
        _, source_sha256 = _archive_bytes(self.path, commit)
        return RuntimeSnapshot(
            commit=commit,
            tree=tree,
            source_sha256=source_sha256,
        )

    def head_commit(self) -> str:
        """Return HEAD without requiring a clean worktree."""
        return _git_text(self.path, "rev-parse", "HEAD^{commit}")

    def worktree_changed_files(self) -> tuple[str, ...]:
        """Return tracked and untracked worktree paths outside Git metadata."""
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.path),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "Failed to inspect runtime worktree")
        paths: list[str] = []
        for line in result.stdout.splitlines():
            value = line[3:]
            if " -> " in value:
                value = value.split(" -> ", 1)[1]
            paths.append(value)
        return tuple(sorted(paths))

    def validate_worktree_entries(self) -> None:
        """Reject symlinks and special files in the candidate runtime worktree."""
        root = self.path
        for path in root.rglob("*"):
            if ".git" in path.relative_to(root).parts:
                continue
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError(f"Runtime worktree contains a non-regular entry: {path}")

    def validate_commit_entries(self, commit: str) -> None:
        """Reject symlinks and special files in a committed runtime tree."""
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.path),
                "ls-tree",
                "-rz",
                "--full-tree",
                commit,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(
                result.stderr.decode(errors="replace").strip()
                or "Failed to inspect committed runtime entries"
            )
        for record in result.stdout.split(b"\0"):
            if not record:
                continue
            metadata, separator, raw_path = record.partition(b"\t")
            if not separator:
                raise ValueError("Malformed committed runtime tree entry")
            mode, kind, _ = metadata.decode("ascii").split()
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(
                    "Runtime commit contains a non-regular entry: "
                    f"{raw_path.decode(errors='replace')}"
                )

    def commit_worktree(self, message: str) -> RuntimeSnapshot:
        """Create one controller-owned commit with hooks disabled."""
        if not self.worktree_changed_files():
            raise ValueError("Runtime worktree has no changes to commit")
        _git_text(
            self.path,
            "-c",
            "core.hooksPath=/dev/null",
            "add",
            "-A",
            "--",
            ".",
        )
        _git_text(
            self.path,
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "--no-verify",
            "-m",
            message,
        )
        return self.validate_head()

    def restore(self, commit: str) -> RuntimeSnapshot:
        """Restore the generated runtime repository to one committed parent."""
        _git_text(
            self.path,
            "-c",
            "core.hooksPath=/dev/null",
            "reset",
            "--hard",
            commit,
        )
        _git_text(
            self.path,
            "-c",
            "core.hooksPath=/dev/null",
            "clean",
            "-fd",
            "--",
            ".",
        )
        return self.validate_head()

    def materialize(self, commit: str, destination: Path) -> RuntimeSnapshot:
        """Materialize one validated commit without checkout filters."""
        resolved_commit = _git_text(self.path, "rev-parse", f"{commit}^{{commit}}")
        tree = _git_text(self.path, "rev-parse", f"{resolved_commit}^{{tree}}")
        self.validate_commit_entries(resolved_commit)
        payload, source_sha256 = _archive_bytes(self.path, resolved_commit)
        resolved_destination = destination.expanduser().resolve()
        if resolved_destination.exists():
            raise FileExistsError(f"Runtime snapshot already exists: {resolved_destination}")
        resolved_destination.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            for member in archive.getmembers():
                relative = Path(member.name)
                if (
                    relative.is_absolute()
                    or not relative.parts
                    or any(part in {"", ".", ".."} for part in relative.parts)
                ):
                    raise ValueError(f"Runtime archive contains unsafe path: {member.name}")
                target = resolved_destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ValueError(
                        f"Runtime archive may contain only regular files: {member.name}"
                    )
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"Runtime archive file has no content: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
                target.chmod(member.mode & 0o777)
        if not (resolved_destination / "__init__.py").is_file():
            raise ValueError("Harness snapshot does not contain __init__.py")
        return RuntimeSnapshot(
            commit=resolved_commit,
            tree=tree,
            source_sha256=source_sha256,
        )

    def materialize_atomic(self, commit: str, destination: Path) -> RuntimeSnapshot:
        """Publish one verified runtime directory with recoverable staging."""
        resolved = destination.expanduser().resolve()
        if resolved.exists():
            try:
                self.verify_materialized(commit, resolved)
            except ValueError:
                index = 1
                while True:
                    failed = resolved.with_name(f"{resolved.name}-incomplete-{index:02d}")
                    if not failed.exists():
                        resolved.rename(failed)
                        break
                    index += 1
            else:
                _, source_sha256 = _archive_bytes(self.path, commit)
                return RuntimeSnapshot(
                    commit=_git_text(self.path, "rev-parse", f"{commit}^{{commit}}"),
                    tree=_git_text(self.path, "rev-parse", f"{commit}^{{tree}}"),
                    source_sha256=source_sha256,
                )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        staging = resolved.with_name(f".{resolved.name}.tmp-{uuid.uuid4().hex}")
        snapshot = self.materialize(commit, staging)
        try:
            self.verify_materialized(commit, staging)
            os.replace(staging, resolved)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return snapshot

    def changed_files(self, base_commit: str, head_commit: str) -> tuple[str, ...]:
        """Return files changed between two committed runtime snapshots."""
        output = _git_text(
            self.path,
            "diff",
            "--name-only",
            f"{base_commit}..{head_commit}",
        )
        return tuple(line for line in output.splitlines() if line)

    def verify_materialized(self, commit: str, destination: Path) -> None:
        """Require a materialized runtime tree to match its committed bytes."""
        with tempfile.TemporaryDirectory(prefix="perfrace-runtime-verify-") as directory:
            expected = Path(directory) / "runtime"
            self.materialize(commit, expected)
            expected_hash = hash_source_tree(expected)
        actual_hash = hash_source_tree(destination)
        if actual_hash != expected_hash:
            raise ValueError(f"Materialized runtime differs from commit {commit}: {destination}")
