from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfrace.collect.discovery import metadata


class FakePool:
    def acquire_blocking(self, _endpoint: str):
        return 0, object()

    def auth_headers(self, _token: object) -> dict[str, str]:
        return {"Authorization": "test"}

    def report_response(self, _index: int, _response: object, _endpoint: str) -> None:
        return None


class FakeResponse:
    status_code = 200
    text = ""

    def json(self) -> dict:
        return {
            "data": {
                "r0": {
                    "nameWithOwner": "owner/project",
                    "url": "https://github.com/owner/project",
                    "description": "Example project",
                    "stargazerCount": 25,
                    "primaryLanguage": {"name": "Python"},
                    "licenseInfo": {"spdxId": "MIT"},
                    "isFork": False,
                    "isArchived": False,
                    "isDisabled": False,
                    "diskUsage": 123,
                    "createdAt": "2026-01-01T00:00:00Z",
                    "pushedAt": "2026-08-01T00:00:00Z",
                    "repositoryTopics": {
                        "nodes": [
                            {"topic": {"name": "agent"}},
                            {"topic": {"name": "performance"}},
                        ]
                    },
                    "defaultBranchRef": {
                        "name": "main",
                        "target": {"oid": "a" * 40},
                    },
                },
                "r1": None,
            }
        }


def test_metadata_query_includes_project_snapshot_fields() -> None:
    query = metadata._build_query(["owner/project"])

    assert "repositoryTopics(first: 20)" in query
    assert "defaultBranchRef" in query
    assert "... on Commit { oid }" in query
    assert "stargazerCount" in query


def test_fetch_project_metadata_persists_valid_and_unavailable_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0

    def fake_post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse()

    monkeypatch.setattr(metadata.requests, "post", fake_post)
    output = tmp_path / "metadata.jsonl"
    repos = ["owner/project", "missing/project"]

    counts = metadata.fetch_project_metadata(FakePool(), repos, output)
    resumed = metadata.fetch_project_metadata(FakePool(), repos, output)

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert counts == (1, 1)
    assert resumed == (1, 1)
    assert calls == 1
    assert rows[0]["metadata"]["observed_revision"] == "a" * 40
    assert rows[0]["metadata"]["topics"] == ["agent", "performance"]
    assert rows[1] == {"repo": "missing/project", "metadata": None}


def test_fetch_project_metadata_rejects_graphql_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class ErrorResponse(FakeResponse):
        def json(self) -> dict:
            return {
                "data": {"r0": None},
                "errors": [{"type": "RATE_LIMITED", "message": "slow down"}],
            }

    monkeypatch.setattr(
        metadata.requests,
        "post",
        lambda *_args, **_kwargs: ErrorResponse(),
    )

    with pytest.raises(RuntimeError, match="slow down"):
        metadata.fetch_project_metadata(
            FakePool(),
            ["owner/project"],
            tmp_path / "metadata.jsonl",
        )
