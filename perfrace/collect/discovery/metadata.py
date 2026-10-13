"""Fetch fixed GitHub repository snapshots for discovered projects."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from ..utils._constants import GITHUB_API
from ..utils.tokens import TokenPool


_REPOSITORY_FIELDS = """
    nameWithOwner
    url
    description
    stargazerCount
    primaryLanguage { name }
    licenseInfo { spdxId }
    isFork
    isArchived
    isDisabled
    diskUsage
    createdAt
    pushedAt
    repositoryTopics(first: 20) {
      nodes { topic { name } }
    }
    defaultBranchRef {
      name
      target {
        ... on Commit { oid }
      }
    }
"""


def _build_query(repos: list[str]) -> str:
    fields: list[str] = []
    for index, repo in enumerate(repos):
        try:
            owner, name = repo.split("/", 1)
        except ValueError as exc:
            raise ValueError(f"invalid repository name: {repo!r}") from exc
        fields.append(
            f"  r{index}: repository("
            f"owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{"
            f"{_REPOSITORY_FIELDS}  }}"
        )
    return "query {\n" + "\n".join(fields) + "\n}"


def _fetch_batch(
    pool: TokenPool,
    repos: list[str],
    *,
    max_retries: int = 3,
) -> dict[str, dict[str, Any] | None]:
    query = _build_query(repos)
    for attempt in range(max_retries):
        token_index, token = pool.acquire_blocking("rest")
        headers = pool.auth_headers(token)
        headers["Content-Type"] = "application/json"
        try:
            response = requests.post(
                f"{GITHUB_API}/graphql",
                headers=headers,
                json={"query": query},
                timeout=30,
            )
        except requests.RequestException:
            if attempt + 1 == max_retries:
                raise
            time.sleep(2**attempt)
            continue
        pool.report_response(token_index, response, "rest")
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError("GitHub GraphQL response was not JSON") from exc
            errors = payload.get("errors") or []
            if not isinstance(errors, list):
                raise RuntimeError("GitHub GraphQL errors must be a list")
            fatal_errors = [
                error
                for error in errors
                if not isinstance(error, dict) or error.get("type") != "NOT_FOUND"
            ]
            if fatal_errors:
                first_error = fatal_errors[0]
                message = first_error.get("message") if isinstance(first_error, dict) else None
                raise RuntimeError(
                    f"GitHub GraphQL returned an error: {message or 'unknown error'}"
                )
            data = payload.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("GitHub GraphQL response did not contain data")
            return {repo: data.get(f"r{index}") for index, repo in enumerate(repos)}
        if response.status_code in {403, 429, 502, 503} and attempt + 1 < max_retries:
            time.sleep(2**attempt)
            continue
        raise RuntimeError(
            f"GitHub GraphQL request failed: HTTP {response.status_code}: {response.text[:300]}"
        )
    raise RuntimeError("GitHub GraphQL request exhausted retries")


def _normalize_metadata(repo: str, raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"GitHub metadata for {repo} must be an object or null")
    topics_connection = raw.get("repositoryTopics") or {}
    topic_nodes = topics_connection.get("nodes") or []
    topics = sorted(
        {
            topic_name
            for node in topic_nodes
            if isinstance(node, dict)
            for topic in [node.get("topic")]
            if isinstance(topic, dict)
            for topic_name in [topic.get("name")]
            if isinstance(topic_name, str) and topic_name
        }
    )
    default_branch = raw.get("defaultBranchRef") or {}
    target = default_branch.get("target") or {}
    language = raw.get("primaryLanguage") or {}
    license_info = raw.get("licenseInfo") or {}
    return {
        "repo": raw.get("nameWithOwner"),
        "repo_url": raw.get("url"),
        "description": raw.get("description"),
        "topics": topics,
        "stargazer_count": int(raw.get("stargazerCount") or 0),
        "primary_language": language.get("name"),
        "license_spdx": license_info.get("spdxId"),
        "disk_usage_kb": int(raw.get("diskUsage") or 0),
        "created_at": raw.get("createdAt"),
        "pushed_at": raw.get("pushedAt"),
        "is_fork": bool(raw.get("isFork")),
        "is_archived": bool(raw.get("isArchived")),
        "is_disabled": bool(raw.get("isDisabled")),
        "default_branch": default_branch.get("name"),
        "observed_revision": target.get("oid"),
    }


def fetch_project_metadata(
    pool: TokenPool,
    repos: list[str],
    output_path: Path,
    *,
    batch_size: int = 50,
) -> tuple[int, int]:
    """Persist a terminal metadata result for every discovered repository."""
    if not 1 <= batch_size <= 50:
        raise ValueError("metadata batch_size must be between 1 and 50")
    if len(set(repos)) != len(repos):
        raise ValueError("metadata input contains duplicate repositories")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any] | None] = {}
    if output_path.exists():
        with output_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid metadata JSON on line {line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(row, dict) or not isinstance(row.get("repo"), str):
                    raise ValueError(f"metadata line {line_number} must contain a repository")
                repo = row["repo"]
                if repo in results:
                    raise ValueError(f"duplicate metadata row for {repo}")
                metadata = row.get("metadata")
                if metadata is not None and not isinstance(metadata, dict):
                    raise ValueError(f"metadata for {repo} must be an object or null")
                results[repo] = metadata

    todo = [repo for repo in repos if repo not in results]
    with output_path.open("a", encoding="utf-8") as handle:
        for offset in range(0, len(todo), batch_size):
            batch = todo[offset : offset + batch_size]
            fetched = _fetch_batch(pool, batch)
            for repo in batch:
                metadata = _normalize_metadata(repo, fetched.get(repo))
                handle.write(
                    json.dumps(
                        {"repo": repo, "metadata": metadata},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
                results[repo] = metadata
            handle.flush()
            os.fsync(handle.fileno())

    missing = [repo for repo in repos if repo not in results]
    if missing:
        raise RuntimeError(f"metadata is incomplete for {len(missing)} repositories")
    valid = sum(results[repo] is not None for repo in repos)
    return valid, len(repos) - valid
