"""Deterministic release-catalog synchronization."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from dataclasses import asdict
from pathlib import Path

from perfrace.curate.report import read_text, write_text
from perfrace.release.publisher import ReleaseRecord


def _catalog_payload(instance_root: Path) -> dict[str, object]:
    records: dict[str, dict[str, object]] = {}
    for path in sorted((instance_root / ".releases").glob("*.json")):
        raw = json.loads(read_text(path))
        record = ReleaseRecord(**raw)
        if path.stem != record.instance:
            raise ValueError(f"release record filename does not match {record.instance}")
        records[record.instance] = asdict(record)
    return {"schema_version": 1, "instances": records}


def sync_release_catalog(instance_root: Path, output: Path) -> set[str]:
    """Atomically rebuild a catalog and return its active instance IDs."""
    root = instance_root.expanduser().resolve()
    releases = root / ".releases"
    releases.mkdir(parents=True, exist_ok=True)
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(
        releases / ".catalog.lock",
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o666,
    )
    try:
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise ValueError("release catalog lock is not a regular file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        for _ in range(3):
            payload = _catalog_payload(root)
            content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            try:
                current = read_text(destination)
            except FileNotFoundError:
                current = None
            if current != content:
                write_text(destination, content)
            if _catalog_payload(root) == payload:
                instances = payload["instances"]
                assert isinstance(instances, dict)
                return set(instances)
        raise RuntimeError("release records changed repeatedly during catalog export")
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
