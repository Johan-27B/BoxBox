from __future__ import annotations

import base64

import pytest

from perfrace.collect.filter import github


def _candidate(**overrides):
    candidate = {
        "repo_url": "https://github.com/owner/project",
        "discovery_channel": "ai-signals",
        "discovered_at": "2026-08-30T00:00:00Z",
        "observed_revision": "a" * 40,
        "default_branch": "main",
        "description": "Example",
        "topics": [],
        "stargazer_count": 1,
        "primary_language": "Python",
        "license_spdx": "MIT",
        "disk_usage_kb": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "pushed_at": "2026-08-30T00:00:00Z",
        "is_fork": False,
        "is_archived": False,
        "is_disabled": False,
        "signal_kind": "branch",
        "signal_url": "https://github.com/owner/project/tree/copilot/fix",
        "signal_actors": ["Copilot"],
        "authorship_window": {
            "start_at": "2025-08-30T00:00:00Z",
            "end_at": "2026-08-30T00:00:00Z",
        },
    }
    candidate.update(overrides)
    return candidate


def test_archived_repository_is_rejected_without_api_call() -> None:
    with pytest.raises(github.RepositoryRejected, match="archived") as raised:
        github.fetch_repository_evidence(object(), _candidate(is_archived=True))

    assert raised.value.gate == "accessible"


def test_truncated_tree_is_resource_rejected(monkeypatch) -> None:
    def fake_get(_pool, endpoint: str, **_kwargs):
        if "/git/commits/" in endpoint:
            return 200, {"sha": "a" * 40, "tree": {"sha": "b" * 40}}
        if "/git/trees/" in endpoint:
            return 200, {"truncated": True, "tree": []}
        raise AssertionError(endpoint)

    monkeypatch.setattr(github, "_get_json", fake_get)

    with pytest.raises(github.RepositoryRejected, match="truncated") as raised:
        github.fetch_repository_evidence(object(), _candidate())

    assert raised.value.gate == "resource_feasibility"


def test_missing_commit_tree_is_accessible_rejected(monkeypatch) -> None:
    def fake_get(_pool, endpoint: str, **_kwargs):
        if "/git/commits/" in endpoint:
            return 200, {"sha": "a" * 40, "tree": {"sha": "b" * 40}}
        if "/git/trees/" in endpoint:
            assert "b" * 40 in endpoint
            return 404, None
        raise AssertionError(endpoint)

    monkeypatch.setattr(github, "_get_json", fake_get)

    with pytest.raises(github.RepositoryRejected, match="tree") as raised:
        github.fetch_repository_evidence(object(), _candidate())

    assert raised.value.gate == "accessible"


def test_repository_evidence_includes_license_tree_and_manifests(monkeypatch) -> None:
    tree = [
        {"path": "README.md", "type": "blob", "size": 20},
        {"path": "LICENSE", "type": "blob", "size": 20},
        {"path": "package.json", "type": "blob", "size": 20},
    ]

    def encoded(text: str) -> dict[str, str]:
        return {
            "encoding": "base64",
            "content": base64.b64encode(text.encode()).decode(),
        }

    def fake_get(_pool, endpoint: str, **_kwargs):
        if "/git/commits/" in endpoint:
            return 200, {"sha": "a" * 40, "tree": {"sha": "b" * 40}}
        if "/git/trees/" in endpoint:
            return 200, {"truncated": False, "tree": tree}
        if endpoint.endswith("/license"):
            return 200, {
                **encoded("MIT License"),
                "path": "LICENSE",
                "license": {"spdx_id": "MIT"},
            }
        if endpoint.endswith("/contents/README.md"):
            return 200, encoded("Build with npm.")
        if endpoint.endswith("/contents/package.json"):
            return 200, encoded('{"scripts":{"build":"tsc"}}')
        raise AssertionError(endpoint)

    monkeypatch.setattr(github, "_get_json", fake_get)

    evidence = github.fetch_repository_evidence(object(), _candidate())

    assert evidence["tree"]["entry_count"] == 3
    assert evidence["licenses"][0]["spdx"] == "MIT"
    assert [item["path"] for item in evidence["files"]] == [
        "README.md",
        "package.json",
    ]


def test_selected_paths_balance_readmes_and_manifests() -> None:
    tree = [{"path": f"docs/section-{index}/README.md", "type": "blob"} for index in range(20)]
    tree.extend(
        [
            {"path": "README.md", "type": "blob"},
            {"path": "package.json", "type": "blob"},
            {"path": "backend/pyproject.toml", "type": "blob"},
            {"path": "Dockerfile", "type": "blob"},
        ]
    )

    selected = github._selected_paths(tree)

    assert selected[0] == "README.md"
    assert "package.json" in selected
    assert "backend/pyproject.toml" in selected
    assert "Dockerfile" in selected
    assert sum(path.lower().endswith("readme.md") for path in selected) == 2
