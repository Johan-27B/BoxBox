from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from perfrace.cli import app as root_app
from perfrace.collect.filter import cli
from perfrace.collect.filter.runs import FilterRun


def test_filter_help_lists_run_command() -> None:
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.stdout


def test_filter_run_orchestrates_and_reports_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate_file = tmp_path / "candidates.jsonl"
    candidate_file.write_text("{}\n")
    run_state = FilterRun(
        name="sample",
        root=tmp_path / "sample",
        candidate_file=candidate_file,
        candidate_sha256="a" * 64,
        model="gpt-5.6-luna",
        reasoning_effort="high",
        concurrency=20,
        timeout_seconds=180,
        retries=1,
        max_output_tokens=8000,
        prompt_sha256="b" * 64,
        schema_sha256="c" * 64,
        snapshot_policy_sha256="d" * 64,
        authorship_policy_sha256="e" * 64,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    run_state.root.mkdir()
    monkeypatch.setattr(cli, "open_run", lambda *_args, **_kwargs: run_state)
    monkeypatch.setattr(
        cli,
        "read_candidates",
        lambda _path: [{"repo_url": "https://github.com/owner/project"}],
    )
    monkeypatch.setattr(cli, "_token_pool", lambda _path: object())
    calls: list[str] = []

    async def prepare(*_args, **_kwargs):
        calls.append("precheck")
        return [
            {
                "repo_url": "https://github.com/owner/project",
                "candidate": {"repo_url": "https://github.com/owner/project"},
            }
        ]

    monkeypatch.setattr(cli, "_prepare_snapshots", prepare)

    async def judge(*_args, **_kwargs):
        calls.append("judge")

    monkeypatch.setattr(cli, "_judge_ready_snapshots", judge)
    monkeypatch.setattr(
        cli,
        "_attach_authorship_to_pass_results",
        lambda *_args, **_kwargs: (calls.append("authorship") or 1, 2),
    )
    monkeypatch.setattr(
        cli,
        "rebuild_exports",
        lambda *_args, **_kwargs: {
            "input": 1,
            "processed": 1,
            "passed": 1,
            "high_priority": 1,
            "rejected": 0,
            "errors": 0,
            "requests": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cost_usd": 0.01,
        },
    )
    monkeypatch.setattr(cli, "update_manifest", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(
        root_app,
        [
            "filter",
            "run",
            "--candidate-file",
            str(candidate_file),
            "--run-name",
            "sample",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "Passed: 1" in result.stdout
    assert "High priority: 1" in result.stdout
    assert "Errors: 0" in result.stdout
    assert calls == ["precheck", "judge", "authorship"]


def test_authorship_is_attached_only_to_pass_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate_file = tmp_path / "candidates.jsonl"
    candidate_file.write_text("")
    run_state = FilterRun(
        name="sample",
        root=tmp_path / "sample",
        candidate_file=candidate_file,
        candidate_sha256="a" * 64,
        model="gpt-5.6-luna",
        reasoning_effort="high",
        concurrency=20,
        timeout_seconds=180,
        retries=1,
        max_output_tokens=8000,
        prompt_sha256="b" * 64,
        schema_sha256="c" * 64,
        snapshot_policy_sha256="d" * 64,
        authorship_policy_sha256="e" * 64,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    run_state.root.mkdir()
    candidates = [
        {"repo_url": "https://github.com/owner/pass"},
        {"repo_url": "https://github.com/owner/reject"},
    ]
    run_state.results_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "repo_url": candidate["repo_url"],
                    "status": status,
                    "candidate": candidate,
                }
            )
            for candidate, status in zip(candidates, ("PASS", "REJECT"), strict=True)
        )
        + "\n"
    )
    measured: list[str] = []

    def measure(_pool, passed, output_path, *, signatures):
        assert signatures
        measured.extend(candidate["repo_url"] for candidate in passed)
        output_path.write_text(
            json.dumps(
                {
                    "repo_url": "https://github.com/owner/pass",
                    "scope": "default_branch_12_months",
                    "start_at": "2025-08-30T00:00:00Z",
                    "end_at": "2026-08-30T00:00:00Z",
                    "total_commits": 10,
                    "ai_commits": 2,
                    "ai_ratio": 0.2,
                }
            )
            + "\n"
        )
        return 1, 2

    monkeypatch.setattr(cli, "measure_authorship", measure)

    assert cli._attach_authorship_to_pass_results(
        run_state,
        candidates,
        object(),
    ) == (1, 2)
    latest = cli.load_latest_records(run_state.results_path)
    assert measured == ["https://github.com/owner/pass"]
    assert latest["https://github.com/owner/pass"]["candidate"]["authorship"]["ai_ratio"] == 0.2
    assert "authorship" not in latest["https://github.com/owner/reject"]["candidate"]


def test_precheck_rejects_ineligible_star_counts_without_github(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("GitHub must not be called for an ineligible candidate")

    monkeypatch.setattr(cli, "fetch_repository_evidence", unexpected_fetch)

    for stars, failed_gate in ((9, "minimum_stars"), (5_000, "maximum_stars")):
        root = tmp_path / str(stars)
        candidate_file = root / "candidates.jsonl"
        root.mkdir()
        candidate_file.write_text("")
        run_state = FilterRun(
            name=str(stars),
            root=root,
            candidate_file=candidate_file,
            candidate_sha256="a" * 64,
            model="gpt-5.6-luna",
            reasoning_effort="high",
            concurrency=20,
            timeout_seconds=180,
            retries=1,
            max_output_tokens=8000,
            prompt_sha256="b" * 64,
            schema_sha256="c" * 64,
            snapshot_policy_sha256="d" * 64,
            authorship_policy_sha256="e" * 64,
            created_at=datetime(2026, 8, 30, tzinfo=UTC),
        )
        candidate = {
            "repo_url": f"https://github.com/owner/project-{stars}",
            "stargazer_count": stars,
        }

        assert asyncio.run(cli._prepare_snapshots(run_state, [candidate], object())) == []
        result = cli.load_latest_records(run_state.results_path)[candidate["repo_url"]]
        assert result["status"] == "REJECT"
        assert result["failed_gate"] == failed_gate
        assert result["filter"]["precheck"]["rule"] == failed_gate
