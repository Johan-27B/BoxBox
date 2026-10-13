"""Prepare independent harness sources from a directory or a Git revision."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterator


def _generated(name: str) -> bool:
    return name in {".git", "__pycache__"} or name.endswith(".pyc")


def _files(source: Path) -> Iterator[Path]:
    """Visit portable regular files, excluding version-control and bytecode data."""
    for directory, dirs, files in os.walk(source):
        dirs[:] = sorted(name for name in dirs if not _generated(name))
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"Harness sources cannot contain symlinks: {name}")
        for name in sorted(files):
            if _generated(name):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Harness sources require regular files: {path}")
            yield path


def _git(source: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def _export(source: Path, commit: str, destination: Path) -> None:
    # Read actual Git objects, not checkout filters or export-subst attributes.
    listing = _git(source, "ls-tree", "-rz", "--full-tree", commit)
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        relative = PurePosixPath(raw_path.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe path in harness revision")
        if any(_generated(part) for part in relative.parts):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Harness revision requires regular files: {relative}")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git(source, "cat-file", "blob", object_id))
        target.chmod(0o755 if mode == "100755" else 0o644)


def _copy_files(source: Path, destination: Path) -> None:
    for path in _files(source):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            raise IsADirectoryError(target)
        shutil.copy2(path, target)


def materialize(
    source: Path,
    destination: Path,
    *,
    revision: str | None = None,
    overlay: Path | None = None,
) -> Path:
    """Copy a source tree or committed revision without modifying its origin.

    With ``revision``, source must be the root of a working Git repository;
    dirty files do not affect the result. The copy has no inherited Git history.
    Existing destinations are never overwritten, and failed copies are removed.
    An explicit overlay copies additional files by relative path, replacing
    matching files in the new copy only.
    This function has no knowledge of models, prompts, skills, or runtime layout.
    """
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().absolute()
    if not source.is_dir():
        raise ValueError(f"Harness source is not a directory: {source}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Harness destination already exists: {destination}")
    if destination.resolve().is_relative_to(source):
        raise ValueError("Harness destination must be outside its source")
    if overlay is not None:
        overlay = overlay.expanduser().resolve(strict=True)
        if not overlay.is_dir():
            raise ValueError(f"Overlay is not a directory: {overlay}")
        if destination.resolve().is_relative_to(overlay):
            raise ValueError("Harness destination must be outside its overlay")
    commit = None
    if revision is not None:
        root = Path(_git(source, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        if root != source:
            raise ValueError("A revision must be selected from the Git repository root")
        commit = _git(
            source, "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"
        ).decode().strip()
    destination.mkdir(parents=True, exist_ok=False)
    try:
        if commit is not None:
            _export(source, commit, destination)
        else:
            _copy_files(source, destination)
        if overlay is not None:
            _copy_files(overlay, destination)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


def fingerprint(source: Path) -> str:
    """Identify file paths, bytes, and executable bits, independent of location."""
    source = source.expanduser().resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"Harness source is not a directory: {source}")
    digest = hashlib.sha256()
    for path in sorted(_files(source)):
        digest.update(path.relative_to(source).as_posix().encode() + b"\0")
        digest.update(b"x" if path.stat().st_mode & 0o111 else b"-")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
