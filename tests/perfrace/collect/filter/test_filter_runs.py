from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfrace.collect.filter.runs import open_run, update_manifest


def test_filter_run_creates_and_resumes_matching_manifest(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text('{"repo_url":"https://github.com/owner/project"}\n')
    kwargs = {
        "run_name": "sample",
        "candidate_file": candidates,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "concurrency": 20,
        "timeout_seconds": 180,
        "retries": 1,
        "max_output_tokens": 8000,
        "prompt_sha256": "a" * 64,
        "schema_sha256": "b" * 64,
        "snapshot_policy_sha256": "c" * 64,
        "authorship_policy_sha256": "d" * 64,
    }

    created = open_run(tmp_path, **kwargs)
    resumed = open_run(tmp_path, **kwargs)
    update_manifest(created, status="complete")

    assert resumed == created
    assert json.loads(created.manifest_path.read_text())["status"] == "complete"


def test_filter_run_rejects_changed_input(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text('{"repo_url":"https://github.com/owner/project"}\n')
    kwargs = {
        "run_name": "sample",
        "candidate_file": candidates,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "concurrency": 20,
        "timeout_seconds": 180,
        "retries": 1,
        "max_output_tokens": 8000,
        "prompt_sha256": "a" * 64,
        "schema_sha256": "b" * 64,
        "snapshot_policy_sha256": "c" * 64,
        "authorship_policy_sha256": "d" * 64,
    }
    open_run(tmp_path, **kwargs)
    candidates.write_text('{"repo_url":"https://github.com/other/project"}\n')

    with pytest.raises(ValueError, match="candidate_sha256"):
        open_run(tmp_path, **kwargs)
