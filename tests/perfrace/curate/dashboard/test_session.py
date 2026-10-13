"""Tests for Pair Verification session primitives."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from perfrace.curate.dashboard import session as launcher


def test_normalize_repo_url() -> None:
    assert launcher._normalize_repo_url("https://github.com/Owner/Project.git") == (
        "https://github.com/Owner/Project",
        "owner-project",
    )
    with pytest.raises(ValueError, match="github.com"):
        launcher._normalize_repo_url("https://example.com/owner/project")


def test_initial_prompt_includes_session_inputs(tmp_path: Path) -> None:
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-08-30T10:00:00Z",
        invocation_count=0,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(tmp_path / "workspace"),
        initial_workspace_path=str(tmp_path / "workspace"),
    )

    prompt = launcher._initial_prompt(state, tmp_path / "session")

    assert state.repo_url in prompt
    assert state.session_id in prompt
    assert state.instance_root in prompt
    assert state.initial_workspace_path in prompt


def test_create_and_load_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")

    instance_root = tmp_path / "canonical-instances"
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        instance_root,
    )
    loaded, loaded_dir = launcher.load_session(created.session_id)

    assert loaded == created
    assert loaded_dir == session_dir
    report_path = Path(created.workspace_path) / "report.md"
    report = launcher.read_report(report_path)
    assert report is not None
    assert report.schema == 1
    assert report.instance == "owner-project--pending"
    assert report.status == "IN_PROGRESS"
    assert report.realism == "PENDING"
    assert created.instance_root == str(instance_root.resolve())
    assert created.workspace_path == str(instance_root.resolve() / ".staging" / created.session_id)
    assert created.candidate_agent == "copilot-cli"
    assert created.candidate_model == "test-model"
    assert created.candidate_timeout_seconds == 1800
    assert created.gateway_port > 0
    run_config = yaml.safe_load((session_dir / "run.yaml").read_text(encoding="utf-8"))
    assert run_config["job"]["tasks"] == [{"path": created.workspace_path}]
    assert run_config["job"]["agents"][0]["name"] == "copilot-cli"
    assert run_config["job"]["agents"][0]["model_name"] == "test-model"
    assert run_config["job"]["agents"][0]["override_timeout_sec"] == 1800
    runner = session_dir / "run-pair.sh"
    assert runner.stat().st_mode & 0o111
    runner_text = runner.read_text(encoding="utf-8")
    assert '--job-name "$job_name"' in runner_text
    assert "$(date -u +%Y%m%d-%H%M%S)-$$" in runner_text
    text = report_path.read_text(encoding="utf-8")
    assert "| Source | https://github.com/owner/project |" in text
    assert f"| Started | {created.started_at} |" in text
    assert created.session_id not in text


def test_sessions_for_same_repo_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    instance_root = tmp_path / "instances"

    first, first_dir = launcher.create_session(
        "https://github.com/owner/project", "gpt-5.6-sol", instance_root
    )
    second, second_dir = launcher.create_session(
        "https://github.com/owner/project", "gpt-5.6-sol", instance_root
    )

    assert first.session_id != second.session_id
    assert first_dir != second_dir
    assert (first_dir / "copilot-home").is_dir()
    assert (second_dir / "copilot-home").is_dir()


def test_create_session_scopes_state_and_staging_by_run_id(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions" / "collaborator-20260830"
    instance_root = tmp_path / "instances"

    state, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        instance_root,
        run_id="collaborator-20260830",
        session_root=session_root,
    )
    loaded, loaded_dir = launcher.load_session(
        state.session_id,
        session_root=session_root,
    )

    assert session_dir.parent == session_root
    assert Path(state.workspace_path).parent == (
        instance_root / ".staging" / "collaborator-20260830"
    )
    assert loaded == state
    assert loaded_dir == session_dir


def test_create_session_persists_custom_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")

    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
        candidate_agent="claude-code",
        candidate_model="claude-sonnet-4-5",
        candidate_timeout_seconds=900,
    )

    assert created.candidate_agent == "claude-code"
    assert created.candidate_model == "claude-sonnet-4-5"
    assert created.candidate_timeout_seconds == 900
    raw = json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
    assert raw["candidate_agent"] == "claude-code"
    assert raw["candidate_model"] == "claude-sonnet-4-5"
    assert raw["candidate_timeout_seconds"] == 900
    config = yaml.safe_load((session_dir / "run.yaml").read_text(encoding="utf-8"))
    assert "api_gateway" not in config
    assert config["job"]["agents"][0]["name"] == "claude-code"
    assert config["job"]["agents"][0]["override_timeout_sec"] == 900


def test_session_invocation_lock_detects_an_active_process(tmp_path: Path) -> None:
    assert launcher.session_invocation_active(tmp_path) is False

    with launcher.session_invocation_lock(tmp_path):
        assert launcher.session_invocation_active(tmp_path) is True
        with pytest.raises(launcher.SessionInvocationLockedError):
            with launcher.session_invocation_lock(tmp_path):
                pass

    assert launcher.session_invocation_active(tmp_path) is False


def test_copilot_session_exists_requires_persisted_events(tmp_path: Path) -> None:
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-08-29T00:00:00Z",
        invocation_count=1,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(tmp_path / "workspace"),
        initial_workspace_path=str(tmp_path / "workspace"),
    )
    events_path = tmp_path / "copilot-home" / "session-state" / state.session_id / "events.jsonl"

    assert launcher.copilot_session_exists(state, tmp_path) is False
    events_path.parent.mkdir(parents=True)
    events_path.touch()
    assert launcher.copilot_session_exists(state, tmp_path) is False
    events_path.write_text("{}\n")
    assert launcher.copilot_session_exists(state, tmp_path) is True


def test_promote_staging_workspace_updates_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )

    promoted = launcher.promote_staging_workspace(
        created,
        session_dir,
        "project--real-workload",
    )

    assert Path(promoted.workspace_path).name == "project--real-workload"
    assert Path(promoted.workspace_path, "report.md").is_file()
    assert not Path(created.workspace_path).exists()
    assert launcher.load_session(created.session_id)[0] == promoted
    run_config = yaml.safe_load((session_dir / "run.yaml").read_text(encoding="utf-8"))
    assert run_config["job"]["tasks"] == [{"path": promoted.workspace_path}]
    assert run_config["api_gateway"]["port"] == created.gateway_port


def test_archive_rejected_workspace_updates_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )

    rejected = launcher.archive_rejected_workspace(
        created,
        session_dir,
        "review-run",
    )

    expected = (tmp_path / "instances" / ".reject" / "review-run" / created.session_id).resolve()
    assert rejected.workspace_path == str(expected)
    assert (expected / "report.md").is_file()
    assert not Path(created.workspace_path).exists()
    assert launcher.load_session(created.session_id)[0] == rejected
    run_config = yaml.safe_load((session_dir / "run.yaml").read_text(encoding="utf-8"))
    assert run_config["job"]["tasks"] == [{"path": rejected.workspace_path}]


def test_archive_rejected_workspace_rejects_arbitrary_nested_path(tmp_path: Path) -> None:
    workspace = tmp_path / "instances" / "unrelated" / "nested"
    workspace.mkdir(parents=True)
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-09-01T04:00:00Z",
        invocation_count=0,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(workspace),
        initial_workspace_path=str(workspace),
        run_id="review-run",
    )

    with pytest.raises(ValueError, match="not a task directory"):
        launcher.archive_rejected_workspace(state, session_dir, "review-run")


def test_archive_rejected_workspace_rejects_file_source(tmp_path: Path) -> None:
    source = tmp_path / "instances" / ".staging" / "session" / "report.md"
    source.parent.mkdir(parents=True)
    source.write_text("not a workspace\n")
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-09-01T04:00:00Z",
        invocation_count=0,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(source),
        initial_workspace_path=str(source),
        run_id="review-run",
    )

    with pytest.raises(ValueError, match="not a real directory"):
        launcher.archive_rejected_workspace(state, session_dir, "review-run")


def test_archive_rejected_workspace_rejects_top_level_symlink(tmp_path: Path) -> None:
    real_workspace = tmp_path / "instances" / "real--workspace"
    real_workspace.mkdir(parents=True)
    linked_workspace = tmp_path / "instances" / "linked--workspace"
    linked_workspace.symlink_to(real_workspace, target_is_directory=True)
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-09-01T04:00:00Z",
        invocation_count=0,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(linked_workspace),
        initial_workspace_path=str(linked_workspace),
        run_id="review-run",
    )

    with pytest.raises(ValueError, match="symbolic link"):
        launcher.archive_rejected_workspace(state, session_dir, "review-run")

    assert real_workspace.is_dir()
    assert linked_workspace.is_symlink()


def test_archive_rejected_workspace_rejects_symlinked_archive_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "instances" / ".reject").symlink_to(
        outside,
        target_is_directory=True,
    )

    with pytest.raises(ValueError, match="symbolic link"):
        launcher.archive_rejected_workspace(created, session_dir, "review-run")

    assert Path(created.workspace_path).is_dir()
    assert list(outside.iterdir()) == []


def test_archive_rejected_workspace_rejects_noncanonical_archive_path(
    tmp_path: Path,
) -> None:
    workspace = (
        tmp_path / "instances" / ".reject" / "other-run" / "00000000-0000-4000-8000-000000000001"
    )
    workspace.mkdir(parents=True)
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-09-01T04:00:00Z",
        invocation_count=0,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(workspace),
        initial_workspace_path=str(workspace),
        run_id="review-run",
    )

    with pytest.raises(ValueError, match="unexpected archive path"):
        launcher.archive_rejected_workspace(state, session_dir, "review-run")


def test_load_session_completes_promotion_after_pre_rename_crash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    destination = tmp_path / "instances" / "project--recovered"
    launcher.write_text(
        session_dir / launcher.PROMOTION_FILENAME,
        json.dumps(
            {
                "source": created.workspace_path,
                "destination": str(destination),
            }
        ),
    )

    recovered, _ = launcher.load_session(created.session_id)

    assert recovered.workspace_path == str(destination.resolve())
    assert destination.is_dir()
    assert not (session_dir / launcher.PROMOTION_FILENAME).exists()


def test_load_session_recovers_promotion_after_post_rename_crash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    source = Path(created.workspace_path)
    destination = tmp_path / "instances" / "project--recovered"
    launcher.write_text(
        session_dir / launcher.PROMOTION_FILENAME,
        json.dumps(
            {
                "source": str(source),
                "destination": str(destination),
            }
        ),
    )
    source.rename(destination)

    recovered, _ = launcher.load_session(created.session_id)

    assert recovered.workspace_path == str(destination.resolve())
    assert destination.is_dir()
    assert not (session_dir / launcher.PROMOTION_FILENAME).exists()


def test_load_session_completes_rejection_after_pre_rename_crash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    destination = tmp_path / "instances" / ".reject" / "review-run" / created.session_id
    launcher.write_text(
        session_dir / launcher.REJECTION_FILENAME,
        json.dumps(
            {
                "source": created.workspace_path,
                "destination": str(destination),
            }
        ),
    )

    recovered, _ = launcher.load_session(created.session_id)

    assert recovered.workspace_path == str(destination.resolve())
    assert destination.is_dir()
    assert not (session_dir / launcher.REJECTION_FILENAME).exists()


def test_load_session_rejects_rejection_marker_for_arbitrary_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    unrelated = tmp_path / "instances" / "unrelated" / "nested"
    unrelated.mkdir(parents=True)
    destination = tmp_path / "instances" / ".reject" / "review-run" / created.session_id
    launcher.write_text(
        session_dir / launcher.REJECTION_FILENAME,
        json.dumps(
            {
                "source": str(unrelated),
                "destination": str(destination),
            }
        ),
    )

    with pytest.raises(ValueError, match="does not match session workspace"):
        launcher.load_session(created.session_id)

    assert unrelated.is_dir()
    assert not destination.exists()


def test_load_session_rejects_rejection_marker_for_another_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    first, first_dir = launcher.create_session(
        "https://github.com/owner/first",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    second, _ = launcher.create_session(
        "https://github.com/owner/second",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    destination = tmp_path / "instances" / ".reject" / "review-run" / first.session_id
    launcher.write_text(
        first_dir / launcher.REJECTION_FILENAME,
        json.dumps(
            {
                "source": second.workspace_path,
                "destination": str(destination),
            }
        ),
    )

    with pytest.raises(ValueError, match="does not match session workspace"):
        launcher.load_session(first.session_id)

    assert Path(first.workspace_path).is_dir()
    assert Path(second.workspace_path).is_dir()
    assert not destination.exists()


def test_load_session_rejects_file_at_rejection_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
        run_id="review-run",
    )
    source = Path(created.workspace_path)
    source.rename(tmp_path / "source-backup")
    destination = tmp_path / "instances" / ".reject" / "review-run" / created.session_id
    destination.parent.mkdir(parents=True)
    destination.write_text("not a workspace\n")
    launcher.write_text(
        session_dir / launcher.REJECTION_FILENAME,
        json.dumps(
            {
                "source": str(source),
                "destination": str(destination),
            }
        ),
    )

    with pytest.raises(ValueError, match="destination is not a real directory"):
        launcher.load_session(created.session_id)


def test_invocation_reloads_promoted_state_before_metric_sync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    created, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    captured_paths: list[str] = []

    monkeypatch.setattr(launcher, "_perfrace_cli_dir", lambda: tmp_path)
    monkeypatch.setattr(launcher, "register_skill", lambda _home: None)
    monkeypatch.setattr(
        launcher,
        "build_copilot_command",
        lambda *_args, **_kwargs: (["copilot"], {}),
    )
    monkeypatch.setattr(
        launcher,
        "sync_report_metrics",
        lambda state, _session_dir: captured_paths.append(state.workspace_path) or [],
    )
    monkeypatch.setattr(launcher, "aggregate_usage", lambda _session_dir: None)

    def fake_run(*_args, **_kwargs):
        current, _ = launcher.load_session(created.session_id)
        launcher.promote_staging_workspace(
            current,
            session_dir,
            "project--promoted",
        )
        return subprocess.CompletedProcess(["copilot"], 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = launcher._run_session_invocation_unlocked(
        created,
        session_dir,
        resume=False,
    )

    assert result == 0
    assert captured_paths == [str(tmp_path / "instances" / "project--promoted")]


def test_aggregate_usage_sums_invocations_models_and_cache_tokens(tmp_path: Path) -> None:
    payloads = [
        {
            "totalUserRequests": 2,
            "modelMetrics": {
                "gpt-5.6-sol": {
                    "usage": {
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "cacheReadTokens": 30,
                        "cacheWriteTokens": 40,
                    }
                }
            },
        },
        {
            "totalUserRequests": 3,
            "modelMetrics": {
                "gpt-5.6-sol": {
                    "usage": {
                        "inputTokens": 10,
                        "outputTokens": 2,
                        "cacheReadTokens": 0,
                        "cacheWriteTokens": 0,
                    }
                },
                "gpt-5-mini": {
                    "usage": {
                        "inputTokens": 5,
                        "outputTokens": 1,
                        "cacheReadTokens": 0,
                        "cacheWriteTokens": 0,
                    }
                },
            },
        },
    ]
    for index, payload in enumerate(payloads, start=1):
        (tmp_path / f"usage-{index:04d}.json").write_text(json.dumps(payload))

    assert launcher.aggregate_usage(tmp_path) == (208, 5)


def test_estimate_session_cost_requires_a_configured_model(tmp_path: Path) -> None:
    payload = {
        "totalUserRequests": 1,
        "modelMetrics": {
            "unpriced-model": {
                "usage": {
                    "inputTokens": 100,
                    "outputTokens": 10,
                    "cacheReadTokens": 0,
                    "cacheWriteTokens": 0,
                }
            }
        },
    }
    (tmp_path / "usage-0001.json").write_text(json.dumps(payload))

    assert launcher.estimate_session_cost_usd(tmp_path) is None


def test_usage_payload_must_be_an_object(tmp_path: Path) -> None:
    (tmp_path / "usage-0001.json").write_text("[]")

    with pytest.raises(ValueError, match="must be an object"):
        launcher.estimate_session_cost_usd(tmp_path)


def test_estimate_session_cost_does_not_double_count_cache_writes(tmp_path: Path) -> None:
    payload = {
        "totalUserRequests": 1,
        "modelMetrics": {
            "gpt-5.6-sol": {
                "usage": {
                    "inputTokens": 100,
                    "outputTokens": 10,
                    "cacheReadTokens": 20,
                    "cacheWriteTokens": 30,
                }
            }
        },
    }
    (tmp_path / "usage-0001.json").write_text(json.dumps(payload))

    assert launcher.estimate_session_cost_usd(tmp_path) == pytest.approx(0.00071)


def test_sync_report_metrics_updates_only_session_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    usage = {
        "totalUserRequests": 4,
        "modelMetrics": {
            "gpt-5.6-sol": {
                "usage": {
                    "inputTokens": 100,
                    "outputTokens": 10,
                    "cacheReadTokens": 20,
                    "cacheWriteTokens": 30,
                }
            }
        },
    }
    (session_dir / "usage-0001.json").write_text(json.dumps(usage))
    report_path = Path(state.workspace_path) / "report.md"
    events_path = (
        session_dir / "copilot-home" / "session-state" / state.session_id / "events.jsonl"
    )
    events_path.parent.mkdir(parents=True)
    events = [
        {
            "type": "user.message",
            "data": {"content": launcher._initial_prompt(state, session_dir)},
        },
        {"type": "assistant.message", "data": {"content": "brief"}},
        {"type": "user.message", "data": {"content": "Why is this workload realistic?"}},
        {"type": "user.message", "data": {"content": "Approve Realism."}},
    ]
    events_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")

    assert launcher.sync_report_metrics(state, session_dir) == [report_path]
    updated = report_path.read_text(encoding="utf-8")
    assert "| Agent cost | $0.000710 |" in updated
    assert "| Human interactions | 2 |" in updated
    assert "updated: pending" not in updated


def test_sync_report_metrics_skips_malformed_unrelated_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = launcher.create_session(
        "https://github.com/owner/project",
        "gpt-5.6-sol",
        tmp_path / "canonical",
    )
    (session_dir / "usage-0001.json").write_text(
        json.dumps(
            {
                "totalUserRequests": 1,
                "modelMetrics": {
                    "gpt-5.6-sol": {
                        "usage": {
                            "inputTokens": 100,
                            "outputTokens": 10,
                            "cacheReadTokens": 20,
                            "cacheWriteTokens": 30,
                        }
                    }
                },
            }
        )
    )
    unrelated = tmp_path / "canonical" / "a-unrelated" / "report.md"
    unrelated.parent.mkdir()
    unrelated.write_text("---\nmalformed\n---\n", encoding="utf-8")

    updated = launcher.sync_report_metrics(state, session_dir)

    assert updated == [Path(state.workspace_path) / "report.md"]


def test_build_copilot_command_uses_byok_and_yolo_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher.shutil, "which", lambda command: f"/usr/bin/{command}")
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-08-28T00:00:00Z",
        invocation_count=1,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(tmp_path),
        initial_workspace_path=str(tmp_path),
    )

    command, env = launcher.build_copilot_command(
        state,
        tmp_path,
        tmp_path / "usage-0001.json",
        proxy_url="http://127.0.0.1:43210/v1",
        resume=False,
    )

    assert "--session-id" in command
    assert "-i" in command
    assert command[command.index("--add-dir") + 1] == str(tmp_path)
    assert "--yolo" in command
    assert "--allow-all" not in command
    assert "--allow-all-tools" not in command
    assert "--allow-all-paths" not in command
    assert command[command.index("--log-level") + 1] == "info"
    prompt = command[command.index("-i") + 1]
    assert env["PERFRACE_RUN_CONFIG"] in prompt
    assert env["PERFRACE_RUNNER"] in prompt
    assert env["COPILOT_PROVIDER_BASE_URL"] == "http://127.0.0.1:43210/v1"
    assert env["COPILOT_PROVIDER_WIRE_API"] == "responses"
    assert env["COPILOT_HOME"] == str(tmp_path / "copilot-home")
    assert env["COPILOT_OTEL_FILE_EXPORTER_PATH"].endswith("otel-0001.jsonl")
    assert env["PERFRACE_RUN_CONFIG"] == str((tmp_path / "run.yaml").resolve())
    assert env["PERFRACE_RUNNER"] == str((tmp_path / "run-pair.sh").resolve())
    assert env["PATH"].split(":", 1)[0] == str(launcher.PROJECT_ROOT / ".venv" / "bin")
    assert command[command.index("-C") + 1] == str(tmp_path)


def test_build_copilot_command_resumes_without_new_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher.shutil, "which", lambda command: f"/usr/bin/{command}")
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-08-28T00:00:00Z",
        invocation_count=2,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(tmp_path),
        initial_workspace_path=str(tmp_path),
    )

    command, _ = launcher.build_copilot_command(
        state,
        tmp_path,
        tmp_path / "usage-0002.json",
        proxy_url="http://127.0.0.1:43210/v1",
        resume=True,
    )

    assert command[-2:] == ["--resume", state.session_id]
    assert "-i" not in command


def test_perfrace_cli_prefers_workspace_virtualenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = tmp_path / ".venv" / "bin" / "perfrace"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\n", encoding="utf-8")
    cli.chmod(0o755)
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda _command: "/other/perfrace")

    assert launcher._perfrace_cli_dir() == cli.parent


def test_perfrace_cli_falls_back_to_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda _command: "/opt/bin/perfrace")

    assert launcher._perfrace_cli_dir() == Path("/opt/bin")


def test_perfrace_cli_missing_has_clear_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda _command: None)

    with pytest.raises(RuntimeError, match="perfrace CLI is unavailable"):
        launcher._perfrace_cli_dir()


def test_worker_retries_startup_failure_without_resuming_missing_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = launcher.SessionState(
        session_id="00000000-0000-4000-8000-000000000001",
        repo_url="https://github.com/owner/project",
        model="gpt-5.6-sol",
        started_at="2026-08-29T00:00:00Z",
        invocation_count=1,
        instance_root=str(tmp_path / "instances"),
        workspace_path=str(tmp_path / "workspace"),
        initial_workspace_path=str(tmp_path / "workspace"),
    )
    calls: list[bool] = []

    def run_invocation(_state, _session_dir, *, resume):
        calls.append(resume)
        if len(calls) == 1:
            raise RuntimeError("proxy startup failed")
        return 0

    monkeypatch.setattr(launcher, "load_session", lambda _session_id: (state, tmp_path))
    monkeypatch.setattr(launcher, "run_session_invocation", run_invocation)
    monkeypatch.setattr(launcher, "_wait_for_resume", lambda: True)
    monkeypatch.setattr(launcher, "_disposition", lambda _session_id: "ACCEPT")

    assert launcher.supervise(state.session_id) == 0

    assert calls == [False, False]
    worker_state = json.loads((tmp_path / "worker-state.json").read_text())
    assert worker_state == {
        "state": "completed",
        "return_code": 0,
        "message": "ACCEPT",
    }


def test_worker_disposition_reads_markdown_front_matter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher, "SESSION_ROOT", tmp_path / "sessions")
    state, session_dir = launcher.create_session(
        "https://github.com/example/project",
        "gpt-5.6-sol",
        tmp_path / "instances",
    )
    launcher.update_report(
        Path(state.workspace_path) / "report.md",
        launcher.ReportState(
            schema=1,
            instance="project--workload",
            status="ACCEPT",
            realism="APPROVED",
            integrity="APPROVED",
            reliability="APPROVED",
            updated="2026-08-29T14:00:00Z",
        ),
    )
    monkeypatch.setattr(launcher, "load_session", lambda _session_id: (state, session_dir))

    assert launcher._disposition(state.session_id) == "ACCEPT"


def test_session_module_worker_subcommand(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "00000000-0000-4000-8000-000000000001"
    session_root = tmp_path / "sessions"
    session_dir = session_root / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "state.json").write_text("{}\n", encoding="utf-8")
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(launcher, "SESSION_ROOT", session_root)
    monkeypatch.setattr(
        launcher,
        "supervise",
        lambda value, *, wait_for_resume=False: calls.append((value, wait_for_resume)) or 7,
    )

    assert launcher.main(["worker", session_id, "--wait-for-resume"]) == 7
    assert calls == [(session_id, True)]
