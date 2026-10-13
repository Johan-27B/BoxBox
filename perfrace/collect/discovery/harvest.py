"""Discover projects from known AI coding-bot GitHub events."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from ._constants import CLICKHOUSE_PLAY_URL

REPO_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")


def _clickhouse_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _clickhouse_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Discovery timestamps must include a UTC offset")
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def load_bot_accounts(path: Path) -> tuple[str, ...]:
    """Load a non-empty, duplicate-free bot-account list."""
    accounts = tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not accounts:
        raise ValueError(f"bot-account configuration is empty: {path}")
    duplicates = sorted(account for account in set(accounts) if accounts.count(account) > 1)
    if duplicates:
        raise ValueError(f"duplicate bot accounts in {path}: " + ", ".join(duplicates))
    return accounts


def bot_config_sha256(path: Path) -> str:
    """Return the SHA-256 fingerprint of the bot-account configuration."""
    accounts = load_bot_accounts(path)
    normalized = "\n".join(accounts) + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_harvest_query(
    bot_accounts: tuple[str, ...],
    start_at: datetime,
    end_at: datetime,
) -> str:
    """Build the ClickHouse project-discovery query."""
    if not bot_accounts:
        raise ValueError("at least one bot account is required")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    bot_values = ",".join(f"'{_clickhouse_quote(account)}'" for account in bot_accounts)
    start_text = _clickhouse_time(start_at)
    end_text = _clickhouse_time(end_at)
    weight = "tuple(created_at, event_type, number, ref)"
    return f"""
SELECT
    repo_name AS repo,
    arraySort(groupUniqArray(actor_login)) AS signal_actors,
    argMax(
        if(event_type = 'PullRequestEvent', 'pull_request', 'branch'),
        {weight}
    ) AS signal_kind,
    argMax(
        if(
            event_type = 'PullRequestEvent',
            toString(number),
            replaceOne(ref, 'refs/heads/', '')
        ),
        {weight}
    ) AS signal_ref
FROM github_events
WHERE created_at >= toDateTime('{start_text}', 'UTC')
  AND created_at < toDateTime('{end_text}', 'UTC')
  AND actor_login IN ({bot_values})
  AND repo_name != ''
  AND (
        (event_type = 'PullRequestEvent' AND action = 'opened' AND number > 0)
        OR
        (event_type = 'PushEvent' AND startsWith(ref, 'refs/heads/'))
      )
GROUP BY repo_name
ORDER BY repo_name
FORMAT JSONEachRow
""".strip()


def _project_record(row: object) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("ClickHouse harvest row must be a JSON object")
    repo = row.get("repo")
    signal_kind = row.get("signal_kind")
    signal_ref = row.get("signal_ref")
    signal_actors = row.get("signal_actors")
    if not isinstance(repo, str) or not REPO_PATTERN.fullmatch(repo):
        raise ValueError(f"invalid repository in ClickHouse harvest row: {repo!r}")
    if signal_kind == "pull_request":
        try:
            number = int(signal_ref)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid pull request reference for {repo}") from exc
        if number <= 0:
            raise ValueError(f"invalid pull request reference for {repo}")
        signal_url = f"https://github.com/{repo}/pull/{number}"
    elif signal_kind == "branch":
        if not isinstance(signal_ref, str) or not signal_ref.strip():
            raise ValueError(f"invalid branch reference for {repo}")
        branch = urllib.parse.quote(signal_ref.strip(), safe="/-._~")
        signal_url = f"https://github.com/{repo}/tree/{branch}"
    else:
        raise ValueError(f"invalid signal kind for {repo}: {signal_kind!r}")
    if (
        not isinstance(signal_actors, list)
        or not signal_actors
        or not all(isinstance(actor, str) and actor for actor in signal_actors)
    ):
        raise ValueError(f"invalid signal actors for {repo}")
    return {
        "repo": repo,
        "signal_actors": sorted(set(signal_actors)),
        "signal_kind": signal_kind,
        "signal_url": signal_url,
    }


def harvest_projects(
    output_path: Path,
    *,
    bot_accounts: tuple[str, ...],
    start_at: datetime,
    end_at: datetime,
) -> int:
    """Write one latest GitHub evidence reference per discovered project."""
    query = build_harvest_query(bot_accounts, start_at, end_at)
    try:
        response = requests.post(
            CLICKHOUSE_PLAY_URL,
            data=query.encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=300,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"ClickHouse harvest request failed: {exc}") from exc
    if response.status_code != 200:
        raise RuntimeError(
            f"ClickHouse harvest failed: HTTP {response.status_code}: {response.text[:300]}"
        )

    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(response.text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid ClickHouse JSON on line {line_number}: {exc.msg}") from exc
        record = _project_record(row)
        if record["repo"] in records:
            raise ValueError(f"duplicate repository in ClickHouse output: {record['repo']}")
        records[record["repo"]] = record

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            for repo in sorted(records):
                handle.write(json.dumps(records[repo], ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(records)


def read_harvest_repos(path: Path) -> list[str]:
    """Return the repository names in one harvested project file."""
    repos: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid harvest JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(row, dict) or not isinstance(row.get("repo"), str):
                raise ValueError(f"harvest line {line_number} must contain a repository")
            repos.append(row["repo"])
    if len(set(repos)) != len(repos):
        raise ValueError(f"harvest file contains duplicate repositories: {path}")
    return repos
