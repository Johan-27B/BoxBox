"""Export Discovery project snapshots as Filter candidate records."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REVISION_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
REQUIRED_STRING_FIELDS = (
    "repo_url",
    "discovery_channel",
    "discovered_at",
    "observed_revision",
    "default_branch",
    "signal_kind",
    "signal_url",
)


def validate_candidate(candidate: dict[str, Any]) -> None:
    """Validate the required fields of one candidate record."""
    for field in REQUIRED_STRING_FIELDS:
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"candidate {field} must be a non-empty string")
    if candidate["discovery_channel"] not in {"ai-signals", "project-list"}:
        raise ValueError("candidate discovery_channel must be 'ai-signals' or 'project-list'")
    if not REVISION_PATTERN.fullmatch(candidate["observed_revision"]):
        raise ValueError("candidate observed_revision must be a Git object ID")

    repo_url = urllib.parse.urlparse(candidate["repo_url"])
    repo_parts = [part for part in repo_url.path.split("/") if part]
    if (
        repo_url.scheme != "https"
        or repo_url.netloc.lower() != "github.com"
        or len(repo_parts) != 2
    ):
        raise ValueError("candidate repo_url must be an https GitHub repository URL")

    signal_kind = candidate["signal_kind"]
    if signal_kind not in {"pull_request", "branch"}:
        raise ValueError("candidate signal_kind must be pull_request or branch")
    signal_url = urllib.parse.urlparse(candidate["signal_url"])
    signal_parts = [part for part in signal_url.path.split("/") if part]
    expected_segment = "pull" if signal_kind == "pull_request" else "tree"
    expected_length = 4 if signal_kind == "pull_request" else None
    if (
        signal_url.scheme != "https"
        or signal_url.netloc.lower() != "github.com"
        or signal_parts[:2] != repo_parts
        or (expected_length is not None and len(signal_parts) != expected_length)
        or (signal_kind == "branch" and len(signal_parts) < 4)
        or signal_parts[2] != expected_segment
    ):
        raise ValueError("candidate signal_url does not match its repository and kind")

    discovered_at = datetime.fromisoformat(candidate["discovered_at"].replace("Z", "+00:00"))
    if discovered_at.tzinfo is None or discovered_at.utcoffset() is None:
        raise ValueError("candidate discovered_at must include a UTC offset")

    if candidate.get("description") is not None and not isinstance(candidate["description"], str):
        raise ValueError("candidate description must be a string or null")
    topics = candidate.get("topics")
    if not isinstance(topics, list) or not all(isinstance(item, str) for item in topics):
        raise ValueError("candidate topics must be a list of strings")
    for field in ("stargazer_count", "disk_usage_kb"):
        value = candidate.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"candidate {field} must be a non-negative integer")
    for field in ("primary_language", "license_spdx", "created_at", "pushed_at"):
        value = candidate.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"candidate {field} must be a string or null")
    for field in ("is_fork", "is_archived", "is_disabled"):
        if not isinstance(candidate.get(field), bool):
            raise ValueError(f"candidate {field} must be a boolean")
    actors = candidate.get("signal_actors")
    if (
        not isinstance(actors, list)
        or not actors
        or not all(isinstance(actor, str) and actor for actor in actors)
    ):
        raise ValueError("candidate signal_actors must be a non-empty string list")
    authorship_window = candidate.get("authorship_window")
    if not isinstance(authorship_window, dict):
        raise ValueError("candidate authorship_window must be an object")
    parsed_window: dict[str, datetime] = {}
    for field in ("start_at", "end_at"):
        value = authorship_window.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"candidate authorship_window {field} must be a string")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
            raise ValueError(f"candidate authorship_window {field} must use UTC")
        parsed_window[field] = parsed
    if parsed_window["end_at"] <= parsed_window["start_at"]:
        raise ValueError("candidate authorship_window end_at must be after start_at")


def _read_index(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path} line {line_number}: {exc.msg}") from exc
            if not isinstance(row, dict) or not isinstance(row.get("repo"), str):
                raise ValueError(f"{path} line {line_number} must contain a repository")
            repo = row["repo"]
            if repo in records:
                raise ValueError(f"duplicate repository in {path}: {repo}")
            records[repo] = row
    return records


def export_candidates(
    harvest_path: Path,
    metadata_path: Path,
    output_path: Path,
    *,
    discovered_at: datetime,
    authorship_start_at: datetime,
    authorship_end_at: datetime,
) -> tuple[int, int]:
    """Write sorted candidates and return ``(exported, excluded)``."""
    if discovered_at.tzinfo is None or discovered_at.utcoffset() is None:
        raise ValueError("discovered_at must include a UTC offset")
    discovered_text = (
        discovered_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    if authorship_start_at.tzinfo is None or authorship_start_at.utcoffset() is None:
        raise ValueError("authorship_start_at must include a UTC offset")
    if authorship_end_at.tzinfo is None or authorship_end_at.utcoffset() is None:
        raise ValueError("authorship_end_at must include a UTC offset")
    authorship_start_text = (
        authorship_start_at.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    authorship_end_text = (
        authorship_end_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    harvest = _read_index(harvest_path)
    metadata_rows = _read_index(metadata_path)
    candidates_by_url: dict[str, dict[str, Any]] = {}
    excluded = 0

    for repo, seed in harvest.items():
        metadata_row = metadata_rows.get(repo)
        metadata = metadata_row.get("metadata") if metadata_row else None
        if not isinstance(metadata, dict):
            excluded += 1
            continue
        required_snapshot = (
            metadata.get("repo_url"),
            metadata.get("default_branch"),
            metadata.get("observed_revision"),
        )
        if not all(isinstance(value, str) and value for value in required_snapshot):
            excluded += 1
            continue

        signal_kind = seed.get("signal_kind")
        source_url = seed.get("signal_url")
        if not isinstance(source_url, str):
            raise ValueError(f"harvest signal URL is missing for {repo}")
        source_parts = [part for part in urllib.parse.urlparse(source_url).path.split("/") if part]
        if signal_kind == "pull_request":
            signal_ref = source_parts[-1]
            signal_segment = "pull"
        elif signal_kind == "branch":
            signal_ref = "/".join(source_parts[3:])
            signal_segment = "tree"
        else:
            raise ValueError(f"harvest signal kind is invalid for {repo}")
        signal_url = f"{str(metadata['repo_url']).rstrip('/')}/{signal_segment}/{signal_ref}"
        candidate = {
            "repo_url": metadata["repo_url"],
            "discovery_channel": "ai-signals",
            "discovered_at": discovered_text,
            "observed_revision": metadata["observed_revision"],
            "default_branch": metadata["default_branch"],
            "description": metadata.get("description"),
            "topics": metadata.get("topics") or [],
            "stargazer_count": metadata.get("stargazer_count", 0),
            "primary_language": metadata.get("primary_language"),
            "license_spdx": metadata.get("license_spdx"),
            "disk_usage_kb": metadata.get("disk_usage_kb", 0),
            "created_at": metadata.get("created_at"),
            "pushed_at": metadata.get("pushed_at"),
            "is_fork": metadata.get("is_fork", False),
            "is_archived": metadata.get("is_archived", False),
            "is_disabled": metadata.get("is_disabled", False),
            "signal_kind": signal_kind,
            "signal_url": signal_url,
            "signal_actors": seed.get("signal_actors"),
            "authorship_window": {
                "start_at": authorship_start_text,
                "end_at": authorship_end_text,
            },
        }
        validate_candidate(candidate)
        repo_url = candidate["repo_url"]
        existing = candidates_by_url.get(repo_url)
        if existing is None:
            candidates_by_url[repo_url] = candidate
        else:
            excluded += 1
            if candidate["signal_url"] < existing["signal_url"]:
                candidates_by_url[repo_url] = candidate

    candidates = list(candidates_by_url.values())
    candidates.sort(key=lambda item: (-item["stargazer_count"], item["repo_url"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            for candidate in candidates:
                handle.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(candidates), excluded
