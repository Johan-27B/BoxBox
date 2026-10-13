from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from perfrace.collect.filter import authorship


def test_load_coauthor_signatures_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "signatures.txt"
    path.write_text("Co-Authored-By: Copilot\nCo-Authored-By: Copilot\n")

    with pytest.raises(ValueError, match="duplicates"):
        authorship.load_coauthor_signatures(path)


def test_search_matching_shas_splits_over_limit(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_search_page(_pool, query: str, page: int):
        calls.append((query, page))
        if "2025-01-01T00:00:00Z..2025-01-03T00:00:00Z" in query:
            return [], 1001
        sha = "a" * 40 if "2025-01-01T00:00:00Z" in query else "b" * 40
        return [{"sha": sha, "repository": {"full_name": "owner/project"}}], 1

    monkeypatch.setattr(authorship, "_search_page", fake_search_page)

    matches = authorship._search_matching_shas(
        object(),
        repo="owner/project",
        terms=("author:Copilot",),
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        end_at=datetime(2025, 1, 3, tzinfo=UTC),
    )

    assert matches == {"a" * 40, "b" * 40}
    assert len(calls) == 3


def test_search_matching_shas_accepts_count_drift(monkeypatch) -> None:
    first_page = [
        {
            "sha": f"{index:040x}",
            "repository": {"full_name": "owner/project"},
        }
        for index in range(100)
    ]

    def fake_search_page(_pool, _query: str, page: int):
        if page == 1:
            return first_page, 150
        return [
            {
                "sha": "f" * 40,
                "repository": {"full_name": "owner/project"},
            }
        ], 151

    monkeypatch.setattr(authorship, "_search_page", fake_search_page)

    matches = authorship._search_matching_shas(
        object(),
        repo="owner/project",
        terms=("author:Copilot",),
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        end_at=datetime(2025, 1, 2, tzinfo=UTC),
    )

    assert len(matches) == 101


def test_search_matching_shas_filters_repository_and_actor(monkeypatch) -> None:
    monkeypatch.setattr(
        authorship,
        "_search_page",
        lambda *_args, **_kwargs: (
            [
                {
                    "sha": "a" * 40,
                    "author": {"login": "Copilot"},
                    "repository": {"full_name": "owner/project"},
                },
                {
                    "sha": "b" * 40,
                    "author": {"login": "Copilot"},
                    "repository": {"full_name": "other/project"},
                },
                {
                    "sha": "c" * 40,
                    "author": {"login": "human"},
                    "repository": {"full_name": "owner/project"},
                },
            ],
            3,
        ),
    )

    matches = authorship._search_matching_shas(
        object(),
        repo="owner/project",
        terms=("author-name:Copilot",),
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        end_at=datetime(2025, 1, 2, tzinfo=UTC),
        expected_actor="Copilot",
    )

    assert matches == {"a" * 40}


def test_measure_authorship_deduplicates_matches_and_resumes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidates = [
        {
            "repo_url": "https://github.com/renamed/project",
            "observed_revision": "c" * 40,
            "signal_actors": ["Copilot"],
            "authorship_window": {
                "start_at": "2025-08-30T00:00:00Z",
                "end_at": "2026-08-30T00:00:00Z",
            },
        }
    ]
    output_path = tmp_path / "authorship.jsonl"
    searches = 0

    monkeypatch.setattr(
        authorship,
        "_graphql_total_count",
        lambda *_args, **_kwargs: 10,
    )
    monkeypatch.setattr(
        authorship,
        "_actor_search_term",
        lambda *_args, **_kwargs: "author-name:Copilot",
    )

    def fake_search(*_args, repo: str, terms: tuple[str, ...], **_kwargs):
        nonlocal searches
        searches += 1
        assert repo == "renamed/project"
        if terms[0].startswith("author-name:"):
            return {"a" * 40}
        return {"a" * 40, "b" * 40}

    monkeypatch.setattr(authorship, "_search_matching_shas", fake_search)

    first = authorship.measure_authorship(
        object(),
        candidates,
        output_path,
        signatures=("Co-Authored-By: Copilot",),
    )
    resumed = authorship.measure_authorship(
        object(),
        candidates,
        output_path,
        signatures=("Co-Authored-By: Copilot",),
    )

    row = json.loads(output_path.read_text())
    assert first == (1, 2)
    assert resumed == (1, 2)
    assert searches == 2
    assert row["repo_url"] == "https://github.com/renamed/project"
    assert row["total_commits"] == 10
    assert row["ai_commits"] == 2
    assert row["ai_ratio"] == 0.2
