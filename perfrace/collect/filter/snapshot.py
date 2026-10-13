"""Deterministic bounded evidence snapshots for Filter judgments."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ._constants import (
    MAX_FILE_BYTES,
    MAX_LICENSE_BYTES,
    MAX_README_BYTES,
    MAX_SNAPSHOT_BYTES,
    MAX_TREE_PATHS_IN_PROMPT,
)


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode("utf-8", errors="ignore"), True


def _serialized_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _tree_path_key(path: str) -> tuple[int, int, int, str]:
    parts = path.split("/")
    preferred_roots = {
        "src",
        "lib",
        "app",
        "apps",
        "packages",
        "crates",
        "cmd",
        "server",
        "client",
        "docs",
        "examples",
    }
    return (
        len(parts),
        0 if parts[0].lower() in preferred_roots else 1,
        sum(part.startswith(".") for part in parts),
        path,
    )


def build_snapshot(
    candidate: dict[str, Any],
    repository_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Select, truncate, and hash the evidence sent to the Filter judge."""
    tree = repository_evidence["tree"]
    ordered_paths = sorted(tree["paths"], key=_tree_path_key)
    licenses: list[dict[str, Any]] = []
    remaining_license_bytes = MAX_LICENSE_BYTES
    for license_data in repository_evidence["licenses"]:
        if remaining_license_bytes <= 0:
            break
        license_text, license_truncated = _truncate_text(
            license_data["text"],
            remaining_license_bytes,
        )
        used_bytes = len(license_text.encode("utf-8"))
        remaining_license_bytes -= used_bytes
        licenses.append(
            {
                "path": license_data["path"],
                "spdx": license_data["spdx"],
                "source_url": license_data["source_url"],
                "text": license_text,
                "text_truncated": license_truncated,
            }
        )
    snapshot: dict[str, Any] = {
        "repo_url": candidate["repo_url"],
        "candidate": candidate,
        "repository": {
            "name": repository_evidence["repository"],
            "revision": repository_evidence["revision"],
        },
        "tree": {
            "entry_count": tree["entry_count"],
            "tracked_bytes": tree["tracked_bytes"],
            "paths": list(ordered_paths[:MAX_TREE_PATHS_IN_PROMPT]),
            "paths_truncated": len(tree["paths"]) > MAX_TREE_PATHS_IN_PROMPT,
        },
        "licenses": licenses,
        "files": [],
        "file_errors": repository_evidence.get("file_errors", []),
    }

    while snapshot["tree"]["paths"] and len(_serialized_bytes(snapshot)) > MAX_SNAPSHOT_BYTES:
        snapshot["tree"]["paths"] = snapshot["tree"]["paths"][
            : len(snapshot["tree"]["paths"]) // 2
        ]
        snapshot["tree"]["paths_truncated"] = True

    readme_seen = False
    for file_data in repository_evidence.get("files", []):
        path = file_data["path"]
        is_readme = path.lower().rsplit("/", 1)[-1].startswith("readme")
        limit = MAX_README_BYTES if is_readme and not readme_seen else MAX_FILE_BYTES
        readme_seen = readme_seen or is_readme
        text, truncated = _truncate_text(file_data["text"], limit)
        selected = {
            "path": path,
            "source_url": file_data["source_url"],
            "text": text,
            "text_truncated": truncated,
        }
        snapshot["files"].append(selected)
        if len(_serialized_bytes(snapshot)) > MAX_SNAPSHOT_BYTES:
            snapshot["files"].pop()
            break

    encoded = _serialized_bytes(snapshot)
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"mandatory Filter snapshot evidence exceeds {MAX_SNAPSHOT_BYTES} bytes")
    snapshot["snapshot_sha256"] = hashlib.sha256(encoded).hexdigest()
    snapshot["snapshot_bytes"] = len(encoded)
    return snapshot
