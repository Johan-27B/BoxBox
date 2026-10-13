from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from perfrace.collect.discovery import harvest


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


def test_load_bot_accounts_and_fingerprint_are_normalized(tmp_path: Path) -> None:
    path = tmp_path / "bots.txt"
    path.write_text("# comment\ncursor[bot]\n\nCopilot\n")

    assert harvest.load_bot_accounts(path) == ("cursor[bot]", "Copilot")
    assert harvest.bot_config_sha256(path) == harvest.bot_config_sha256(path)


def test_load_bot_accounts_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "bots.txt"
    path.write_text("Copilot\nCopilot\n")

    with pytest.raises(ValueError, match="duplicate bot accounts"):
        harvest.load_bot_accounts(path)


def test_build_harvest_query_uses_fixed_window_and_project_events() -> None:
    query = harvest.build_harvest_query(
        ("cursor[bot]",),
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert "created_at >= toDateTime('2026-08-01 00:00:00', 'UTC')" in query
    assert "created_at < toDateTime('2026-08-02 00:00:00', 'UTC')" in query
    assert "PullRequestEvent" in query
    assert "PushEvent" in query
    assert "GROUP BY repo_name" in query


def test_harvest_projects_writes_compact_sorted_references(
    tmp_path: Path,
    monkeypatch,
) -> None:
    response = FakeResponse(
        "\n".join(
            [
                json.dumps(
                    {
                        "repo": "sample/resume",
                        "signal_actors": ["cursor[bot]"],
                        "signal_kind": "branch",
                        "signal_ref": "cursor/add-feature",
                    }
                ),
                json.dumps(
                    {
                        "repo": "a-owner/a-repo",
                        "signal_actors": ["Copilot"],
                        "signal_kind": "pull_request",
                        "signal_ref": "42",
                    }
                ),
            ]
        )
    )
    monkeypatch.setattr(harvest.requests, "post", lambda *_args, **_kwargs: response)
    output = tmp_path / "harvest.jsonl"

    rows = harvest.harvest_projects(
        output,
        bot_accounts=("cursor[bot]",),
        start_at=datetime(2026, 8, 1, tzinfo=UTC),
        end_at=datetime(2026, 8, 2, tzinfo=UTC),
    )

    payloads = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows == 2
    assert [payload["repo"] for payload in payloads] == [
        "a-owner/a-repo",
        "sample/resume",
    ]
    assert payloads[0]["signal_url"].endswith("/pull/42")
    assert payloads[0]["signal_actors"] == ["Copilot"]
    assert payloads[1]["signal_url"].endswith("/tree/cursor/add-feature")
