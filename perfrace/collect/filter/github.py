"""GitHub API access for revision-pinned Filter snapshots."""

from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import quote, urlparse

import requests

from ..discovery.export import validate_candidate
from ..utils._constants import GITHUB_API
from ..utils.tokens import TokenPool
from ._constants import MAX_SELECTED_FILES, MAX_TRACKED_BYTES, MAX_TREE_ENTRIES


class RepositoryRejected(ValueError):
    """A deterministic Filter rejection with a specific gate."""

    def __init__(self, gate: str, reason: str, evidence: list[str]):
        super().__init__(reason)
        self.gate = gate
        self.reason = reason
        self.evidence = evidence


class GitHubSnapshotError(RuntimeError):
    """A retryable GitHub snapshot failure."""


def _get_json(
    pool: TokenPool,
    endpoint: str,
    *,
    params: dict[str, str] | None = None,
    allow_not_found: bool = False,
    max_retries: int = 3,
) -> tuple[int, Any]:
    for attempt in range(max_retries):
        token_index, token = pool.acquire_blocking("rest")
        try:
            response = requests.get(
                f"{GITHUB_API}/{endpoint.lstrip('/')}",
                headers=pool.auth_headers(token),
                params=params,
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
                return response.status_code, response.json()
            except ValueError as exc:
                raise GitHubSnapshotError(f"GitHub returned non-JSON data for {endpoint}") from exc
        if allow_not_found and response.status_code in {404, 410}:
            return response.status_code, None
        if response.status_code in {403, 429, 502, 503} and attempt + 1 < max_retries:
            time.sleep(2**attempt)
            continue
        raise GitHubSnapshotError(
            f"GitHub request failed for {endpoint}: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    raise GitHubSnapshotError(f"GitHub request exhausted retries for {endpoint}")


def _repository_parts(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or len(parts) != 2:
        raise ValueError("candidate repo_url must identify one GitHub repository")
    return parts[0], parts[1]


def _decode_content(payload: object, path: str) -> str:
    if not isinstance(payload, dict):
        raise GitHubSnapshotError(f"GitHub content payload is invalid for {path}")
    content = payload.get("content")
    encoding = payload.get("encoding")
    if not isinstance(content, str) or encoding != "base64":
        raise GitHubSnapshotError(f"GitHub content is unavailable for {path}")
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except ValueError as exc:
        raise GitHubSnapshotError(f"GitHub content is invalid for {path}") from exc


def _selected_paths(tree: list[dict[str, Any]]) -> list[str]:
    groups: dict[str, list[tuple[int, str]]] = {
        "readme": [],
        "setup": [],
        "contributing": [],
        "manifest": [],
        "build": [],
    }
    manifests = {
        "package.json",
        "pyproject.toml",
        "cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "makefile",
        "cmakelists.txt",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "gemfile",
        "mix.exs",
    }
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        lower = path.lower()
        basename = lower.rsplit("/", 1)[-1]
        depth = lower.count("/")
        if basename.startswith("readme"):
            group = "readme"
        elif basename.startswith("install") or basename.startswith("getting-started"):
            group = "setup"
        elif basename.startswith("contributing"):
            group = "contributing"
        elif basename in manifests:
            group = "manifest"
        elif depth <= 2 and (
            "quickstart" in basename or "build" in basename or "setup" in basename
        ):
            group = "build"
        else:
            continue
        groups[group].append((depth, path))

    selected: list[str] = []
    selections = (
        ("readme", 1),
        ("manifest", 8),
        ("setup", 2),
        ("contributing", 1),
        ("readme", 1),
        ("build", MAX_SELECTED_FILES),
    )
    for group, quota in selections:
        added = 0
        for _, path in sorted(
            groups[group],
            key=lambda item: (
                item[0],
                (
                    0
                    if group != "readme"
                    or item[1].lower().rsplit("/", 1)[-1]
                    in {"readme", "readme.md", "readme.rst", "readme.txt"}
                    else 1
                ),
                item[1],
            ),
        ):
            if path in selected:
                continue
            selected.append(path)
            added += 1
            if added >= quota or len(selected) >= MAX_SELECTED_FILES:
                break
        if len(selected) >= MAX_SELECTED_FILES:
            break
    return selected


def _license_paths(tree: list[dict[str, Any]]) -> list[str]:
    names = {
        "license",
        "license.txt",
        "license.md",
        "copying",
        "copying.txt",
        "copying.md",
        "copyright",
    }
    paths = [
        path
        for item in tree
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and isinstance((path := item.get("path")), str)
        and path.rsplit("/", 1)[-1].lower() in names
    ]
    return sorted(paths, key=lambda path: (path.count("/"), path))[:5]


def fetch_repository_evidence(
    pool: TokenPool,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Fetch repository, revision, tree, license, and selected file evidence."""
    validate_candidate(candidate)
    if candidate["is_archived"]:
        raise RepositoryRejected(
            "accessible",
            "Repository is archived.",
            ["candidate.is_archived = true"],
        )
    if candidate["is_disabled"]:
        raise RepositoryRejected(
            "accessible",
            "Repository is disabled.",
            ["candidate.is_disabled = true"],
        )

    owner, name = _repository_parts(candidate["repo_url"])
    repository = f"{owner}/{name}"
    revision = candidate["observed_revision"]
    encoded_revision = quote(revision, safe="")
    status, commit_payload = _get_json(
        pool,
        f"repos/{repository}/git/commits/{encoded_revision}",
        allow_not_found=True,
    )
    if status in {404, 410} or commit_payload is None:
        raise RepositoryRejected(
            "accessible",
            "Observed revision is no longer available.",
            [f"GitHub git commit lookup returned HTTP {status}"],
        )
    if not isinstance(commit_payload, dict):
        raise GitHubSnapshotError(f"GitHub returned an invalid commit for {repository}")
    commit_tree = commit_payload.get("tree") or {}
    tree_sha = commit_tree.get("sha") if isinstance(commit_tree, dict) else None
    if not isinstance(tree_sha, str) or not tree_sha:
        raise GitHubSnapshotError(f"GitHub commit has no tree SHA for {repository}")

    tree_status, tree_payload = _get_json(
        pool,
        f"repos/{repository}/git/trees/{quote(tree_sha, safe='')}",
        params={"recursive": "1"},
        allow_not_found=True,
    )
    if tree_status in {404, 410} or tree_payload is None:
        raise RepositoryRejected(
            "accessible",
            "Observed revision tree is no longer available.",
            [f"GitHub git tree lookup returned HTTP {tree_status}"],
        )
    if not isinstance(tree_payload, dict) or not isinstance(tree_payload.get("tree"), list):
        raise GitHubSnapshotError(f"GitHub returned an invalid tree for {repository}")
    tree = tree_payload["tree"]
    truncated = bool(tree_payload.get("truncated"))
    entry_count = len(tree)
    tracked_bytes = sum(
        int(item.get("size") or 0)
        for item in tree
        if isinstance(item, dict) and item.get("type") == "blob"
    )
    if truncated:
        raise RepositoryRejected(
            "resource_feasibility",
            "Recursive Git tree is truncated by GitHub.",
            [f"tree entries returned: {entry_count}", f"tracked bytes returned: {tracked_bytes}"],
        )
    if entry_count > MAX_TREE_ENTRIES:
        raise RepositoryRejected(
            "resource_feasibility",
            f"Git tree exceeds {MAX_TREE_ENTRIES} entries.",
            [f"tree entries: {entry_count}"],
        )
    if tracked_bytes > MAX_TRACKED_BYTES:
        raise RepositoryRejected(
            "resource_feasibility",
            "Tracked Git blobs exceed 500 MiB.",
            [f"tracked bytes: {tracked_bytes}"],
        )

    licenses: list[dict[str, Any]] = []
    primary_license_path: str | None = None
    primary_license_spdx = candidate.get("license_spdx")
    license_status, license_payload = _get_json(
        pool,
        f"repos/{repository}/license",
        params={"ref": revision},
        allow_not_found=True,
    )
    if license_status == 200 and isinstance(license_payload, dict):
        path_value = license_payload.get("path")
        if isinstance(path_value, str):
            primary_license_path = path_value
        license_info = license_payload.get("license") or {}
        if isinstance(license_info, dict):
            spdx_value = license_info.get("spdx_id")
            if isinstance(spdx_value, str) and spdx_value not in {"", "NOASSERTION"}:
                primary_license_spdx = spdx_value
        licenses.append(
            {
                "path": primary_license_path or "LICENSE",
                "spdx": primary_license_spdx,
                "text": _decode_content(
                    license_payload,
                    primary_license_path or "LICENSE",
                ),
                "source_url": (
                    f"{candidate['repo_url']}/blob/{revision}/{primary_license_path or 'LICENSE'}"
                ),
            }
        )

    for license_path in _license_paths(tree):
        if any(item["path"] == license_path for item in licenses):
            continue
        try:
            file_status, content_payload = _get_json(
                pool,
                f"repos/{repository}/contents/{quote(license_path, safe='/')}",
                params={"ref": revision},
                allow_not_found=True,
            )
            if file_status != 200 or content_payload is None:
                continue
            license_text = _decode_content(content_payload, license_path)
        except GitHubSnapshotError:
            continue
        licenses.append(
            {
                "path": license_path,
                "spdx": (primary_license_spdx if license_path == primary_license_path else None),
                "text": license_text,
                "source_url": f"{candidate['repo_url']}/blob/{revision}/{license_path}",
            }
        )
    if not licenses or not any(item["text"].strip() for item in licenses):
        raise RepositoryRejected(
            "accessible",
            "Repository has no explicit license text.",
            [f"GitHub license lookup returned HTTP {license_status}"],
        )

    files: list[dict[str, Any]] = []
    file_errors: list[dict[str, str]] = []
    for path in _selected_paths(tree):
        if any(item["path"] == path for item in licenses):
            continue
        try:
            file_status, payload = _get_json(
                pool,
                f"repos/{repository}/contents/{quote(path, safe='/')}",
                params={"ref": revision},
                allow_not_found=True,
            )
            if file_status != 200 or payload is None:
                file_errors.append({"path": path, "error": f"HTTP {file_status}"})
                continue
            text = _decode_content(payload, path)
        except GitHubSnapshotError as exc:
            file_errors.append({"path": path, "error": str(exc)})
            continue
        files.append(
            {
                "path": path,
                "text": text,
                "source_url": f"{candidate['repo_url']}/blob/{revision}/{path}",
            }
        )

    return {
        "repository": repository,
        "revision": revision,
        "tree": {
            "truncated": truncated,
            "entry_count": entry_count,
            "tracked_bytes": tracked_bytes,
            "paths": [
                item["path"]
                for item in tree
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            ],
        },
        "licenses": licenses,
        "files": files,
        "file_errors": file_errors,
    }
