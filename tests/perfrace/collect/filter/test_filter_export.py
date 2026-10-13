from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from perfrace.collect.filter.export import (
    append_record,
    is_high_priority,
    judged_result,
    rebuild_exports,
)
from perfrace.collect.filter.runs import FilterRun
from perfrace.curate.dashboard.store import parse_candidate_jsonl


def _candidate(repo: str, stars: int) -> dict[str, object]:
    return {
        "repo_url": f"https://github.com/{repo}",
        "discovery_channel": "ai-signals",
        "discovered_at": "2026-08-30T00:00:00Z",
        "observed_revision": "a" * 40,
        "default_branch": "main",
        "description": "Example",
        "topics": [],
        "stargazer_count": stars,
        "primary_language": "Python",
        "license_spdx": "MIT",
        "disk_usage_kb": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "pushed_at": "2026-08-30T00:00:00Z",
        "is_fork": False,
        "is_archived": False,
        "is_disabled": False,
        "signal_kind": "branch",
        "signal_url": f"https://github.com/{repo}/tree/copilot/fix",
        "signal_actors": ["Copilot"],
        "authorship_window": {
            "start_at": "2025-08-30T00:00:00Z",
            "end_at": "2026-08-30T00:00:00Z",
        },
        "authorship": {
            "scope": "default_branch_12_months",
            "start_at": "2025-08-30T00:00:00Z",
            "end_at": "2026-08-30T00:00:00Z",
            "total_commits": 10,
            "ai_commits": 1,
            "ai_ratio": 0.1,
        },
    }


def _outcome(
    repo_url: str,
    evaluation_passed: bool,
    potential: str = "high",
) -> dict[str, object]:
    process = (
        {
            "name": "CLI process",
            "workload_carrier": "portable_artifact",
            "setup_commands": ["uv sync"],
            "build_commands": [],
            "smoke_command": "tool input.txt",
            "input": "Input file",
            "output": "Output file",
            "metric": "Wall-clock time",
            "correctness": "Output equality",
            "external_services": [],
        }
        if evaluation_passed
        else None
    )
    return {
        "repo_url": repo_url,
        "status": "JUDGED",
        "snapshot_sha256": "b" * 64,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "attempts": 1,
        "usage": {
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "output_tokens": 20,
            "total_tokens": 120,
            "requests": 1,
            "models": ["gpt-5.6-luna"],
        },
        "cost_usd": 0.01,
        "judgment": {
            "gates": {
                "accessible": {"passed": True, "evidence": ["LICENSE"]},
                "reproducibility": {
                    "passed": True,
                    "evidence": ["pyproject.toml"],
                },
                "evaluation_potential": {
                    "passed": evaluation_passed,
                    "evidence": ["src/cli.py"],
                },
                "resource_feasibility": {
                    "passed": True,
                    "evidence": ["Linux CPU-only"],
                    "linux_x86_64_runnable": True,
                    "special_hardware_required": False,
                },
            },
            "reason": "Decision.",
            "optimization_profile": {
                "computation": "Batch project processing",
                "potential": potential,
                "performance_hint": "Repeated local work scales with the input batch.",
            },
            "preliminary_process": process,
        },
    }


def test_rebuild_exports_preserves_candidate_order_and_dashboard_shape(
    tmp_path: Path,
) -> None:
    first = _candidate("owner/first", 10)
    second = _candidate("owner/second", 1)
    candidate_file = tmp_path / "candidates.jsonl"
    candidate_file.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    run = FilterRun(
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
    append_record(run.results_path, judged_result(second, _outcome(second["repo_url"], False)))
    append_record(run.results_path, judged_result(first, _outcome(first["repo_url"], True)))

    summary = rebuild_exports(run, [first, second])

    results = [json.loads(line) for line in run.results_path.read_text().splitlines()]
    assert [row["repo_url"] for row in results] == [
        first["repo_url"],
        second["repo_url"],
    ]
    assert summary["passed"] == 1
    assert summary["rejected"] == 1
    assert len(parse_candidate_jsonl(run.passed_path.read_text())) == 1


def test_low_optimization_potential_is_rejected() -> None:
    candidate = _candidate("owner/project", 1)

    result = judged_result(
        candidate,
        _outcome(candidate["repo_url"], True, potential="low"),
    )

    assert result["status"] == "REJECT"
    assert result["failed_gate"] == "optimization_potential"


def test_linux_and_hardware_requirements_override_resource_pass() -> None:
    candidate = _candidate("owner/project", 100)

    for field, value in (
        ("linux_x86_64_runnable", False),
        ("special_hardware_required", True),
    ):
        outcome = _outcome(candidate["repo_url"], True)
        outcome["judgment"]["gates"]["resource_feasibility"][field] = value

        result = judged_result(candidate, outcome)

        assert result["status"] == "REJECT"
        assert result["failed_gate"] == "resource_feasibility"
        assert any(
            field in evidence
            for evidence in result["filter"]["gates"]["resource_feasibility"]["evidence"]
        )


def test_high_priority_requires_strict_pair_verification_signals() -> None:
    candidate = _candidate("owner/project", 100)
    outcome = _outcome(candidate["repo_url"], True)
    outcome["judgment"]["optimization_profile"]["computation"] = (
        "Parse and sort a fixed record corpus."
    )
    result = judged_result(candidate, outcome)
    eligible = {**result["candidate"], "filter": result["filter"]}

    assert is_high_priority(eligible) is True

    cases = []
    for field, value in (
        ("stargazer_count", 99),
        ("stargazer_count", 5_000),
        ("created_at", "2022-12-31T00:00:00Z"),
        ("disk_usage_kb", 500_000),
        ("description", "Agent workflow orchestration"),
    ):
        changed = json.loads(json.dumps(eligible))
        changed[field] = value
        cases.append(changed)

    external = json.loads(json.dumps(eligible))
    external["filter"]["preliminary_process"]["external_services"] = ["Remote API"]
    cases.append(external)
    repo_native = json.loads(json.dumps(eligible))
    repo_native["filter"]["preliminary_process"]["correctness"] = "Run the unit test suite."
    cases.append(repo_native)
    no_core = json.loads(json.dumps(eligible))
    no_core["filter"]["optimization_profile"]["computation"] = "Handle project records."
    cases.append(no_core)
    unresolved = json.loads(json.dumps(eligible))
    unresolved["filter"]["preliminary_process"]["workload_carrier"] = "unresolved"
    cases.append(unresolved)

    assert all(is_high_priority(case) is False for case in cases)


def test_rebuild_exports_writes_dashboard_compatible_high_priority_queue(
    tmp_path: Path,
) -> None:
    candidate = _candidate("owner/project", 100)
    outcome = _outcome(candidate["repo_url"], True)
    outcome["judgment"]["optimization_profile"]["computation"] = (
        "Parse and sort a fixed record corpus."
    )
    candidate_file = tmp_path / "candidates.jsonl"
    candidate_file.write_text(json.dumps(candidate) + "\n")
    run = FilterRun(
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
    append_record(run.results_path, judged_result(candidate, outcome))

    summary = rebuild_exports(run, [candidate])

    assert summary["high_priority"] == 1
    assert len(parse_candidate_jsonl(run.high_priority_path.read_text())) == 1
