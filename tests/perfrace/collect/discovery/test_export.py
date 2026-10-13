from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from perfrace.collect.discovery.export import export_candidates, validate_candidate
from perfrace.curate.dashboard.store import parse_candidate_jsonl


def _metadata(repo_url: str, stars: int) -> dict[str, object]:
    return {
        "repo": repo_url.removeprefix("https://github.com/"),
        "repo_url": repo_url,
        "description": "Example",
        "topics": ["agent"],
        "stargazer_count": stars,
        "primary_language": "Python",
        "license_spdx": "MIT",
        "disk_usage_kb": 100,
        "created_at": "2026-01-01T00:00:00Z",
        "pushed_at": "2026-08-01T00:00:00Z",
        "is_fork": False,
        "is_archived": False,
        "is_disabled": False,
        "default_branch": "main",
        "observed_revision": "a" * 40,
    }


def test_export_candidates_orders_by_stars_and_excludes_unavailable(
    tmp_path: Path,
) -> None:
    harvest = tmp_path / "harvest.jsonl"
    harvest.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "repo": "low/project",
                        "signal_actors": ["cursor[bot]"],
                        "signal_kind": "branch",
                        "signal_url": "https://github.com/low/project/tree/cursor/add-feature",
                    }
                ),
                json.dumps(
                    {
                        "repo": "high/project",
                        "signal_actors": ["Copilot"],
                        "signal_kind": "pull_request",
                        "signal_url": "https://github.com/high/project/pull/7",
                    }
                ),
                json.dumps(
                    {
                        "repo": "missing/project",
                        "signal_actors": ["Copilot"],
                        "signal_kind": "branch",
                        "signal_url": "https://github.com/missing/project/tree/copilot/fix",
                    }
                ),
                json.dumps(
                    {
                        "repo": "top/project",
                        "signal_actors": ["Copilot"],
                        "signal_kind": "pull_request",
                        "signal_url": "https://github.com/top/project/pull/9",
                    }
                ),
            ]
        )
        + "\n"
    )
    metadata = tmp_path / "metadata.jsonl"
    metadata.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "repo": "low/project",
                        "metadata": _metadata("https://github.com/low/project", 100),
                    }
                ),
                json.dumps(
                    {
                        "repo": "high/project",
                        "metadata": _metadata("https://github.com/high/project", 100),
                    }
                ),
                json.dumps({"repo": "missing/project", "metadata": None}),
                json.dumps(
                    {
                        "repo": "top/project",
                        "metadata": _metadata("https://github.com/top/project", 200),
                    }
                ),
            ]
        )
        + "\n"
    )
    output = tmp_path / "candidates.jsonl"

    counts = export_candidates(
        harvest,
        metadata,
        output,
        discovered_at=datetime(2026, 8, 30, tzinfo=UTC),
        authorship_start_at=datetime(2025, 8, 30, tzinfo=UTC),
        authorship_end_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    candidates = [json.loads(line) for line in output.read_text().splitlines()]
    assert counts == (3, 1)
    assert [candidate["repo_url"] for candidate in candidates] == [
        "https://github.com/top/project",
        "https://github.com/high/project",
        "https://github.com/low/project",
    ]
    assert candidates[0]["signal_url"] == "https://github.com/top/project/pull/9"
    assert len(parse_candidate_jsonl(output.read_text())) == 3


def test_validate_candidate_rejects_mismatched_signal_url() -> None:
    candidate = {
        **_metadata("https://github.com/owner/project", 1),
        "discovery_channel": "ai-signals",
        "discovered_at": "2026-08-30T00:00:00Z",
        "signal_kind": "branch",
        "signal_url": "https://github.com/other/project/tree/cursor/fix",
        "signal_actors": ["cursor[bot]"],
        "authorship_window": {
            "start_at": "2025-08-30T00:00:00Z",
            "end_at": "2026-08-30T00:00:00Z",
        },
    }
    candidate.pop("repo")

    with pytest.raises(ValueError, match="does not match"):
        validate_candidate(candidate)


def test_validate_candidate_requires_signal_actors() -> None:
    candidate = {
        **_metadata("https://github.com/owner/project", 1),
        "discovery_channel": "ai-signals",
        "discovered_at": "2026-08-30T00:00:00Z",
        "signal_kind": "branch",
        "signal_url": "https://github.com/owner/project/tree/cursor/fix",
        "signal_actors": [],
        "authorship_window": {
            "start_at": "2025-08-30T00:00:00Z",
            "end_at": "2026-08-30T00:00:00Z",
        },
    }
    candidate.pop("repo")

    with pytest.raises(ValueError, match="signal_actors"):
        validate_candidate(candidate)


@pytest.mark.parametrize(
    ("start_at", "end_at", "message"),
    [
        (
            "2025-08-30T01:00:00+01:00",
            "2026-08-30T00:00:00Z",
            "must use UTC",
        ),
        (
            "2026-08-30T00:00:00Z",
            "2025-08-30T00:00:00Z",
            "must be after start_at",
        ),
    ],
)
def test_validate_candidate_requires_ordered_utc_authorship_window(
    start_at: str,
    end_at: str,
    message: str,
) -> None:
    candidate = {
        **_metadata("https://github.com/owner/project", 1),
        "discovery_channel": "ai-signals",
        "discovered_at": "2026-08-30T00:00:00Z",
        "signal_kind": "branch",
        "signal_url": "https://github.com/owner/project/tree/copilot/fix",
        "signal_actors": ["Copilot"],
        "authorship_window": {"start_at": start_at, "end_at": end_at},
    }
    candidate.pop("repo")

    with pytest.raises(ValueError, match=message):
        validate_candidate(candidate)


def test_export_candidates_deduplicates_canonical_repository_urls(
    tmp_path: Path,
) -> None:
    harvest = tmp_path / "harvest.jsonl"
    harvest.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "repo": "old/project",
                        "signal_actors": ["Copilot"],
                        "signal_kind": "branch",
                        "signal_url": "https://github.com/old/project/tree/z-branch",
                    }
                ),
                json.dumps(
                    {
                        "repo": "new/project",
                        "signal_actors": ["Copilot"],
                        "signal_kind": "branch",
                        "signal_url": "https://github.com/new/project/tree/a-branch",
                    }
                ),
            ]
        )
        + "\n"
    )
    metadata = tmp_path / "metadata.jsonl"
    snapshot = _metadata("https://github.com/new/project", 1)
    metadata.write_text(
        "\n".join(
            [
                json.dumps({"repo": "old/project", "metadata": snapshot}),
                json.dumps({"repo": "new/project", "metadata": snapshot}),
            ]
        )
        + "\n"
    )
    output = tmp_path / "candidates.jsonl"

    assert export_candidates(
        harvest,
        metadata,
        output,
        discovered_at=datetime(2026, 8, 30, tzinfo=UTC),
        authorship_start_at=datetime(2025, 8, 30, tzinfo=UTC),
        authorship_end_at=datetime(2026, 8, 30, tzinfo=UTC),
    ) == (1, 1)
    candidate = json.loads(output.read_text())
    assert candidate["repo_url"] == "https://github.com/new/project"
    assert candidate["signal_url"].endswith("/tree/a-branch")
