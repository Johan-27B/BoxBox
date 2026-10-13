"""Measure recent AI-attributed commits for Filter survivors."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from ..utils._constants import GITHUB_API
from ..utils.tokens import TokenPool

SEARCH_PAGE_SIZE = 100
SEARCH_RESULT_LIMIT = 1000
MAX_QUERY_LENGTH = 240


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("authorship timestamps must include a UTC offset")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed.astimezone(UTC)


def load_coauthor_signatures(path: Path) -> tuple[str, ...]:
    """Load configured commit-message signatures."""
    signatures = tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not signatures:
        raise ValueError(f"co-author signature configuration is empty: {path}")
    if len(set(signatures)) != len(signatures):
        raise ValueError(f"co-author signature configuration has duplicates: {path}")
    return signatures


def coauthor_config_sha256(path: Path) -> str:
    """Return the normalized SHA-256 fingerprint of co-author signatures."""
    signatures = load_coauthor_signatures(path)
    normalized = "\n".join(signatures) + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_index(path: Path, key: str = "repo_url") -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path} line {line_number}: {exc.msg}") from exc
            if not isinstance(row, dict) or not isinstance(row.get(key), str):
                raise ValueError(f"{path} line {line_number} must contain {key}")
            value = row[key]
            if value in records:
                raise ValueError(f"duplicate {key} in {path}: {value}")
            records[value] = row
    return records


def _graphql_total_count(
    pool: TokenPool,
    *,
    repo: str,
    revision: str,
    start_at: datetime,
    end_at: datetime,
    max_retries: int = 3,
) -> int:
    owner, name = repo.split("/", 1)
    query = f"""
query {{
  repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
    object(oid: {json.dumps(revision)}) {{
      ... on Commit {{
        history(
          since: {json.dumps(_iso_utc(start_at))}
          until: {json.dumps(_iso_utc(end_at))}
        ) {{
          totalCount
        }}
      }}
    }}
  }}
}}
""".strip()
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
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(
                    f"GitHub GraphQL authorship query failed for {repo}: "
                    f"{payload['errors'][0].get('message', 'unknown error')}"
                )
            repository = (payload.get("data") or {}).get("repository") or {}
            commit = repository.get("object") or {}
            history = commit.get("history") or {}
            total = history.get("totalCount")
            if not isinstance(total, int) or total < 0:
                raise RuntimeError(f"GitHub returned no commit count for {repo}")
            return total
        if response.status_code in {403, 429, 502, 503} and attempt + 1 < max_retries:
            time.sleep(2**attempt)
            continue
        raise RuntimeError(
            f"GitHub GraphQL authorship query failed for {repo}: "
            f"HTTP {response.status_code}: {response.text[:300]}"
        )
    raise RuntimeError(f"GitHub GraphQL authorship query exhausted retries for {repo}")


def _actor_search_term(
    pool: TokenPool,
    actor: str,
    *,
    max_retries: int = 3,
) -> str:
    for attempt in range(max_retries):
        token_index, token = pool.acquire_blocking("rest")
        try:
            response = requests.get(
                f"{GITHUB_API}/users/{quote(actor, safe='')}",
                headers=pool.auth_headers(token),
                timeout=30,
            )
        except requests.RequestException:
            if attempt + 1 == max_retries:
                raise
            time.sleep(2**attempt)
            continue
        pool.report_response(token_index, response, "rest")
        if response.status_code == 200:
            payload = response.json()
            account_id = payload.get("id")
            login = payload.get("login")
            if not isinstance(account_id, int) or not isinstance(login, str):
                raise RuntimeError(f"GitHub returned an invalid actor record for {actor}")
            return f"author-email:{account_id}+{login}@users.noreply.github.com"
        if response.status_code == 404:
            return f"author-name:{json.dumps(actor)}"
        if response.status_code in {403, 429, 502, 503} and attempt + 1 < max_retries:
            time.sleep(2**attempt)
            continue
        raise RuntimeError(
            f"GitHub actor lookup failed for {actor}: "
            f"HTTP {response.status_code}: {response.text[:300]}"
        )
    raise RuntimeError(f"GitHub actor lookup exhausted retries for {actor}")


def _search_page(
    pool: TokenPool,
    query: str,
    page: int,
    *,
    max_retries: int = 3,
) -> tuple[list[dict[str, Any]], int]:
    for attempt in range(max_retries):
        token_index, token = pool.acquire_blocking("search")
        headers = pool.auth_headers(token)
        headers["Accept"] = "application/vnd.github.cloak-preview+json"
        try:
            response = requests.get(
                f"{GITHUB_API}/search/commits",
                headers=headers,
                params={
                    "q": query,
                    "per_page": SEARCH_PAGE_SIZE,
                    "page": page,
                },
                timeout=30,
            )
        except requests.RequestException:
            if attempt + 1 == max_retries:
                raise
            time.sleep(2**attempt)
            continue
        pool.report_response(token_index, response, "search")
        if response.status_code == 200:
            payload = response.json()
            items = payload.get("items") or []
            total = payload.get("total_count")
            if not isinstance(items, list) or not isinstance(total, int):
                raise RuntimeError("GitHub commit search returned an invalid payload")
            return items, total
        if response.status_code in {403, 429, 502, 503} and attempt + 1 < max_retries:
            time.sleep(2**attempt)
            continue
        raise RuntimeError(
            f"GitHub commit search failed: HTTP {response.status_code}: {response.text[:300]}"
        )
    raise RuntimeError("GitHub commit search exhausted retries")


def _signature_groups(
    signatures: tuple[str, ...],
    *,
    repo: str,
    start_at: datetime,
    end_at: datetime,
) -> list[tuple[str, ...]]:
    suffix = f" repo:{repo} committer-date:{_iso_utc(start_at)}..{_iso_utc(end_at)}"
    groups: list[tuple[str, ...]] = []
    current: list[str] = []
    for signature in signatures:
        candidate = [*current, signature]
        query = " OR ".join(json.dumps(item) for item in candidate) + suffix
        if len(query) <= MAX_QUERY_LENGTH:
            current = candidate
            continue
        if not current:
            raise ValueError(f"co-author signature is too long: {signature!r}")
        groups.append(tuple(current))
        current = [signature]
    if current:
        groups.append(tuple(current))
    return groups


def _search_query(
    terms: tuple[str, ...],
    *,
    repo: str,
    start_at: datetime,
    end_at: datetime,
) -> str:
    return (
        " OR ".join(terms)
        + f" repo:{repo} "
        + f"committer-date:{_iso_utc(start_at)}..{_iso_utc(end_at)}"
    )


def _search_matching_shas(
    pool: TokenPool,
    *,
    repo: str,
    terms: tuple[str, ...],
    start_at: datetime,
    end_at: datetime,
    expected_actor: str | None = None,
    expected_signatures: tuple[str, ...] = (),
) -> set[str]:
    pending: deque[tuple[datetime, datetime]] = deque([(start_at, end_at)])
    matches: set[str] = set()
    while pending:
        slice_start, slice_end = pending.popleft()
        query = _search_query(
            terms,
            repo=repo,
            start_at=slice_start,
            end_at=slice_end,
        )
        first_page, total = _search_page(pool, query, 1)
        if total > SEARCH_RESULT_LIMIT:
            midpoint = (slice_start + (slice_end - slice_start) / 2).replace(microsecond=0)
            if midpoint <= slice_start or midpoint >= slice_end:
                raise RuntimeError(
                    f"commit search exceeds {SEARCH_RESULT_LIMIT} results "
                    f"within one second for {repo}"
                )
            pending.append((slice_start, midpoint))
            pending.append((midpoint + timedelta(seconds=1), slice_end))
            continue
        items = list(first_page)
        page = 2
        page_limit = math.ceil(total / SEARCH_PAGE_SIZE)
        split_required = False
        while page <= page_limit:
            page_items, page_total = _search_page(pool, query, page)
            if page_total > SEARCH_RESULT_LIMIT:
                split_required = True
                break
            page_limit = max(
                page_limit,
                math.ceil(page_total / SEARCH_PAGE_SIZE),
            )
            items.extend(page_items)
            if len(page_items) < SEARCH_PAGE_SIZE:
                break
            page += 1
        if split_required:
            midpoint = (slice_start + (slice_end - slice_start) / 2).replace(microsecond=0)
            if midpoint <= slice_start or midpoint >= slice_end:
                raise RuntimeError(
                    f"commit search exceeds {SEARCH_RESULT_LIMIT} results "
                    f"within one second for {repo}"
                )
            pending.append((slice_start, midpoint))
            pending.append((midpoint + timedelta(seconds=1), slice_end))
            continue
        for item in items:
            sha = item.get("sha") if isinstance(item, dict) else None
            if not isinstance(sha, str) or not sha:
                raise RuntimeError(f"commit search returned an invalid SHA for {repo}")
            repository = item.get("repository") or {}
            full_name = repository.get("full_name") if isinstance(repository, dict) else None
            if not isinstance(full_name, str) or full_name.casefold() != repo.casefold():
                continue
            if expected_actor is not None:
                author = item.get("author") or {}
                login = author.get("login") if isinstance(author, dict) else None
                if not isinstance(login, str) or login.casefold() != expected_actor.casefold():
                    continue
            if expected_signatures:
                commit = item.get("commit") or {}
                message = commit.get("message") if isinstance(commit, dict) else None
                if not isinstance(message, str) or not any(
                    signature.casefold() in message.casefold() for signature in expected_signatures
                ):
                    continue
            matches.add(sha)
    return matches


def measure_authorship(
    pool: TokenPool,
    candidates: list[dict[str, Any]],
    output_path: Path,
    *,
    signatures: tuple[str, ...],
) -> tuple[int, int]:
    """Persist authorship metrics and return ``(projects, ai_commits)``."""
    if not signatures:
        raise ValueError("at least one co-author signature is required")
    if len({candidate["repo_url"] for candidate in candidates}) != len(candidates):
        raise ValueError("authorship candidates contain duplicate repo_url values")
    results: dict[str, dict[str, Any]] = {}
    if output_path.exists():
        results = _read_index(output_path)

    actor_terms: dict[str, str] = {}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for candidate in candidates:
            repo_url = candidate["repo_url"]
            if repo_url in results:
                continue
            canonical_repo = repo_url.removeprefix("https://github.com/")
            revision = candidate.get("observed_revision")
            if not isinstance(revision, str) or not revision:
                raise ValueError(f"candidate has no observed revision for {repo_url}")
            actors = candidate.get("signal_actors")
            if (
                not isinstance(actors, list)
                or not actors
                or not all(isinstance(actor, str) and actor for actor in actors)
            ):
                raise ValueError(f"candidate has no observed actors for {repo_url}")
            window = candidate.get("authorship_window")
            if not isinstance(window, dict):
                raise ValueError(f"candidate has no authorship window for {repo_url}")
            start_at = _parse_utc(window.get("start_at"), "authorship_window.start_at")
            end_at = _parse_utc(window.get("end_at"), "authorship_window.end_at")
            if end_at <= start_at:
                raise ValueError(f"candidate authorship window is invalid for {repo_url}")

            total_commits = _graphql_total_count(
                pool,
                repo=canonical_repo,
                revision=revision,
                start_at=start_at,
                end_at=end_at,
            )
            matching_shas: set[str] = set()
            for actor in sorted(set(actors)):
                if actor not in actor_terms:
                    actor_terms[actor] = _actor_search_term(pool, actor)
                matching_shas.update(
                    _search_matching_shas(
                        pool,
                        repo=canonical_repo,
                        terms=(actor_terms[actor],),
                        start_at=start_at,
                        end_at=end_at,
                        expected_actor=actor,
                    )
                )
            for group in _signature_groups(
                signatures,
                repo=canonical_repo,
                start_at=start_at,
                end_at=end_at,
            ):
                matching_shas.update(
                    _search_matching_shas(
                        pool,
                        repo=canonical_repo,
                        terms=tuple(json.dumps(signature) for signature in group),
                        start_at=start_at,
                        end_at=end_at,
                        expected_signatures=group,
                    )
                )
            ai_commits = len(matching_shas)
            if ai_commits > total_commits:
                raise RuntimeError(
                    f"AI commit count exceeds total commits for {repo_url}: "
                    f"{ai_commits} > {total_commits}"
                )
            row = {
                "repo_url": repo_url,
                "scope": "default_branch_12_months",
                "start_at": _iso_utc(start_at),
                "end_at": _iso_utc(end_at),
                "total_commits": total_commits,
                "ai_commits": ai_commits,
                "ai_ratio": (round(ai_commits / total_commits, 8) if total_commits else None),
            }
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            results[repo_url] = row

    eligible = {candidate["repo_url"] for candidate in candidates}
    missing = eligible - results.keys()
    if missing:
        raise RuntimeError(f"authorship is incomplete for {len(missing)} projects")
    ai_total = sum(int(results[repo_url]["ai_commits"]) for repo_url in eligible)
    return len(eligible), ai_total
