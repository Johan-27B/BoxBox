"""Tests for the lightweight Markdown curation report."""

from __future__ import annotations

from pathlib import Path

import pytest

from perfrace.curate.report import (
    ReportState,
    read_report,
    update_report,
    update_report_metadata,
)


def _report(tmp_path: Path) -> Path:
    source = Path("perfrace/curate/skill/REPORT_TEMPLATE.md")
    path = tmp_path / "report.md"
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def test_read_and_update_front_matter_preserves_body(tmp_path: Path) -> None:
    path = _report(tmp_path)
    original_body = path.read_text(encoding="utf-8").split("---\n", 2)[2]
    state = ReportState(
        schema=1,
        instance="project--workload",
        status="REVISE",
        realism="APPROVED",
        reliability="APPROVED",
        integrity="REVISE",
        updated="2026-08-29T14:00:00Z",
    )

    update_report(path, state)

    assert read_report(path) == state
    assert path.read_text(encoding="utf-8").split("---\n", 2)[2] == original_body


def test_front_matter_rejects_legacy_disposition_field(tmp_path: Path) -> None:
    path = _report(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "updated: pending\n",
            "updated: pending\ndisposition: ACCEPT\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported fields"):
        read_report(path)


def test_accept_requires_all_reviews_to_be_approved(tmp_path: Path) -> None:
    path = _report(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "status: IN_PROGRESS",
        "status: ACCEPT",
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="ACCEPT requires all reviews"):
        read_report(path)


def test_accept_requires_a_final_instance_id(tmp_path: Path) -> None:
    path = _report(tmp_path)
    text = (
        path.read_text(encoding="utf-8")
        .replace("status: IN_PROGRESS", "status: ACCEPT")
        .replace("realism: PENDING", "realism: APPROVED")
        .replace("integrity: PENDING", "integrity: APPROVED")
        .replace("reliability: PENDING", "reliability: APPROVED")
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="ACCEPT requires a final instance id"):
        read_report(path)


def test_reviews_must_follow_pipeline_order(tmp_path: Path) -> None:
    path = _report(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "reliability: PENDING",
        "reliability: APPROVED",
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="Reliability review requires approved Realism"):
        read_report(path)

    path = _report(tmp_path)
    text = (
        path.read_text(encoding="utf-8")
        .replace("realism: PENDING", "realism: APPROVED")
        .replace("integrity: PENDING", "integrity: APPROVED")
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Integrity review requires approved Realism and Reliability",
    ):
        read_report(path)


def test_update_metadata_and_timestamp_is_atomic(tmp_path: Path) -> None:
    path = _report(tmp_path)

    update_report_metadata(
        path,
        {
            "Source": "https://github.com/example/project",
            "Started": "2026-08-29T13:00:00Z",
            "Agent cost": "$1.250000",
            "Human interactions": 3,
        },
        updated="2026-08-29T14:00:00Z",
    )

    text = path.read_text(encoding="utf-8")
    assert "| Source | https://github.com/example/project |" in text
    assert "| Started | 2026-08-29T13:00:00Z |" in text
    assert "| Agent cost | $1.250000 |" in text
    assert "| Human interactions | 3 |" in text
    assert read_report(path).updated == "2026-08-29T14:00:00Z"


def test_update_metadata_migrates_legacy_human_comments_row(tmp_path: Path) -> None:
    path = _report(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "| Human interactions | Pending |",
            "| Human comments | Pending |",
        ),
        encoding="utf-8",
    )

    update_report_metadata(
        path,
        {"Human interactions": 4},
        updated="2026-08-30T09:20:00Z",
    )

    text = path.read_text(encoding="utf-8")
    assert "| Human interactions | 4 |" in text
    assert "Human comments" not in text


def test_report_read_and_write_do_not_follow_final_symlink(tmp_path: Path) -> None:
    victim = tmp_path / "victim.md"
    victim.write_text("keep me", encoding="utf-8")
    report = tmp_path / "report.md"
    report.symlink_to(victim)

    with pytest.raises(OSError):
        read_report(report)
    with pytest.raises(OSError):
        update_report_metadata(report, {"Agent cost": "$1"}, updated="now")

    assert victim.read_text(encoding="utf-8") == "keep me"
