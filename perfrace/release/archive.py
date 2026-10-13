"""Deterministic task-package archives."""

from __future__ import annotations

import gzip
import hashlib
import os
import posixpath
import shutil
import stat
import tarfile
from contextlib import contextmanager
from dataclasses import dataclass
from io import BufferedReader
from pathlib import Path, PurePosixPath
from typing import Iterator

from harbor.models.task.paths import TaskPaths
from .packager import TaskPackager as Packager


@dataclass(frozen=True)
class TaskArchive:
    """Identity and transport metadata for one task archive."""

    path: Path
    content_hash: str
    archive_digest: str
    file_count: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_link_target(task_dir: Path, path: Path) -> Path:
    link_target = os.readlink(path)
    if Path(link_target).is_absolute():
        raise ValueError(f"task package symlink must be relative: {path}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(task_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(f"task package symlink escapes the task root: {path}") from exc
    if not (resolved.is_file() or resolved.is_dir()):
        raise ValueError(f"task package symlink has an unsupported target: {path}")
    return resolved


def _package_symlinks(task_dir: Path) -> list[Path]:
    paths = TaskPaths(task_dir)
    single_files = (
        paths.config_path,
        paths.instruction_path,
        paths.readme_path,
        task_dir / "report.md",
        paths.gitignore_path,
    )
    directories = (
        paths.environment_dir,
        paths.tests_dir,
        paths.solution_dir,
        paths.steps_dir,
    )
    for path in single_files:
        if path.is_symlink():
            raise ValueError(f"task packages cannot contain symlinks: {path}")
    links: list[Path] = []
    for path in directories:
        if path.is_symlink():
            raise ValueError(f"task package root cannot be a symlink: {path}")
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_symlink():
                    links.append(child)
    return sorted(set(links), key=lambda path: path.relative_to(task_dir).as_posix())


@contextmanager
def _open_regular(task_dir: Path, path: Path) -> Iterator[tuple[BufferedReader, os.stat_result]]:
    relative = path.relative_to(task_dir)
    root_fd = os.open(
        task_dir,
        os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    directory_fd = root_fd
    opened_directories: list[int] = []
    file_fd = -1
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            opened_directories.append(next_fd)
            directory_fd = next_fd
        file_fd = os.open(
            relative.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"task package entry is not a regular file: {path}")
        with os.fdopen(file_fd, "rb") as handle:
            file_fd = -1
            yield handle, metadata
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        for descriptor in reversed(opened_directories):
            os.close(descriptor)
        os.close(root_fd)


def _hash_open_file(handle: BufferedReader) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _open_package_file(
    task_dir: Path,
    path: Path,
) -> Iterator[tuple[BufferedReader, os.stat_result]]:
    target = _safe_link_target(task_dir, path) if path.is_symlink() else path
    if not target.is_file():
        raise ValueError(f"task package file symlink resolves to a directory: {path}")
    with _open_regular(task_dir, target) as opened:
        yield opened


def _package_content_hash(task_dir: Path, files: list[Path]) -> str:
    outer = hashlib.sha256()
    for path in files:
        relative = path.relative_to(task_dir).as_posix()
        with _open_package_file(task_dir, path) as (handle, _):
            file_hash = _hash_open_file(handle)
        outer.update(f"{relative}\0{file_hash}\n".encode())
    return outer.hexdigest()


def create_task_archive(task_dir: Path, destination: Path) -> TaskArchive:
    """Create a byte-reproducible gzip archive from Harbor publishable files."""
    task_dir = task_dir.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    links = _package_symlinks(task_dir)
    files = Packager.collect_files(task_dir)
    entries = sorted(
        set(files) | set(links),
        key=lambda path: path.relative_to(task_dir).as_posix(),
    )
    content_hash = _package_content_hash(task_dir, files)
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for path in entries:
                    relative = path.relative_to(task_dir).as_posix()
                    if path.is_symlink():
                        metadata = path.lstat()
                        info = tarfile.TarInfo(relative)
                        info.type = tarfile.SYMTYPE
                        info.linkname = os.readlink(path)
                        info.mode = stat.S_IMODE(metadata.st_mode)
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = 0
                        archive.addfile(info)
                        continue
                    with _open_regular(task_dir, path) as (handle, metadata):
                        info = tarfile.TarInfo(relative)
                        info.size = metadata.st_size
                        info.mode = stat.S_IMODE(metadata.st_mode)
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = 0
                        archive.addfile(info, handle)
        raw.flush()
        os.fsync(raw.fileno())
    return TaskArchive(
        path=destination,
        content_hash=content_hash,
        archive_digest=_sha256(destination),
        file_count=len(entries),
    )


def extract_task_archive(archive_path: Path, destination: Path) -> int:
    """Extract a task archive while rejecting links and path traversal."""
    destination.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        symlink_names = {member.name for member in members if member.issym()}
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                not (member.isfile() or member.issym())
                or relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or member.name in seen
            ):
                raise ValueError(f"unsafe task archive entry: {member.name}")
            seen.add(member.name)
            if member.issym():
                link = PurePosixPath(member.linkname)
                combined = posixpath.normpath((relative.parent / link).as_posix())
                if link.is_absolute() or combined == ".." or combined.startswith("../"):
                    raise ValueError(f"unsafe task archive symlink: {member.name}")
            elif any(
                PurePosixPath(parent).as_posix() in symlink_names
                for parent in relative.parents
                if parent != PurePosixPath(".")
            ):
                raise ValueError(f"task archive entry traverses a symlink: {member.name}")
        for member in members:
            relative = PurePosixPath(member.name)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.issym():
                target.symlink_to(member.linkname)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"missing task archive content: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)
        for member in members:
            if not member.issym():
                continue
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if not target.is_symlink() or os.readlink(target) != member.linkname:
                raise ValueError(f"task archive symlink was not preserved: {member.name}")
    return len(members)


def verify_task_archive(
    archive_path: Path,
    destination: Path,
    *,
    expected_content_hash: str,
    expected_archive_digest: str,
) -> int:
    """Extract and verify one downloaded task archive."""
    if _sha256(archive_path) != expected_archive_digest:
        raise ValueError("pulled task archive digest does not match the published archive")
    entry_count = extract_task_archive(archive_path, destination)
    files = Packager.collect_files(destination)
    content_hash = _package_content_hash(destination.resolve(), files)
    if content_hash != expected_content_hash:
        raise ValueError("pulled task package content hash does not match the source package")
    return entry_count
