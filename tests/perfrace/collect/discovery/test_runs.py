from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from perfrace.collect.discovery.runs import open_run, step_status, update_step


def test_open_run_creates_and_resumes_matching_manifest(tmp_path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 2, tzinfo=UTC)
    digest = "a" * 64

    created = open_run(
        tmp_path,
        run_name="sample",
        start_at=start,
        end_at=end,
        bot_config_sha256=digest,
    )
    resumed = open_run(
        tmp_path,
        run_name="sample",
        start_at=start,
        end_at=end,
        bot_config_sha256=digest,
    )

    assert resumed == created
    assert step_status(created, "harvest") == "pending"
    assert created.authorship_start_at == datetime(2025, 8, 2, tzinfo=UTC)
    assert created.authorship_end_at == end
    update_step(
        created,
        "harvest",
        status="complete",
        rows=12,
        details={"counts": {"discovered": 12}},
    )
    manifest = json.loads(created.manifest_path.read_text())
    assert manifest["steps"]["harvest"]["rows"] == 12
    assert manifest["counts"]["discovered"] == 12


def test_open_run_rejects_parameter_mismatch(tmp_path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    open_run(
        tmp_path,
        run_name="sample",
        start_at=start,
        end_at=datetime(2026, 8, 2, tzinfo=UTC),
        bot_config_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="incompatible manifest fields"):
        open_run(
            tmp_path,
            run_name="sample",
            start_at=start,
            end_at=datetime(2026, 8, 3, tzinfo=UTC),
            bot_config_sha256="a" * 64,
        )


def test_open_run_generates_timestamp_name(tmp_path: Path) -> None:
    run = open_run(
        tmp_path,
        run_name=None,
        start_at=datetime(2026, 8, 1, tzinfo=UTC),
        end_at=datetime(2026, 8, 2, tzinfo=UTC),
        bot_config_sha256="a" * 64,
    )

    assert run.name.startswith("discover-")
    assert run.root.parent == tmp_path.resolve()
