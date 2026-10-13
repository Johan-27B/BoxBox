"""Safe read-only filesystem browsing for one session workspace."""

from __future__ import annotations

import errno
import os
import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterator

from markdown_it import MarkdownIt

MAX_PREVIEW_BYTES = 1024 * 1024
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})


def render_markdown(content: str) -> str:
    """Render safe Markdown with raw HTML disabled."""
    renderer = MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
            "typographer": False,
        },
    )
    renderer.enable("table")
    renderer.enable("strikethrough")
    return renderer.render(content)


def _path_components(relative: str) -> tuple[str, ...]:
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("path escapes the session workspace")
    return tuple(part for part in path.parts if part not in {"", "."})


def _open_component(parent_fd: int, name: str, *, directory: bool) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if directory:
        flags |= os.O_DIRECTORY
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("symlinks are not browsable") from exc
        raise


@contextmanager
def _open_directory(root: Path, relative: str) -> Iterator[int]:
    """Open a directory by descriptor without following path-component symlinks."""
    descriptors: list[int] = []
    try:
        try:
            root_fd = os.open(
                root,
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError("workspace root must not be a symlink") from exc
            raise
        descriptors.append(root_fd)
        current_fd = root_fd
        for component in _path_components(relative):
            current_fd = _open_component(current_fd, component, directory=True)
            descriptors.append(current_fd)
        yield current_fd
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _open_file(root: Path, relative: str) -> Iterator[int]:
    components = _path_components(relative)
    if not components:
        raise IsADirectoryError(relative)
    parent = "/".join(components[:-1])
    with _open_directory(root, parent) as directory_fd:
        file_fd = _open_component(directory_fd, components[-1], directory=False)
        try:
            mode = os.fstat(file_fd).st_mode
            if stat.S_ISDIR(mode):
                raise IsADirectoryError(relative)
            if not stat.S_ISREG(mode):
                raise ValueError("only regular files can be previewed")
            yield file_fd
        finally:
            os.close(file_fd)


def list_directory(root: Path, relative: str = "") -> dict[str, Any]:
    """Return one lazy directory level."""
    entries = []
    with _open_directory(root, relative) as directory_fd:
        for name in os.listdir(directory_fd):
            try:
                entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(entry_stat.st_mode):
                continue
            if stat.S_ISDIR(entry_stat.st_mode):
                entry_type = "directory"
            elif stat.S_ISREG(entry_stat.st_mode):
                entry_type = "file"
            else:
                continue
            entries.append(
                {
                    "name": name,
                    "path": (PurePosixPath(relative) / name).as_posix(),
                    "type": entry_type,
                    "size": entry_stat.st_size,
                    "modified": datetime.fromtimestamp(entry_stat.st_mtime, UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
    entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"]))
    return {"path": relative, "entries": entries}


def read_file_range(
    root: Path,
    relative: str,
    *,
    offset: int = 0,
    limit: int = 262_144,
) -> dict[str, Any]:
    """Return a bounded text range or binary-file metadata."""
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if limit <= 0 or limit > MAX_PREVIEW_BYTES:
        raise ValueError(f"limit must be between 1 and {MAX_PREVIEW_BYTES}")
    with _open_file(root, relative) as file_fd:
        size = os.fstat(file_fd).st_size
        os.lseek(file_fd, offset, os.SEEK_SET)
        data = os.read(file_fd, limit)
    binary = b"\0" in data
    next_offset = offset + len(data)
    eof = next_offset >= size
    return {
        "path": relative,
        "content": "" if binary else data.decode("utf-8", errors="replace"),
        "offset": offset,
        "nextOffset": next_offset,
        "eof": eof,
        "binary": binary,
        "truncated": not eof,
        "size": size,
    }
