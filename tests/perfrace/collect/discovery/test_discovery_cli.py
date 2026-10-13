from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from perfrace.collect.discovery import cli
from perfrace.collect.discovery.runs import DiscoveryRun


def test_discovery_help_lists_pipeline_commands() -> None:
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "run",
        "harvest",
        "metadata",
        "export",
        "token-status",
    ):
        assert command in result.stdout


def test_run_orchestrates_all_steps(tmp_path: Path, monkeypatch) -> None:
    run_state = DiscoveryRun(
        name="sample",
        root=tmp_path / "sample",
        start_at=datetime(2026, 8, 1, tzinfo=UTC),
        end_at=datetime(2026, 8, 2, tzinfo=UTC),
        authorship_start_at=datetime(2025, 8, 2, tzinfo=UTC),
        authorship_end_at=datetime(2026, 8, 2, tzinfo=UTC),
        bot_config_sha256="a" * 64,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    calls: list[str] = []
    monkeypatch.setattr(cli, "bot_config_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(cli, "open_run", lambda *_args, **_kwargs: run_state)
    monkeypatch.setattr(
        cli,
        "_execute_harvest",
        lambda _run: calls.append("harvest") or 3,
    )
    monkeypatch.setattr(
        cli,
        "_execute_metadata",
        lambda _run, **_kwargs: calls.append("metadata") or (2, 1),
    )
    monkeypatch.setattr(
        cli,
        "_execute_export",
        lambda _run: calls.append("export") or (2, 1),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            "--start-at",
            "2026-08-01T00:00:00Z",
            "--end-at",
            "2026-08-02T00:00:00Z",
            "--run-name",
            "sample",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert calls == ["harvest", "metadata", "export"]
    assert "Discovery run: sample" in result.stdout


def test_run_requires_utc_timestamps(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            "--start-at",
            "2026-08-01T00:00:00+08:00",
            "--end-at",
            "2026-08-02T00:00:00Z",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert "--start-at must use the UTC offset" in result.stderr
