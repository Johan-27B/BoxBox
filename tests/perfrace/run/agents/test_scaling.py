from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest
from harbor.environments.base import ExecResult
from harbor.models.agent.context import AgentContext

from perfrace.evolution.evolver import EvolutionOutcome
from perfrace.evolution.meta import MetaAgentEndpoint
from perfrace.evolution.runtime_repository import RuntimeSnapshot
from perfrace.installed.scaling import HarnessScalingAgent, HarnessScalingRound
from perfrace.run.types import Measurement
from boxbox.terminus_boxbox import harness
from boxbox.terminus_boxbox.kernel.interfaces import RuntimeTrap
from boxbox.terminus_boxbox.seed import fingerprint
from perfrace.evolution.runtime_repository import RuntimeRepository
from perfrace.evolution.loader import StaticRuntime, validate_harness_source


async def test_setup_uses_shared_h0_and_container_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr("harbor.agents.terminus_2.terminus_2.Terminus2.setup", AsyncMock())
    source = Path(harness.__file__).parent
    before = fingerprint(source)
    agent = HarnessScalingAgent(
        logs_dir=tmp_path / "logs",
        model_name="openai/test",
        extra_env={"LLM_BASE_URL": "http://localhost/v1", "LLM_API_KEY": "test"},
    )
    # No environment_dir or host-side task sources: these come from the image.
    environment = SimpleNamespace(
        task_env_config=SimpleNamespace(workdir="/workspace/project"),
        default_user="root",
        exec=AsyncMock(return_value=ExecResult(stdout="a" * 40, return_code=0)),
    )
    await agent.setup(environment)
    assert fingerprint(agent._repository.path) == before
    assert fingerprint(source) == before
    agent._runtime._runtime.configure_target_phase(boxbox_enabled=False)
    tools = {
        tool["function"]["name"] for tool in agent._runtime._runtime._get_tool_definitions()
    }
    assert "submit" in tools and "boxbox" not in tools
    assert agent._target_base_commits == {".": "a" * 40}
    # Evidence bookkeeping uses external Git metadata, never the project's .git.
    assert all(
        not path.startswith("/workspace/project/") for path in agent._target_git_dirs.values()
    )


async def test_hs_attempt_accepts_submission_without_review(tmp_path):
    runtime_class = validate_harness_source(Path(harness.__file__).parent, identity="h0")
    runtime = runtime_class(
        logs_dir=tmp_path, model_name="openai/test", completion_name="submit"
    )
    runtime.ensure_agent_session = AsyncMock()
    runtime.run_until_trap = AsyncMock(return_value=RuntimeTrap.COMPLETE)
    static = StaticRuntime(runtime)
    await static.run("Optimize this task.", object(), AgentContext())
    tools = {tool["function"]["name"] for tool in runtime._get_tool_definitions()}
    assert "submit" in tools and "boxbox" not in tools
    runtime.run_until_trap.return_value = RuntimeTrap.BOXBOX
    with pytest.raises(RuntimeError, match="unsupported trap"):
        await static.run("Continue.", object(), AgentContext())


async def test_hs_retained_revision_still_creates_fresh_context(tmp_path, monkeypatch):
    monkeypatch.setattr("harbor.agents.terminus_2.terminus_2.Terminus2.setup", AsyncMock())
    repository = RuntimeRepository.initialize(
        Path(harness.__file__).parent, tmp_path / "repository"
    )
    snapshot = repository.validate_head()
    agent = HarnessScalingAgent(logs_dir=tmp_path / "logs", model_name="openai/test")
    agent._repository = repository
    old = agent._load_runtime(snapshot)
    old._runtime.set_task_instruction("The original instruction.")
    old._runtime._pending_chat_state = {"messages": [{"role": "user", "content": "old work"}]}
    agent._runtime = old
    agent._round_number += 1
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "candidate.txt").write_text("Accepted project progress.")
    environment = SimpleNamespace(exec=AsyncMock())
    await agent._replace_runtime(snapshot, environment)
    assert agent._runtime is not old
    assert agent._runtime._pending_chat_state is None
    assert (workspace / "candidate.txt").read_text() == "Accepted project progress."
    environment.exec.assert_not_awaited()


def make_agent(tmp_path: Path) -> HarnessScalingAgent:
    return HarnessScalingAgent(
        logs_dir=tmp_path,
        model_name="gpt-test",
        extra_env={
            "LLM_BASE_URL": "http://host.docker.internal:4015/v1",
            "LLM_API_KEY": "test-key",
        },
        harness_source=tmp_path / "runtime",
        reasoning_effort="high",
    )


def test_campaign_budget_is_observed_and_validated(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent._measurement_overhead_sec = 45

    agent.set_checkpoint_budget(total_sec=14_400, remaining_sec=12_345)

    assert agent._remaining_sec == 12_300
    with pytest.raises(ValueError, match="usable shared campaign budget"):
        agent.set_checkpoint_budget(total_sec=300, remaining_sec=300)
    with pytest.raises(ValueError, match="invalid remaining budget"):
        agent.set_checkpoint_budget(total_sec=14_400, remaining_sec=14_401)


def test_meta_endpoint_can_reuse_trial_token_proxy_key() -> None:
    endpoint = MetaAgentEndpoint(
        base_url="http://127.0.0.1:4015/v1",
        token_proxy_secret="unused",
        model="gpt-test",
        reasoning_effort="high",
        session_prefix="campaign",
        fixed_api_key="trial-key",
    )

    assert endpoint.api_key_for("campaign-evolve") == "trial-key"


def test_checkpoint_fingerprint_disables_measurement_reuse(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    environment = AsyncMock()

    fingerprint = asyncio.run(agent.checkpoint_fingerprint(environment))

    assert fingerprint is None
    environment.exec.assert_not_awaited()




def test_setup_runtime_retries_one_tmux_cleanup_race(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    session = AsyncMock()
    session._session_name = "boxbox_runtime"
    session.is_session_alive.side_effect = [True, False]
    runtime = MagicMock()
    runtime._session = session
    runtime.setup = AsyncMock(
        side_effect=[
            RuntimeError("Failed to start tmux session. Error: None"),
            None,
        ]
    )
    agent._runtime = runtime
    environment = AsyncMock()
    environment.default_user = "user"
    environment.exec.return_value = ExecResult(stdout="", stderr="", return_code=0)

    asyncio.run(agent._setup_runtime(environment))

    assert runtime.setup.await_count == 2
    session.stop.assert_awaited_once()
    environment.exec.assert_awaited_once_with(
        command="tmux kill-session -t boxbox_runtime",
        user="user",
    )


def test_stop_runtime_session_accepts_already_stopped_tmux(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    session = AsyncMock()
    session.is_session_alive.return_value = False
    runtime = MagicMock()
    runtime._session = session
    agent._runtime = runtime
    environment = AsyncMock()

    asyncio.run(agent._stop_runtime_session(environment))

    session.stop.assert_awaited_once()
    environment.exec.assert_not_awaited()


def test_replace_retained_runtime_starts_fresh_instance(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    snapshot = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    previous_runtime = MagicMock()
    fresh_runtime = MagicMock()
    agent._runtime = previous_runtime
    agent._active_snapshot = snapshot
    agent._stop_runtime_session = AsyncMock()
    agent._load_runtime = MagicMock(return_value=fresh_runtime)
    agent._setup_runtime = AsyncMock()
    environment = AsyncMock()

    asyncio.run(agent._replace_runtime(snapshot, environment))

    agent._stop_runtime_session.assert_awaited_once_with(environment)
    agent._load_runtime.assert_called_once_with(snapshot)
    agent._setup_runtime.assert_awaited_once_with(environment)
    assert agent._runtime is fresh_runtime
    assert agent._active_snapshot == snapshot
    previous_runtime.export_state.assert_not_called()
    fresh_runtime.import_state.assert_not_called()




def test_record_measurement_records_each_runtime_without_workspace_snapshot(
    tmp_path: Path,
) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._round_started_at = 2.0
    agent._active_snapshot = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    agent._persist_round_evidence = AsyncMock()
    environment = AsyncMock()

    asyncio.run(
        agent.record_measurement(
            Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=5.0,
            ),
            environment,
        )
    )
    agent._round_number = 2
    agent._round_started_at = 3.0
    asyncio.run(
        agent.record_measurement(
            Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=7.0,
            ),
            environment,
        )
    )

    summary = json.loads((tmp_path / "harness-scaling" / "state.json").read_text())
    assert summary["task_id"] == "task-a"
    assert summary["schema_version"] == 2
    assert len(summary["rounds"]) == 2
    assert {round_record["measurement"]["value"] for round_record in summary["rounds"]} == {
        5.0,
        7.0,
    }
    assert all("target_snapshot" not in round_record for round_record in summary["rounds"])


def test_delivery_measurement_does_not_create_another_round(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._final_delivery = True
    measurement = Measurement(
        verdict="ACCEPTED",
        metric="wall-clock",
        unit="seconds",
        value=4.0,
    )

    asyncio.run(agent.record_measurement(measurement, AsyncMock()))

    assert agent._rounds == []
    assert (tmp_path / "harness-scaling" / "final-measurement.json").is_file()


def test_finalize_uses_current_runtime_and_workspace(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    runtime = MagicMock()
    runtime.finalize = AsyncMock()
    agent._runtime = runtime
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent.finalize("deliver now", environment, context))

    runtime.finalize.assert_awaited_once_with("deliver now", environment, context)
    assert agent._final_delivery is True
    assert agent._rounds == []
    summary = json.loads((tmp_path / "harness-scaling" / "state.json").read_text())
    assert summary["completed_at"] is not None


def test_finalize_closes_only_pending_tool_calls(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    chat = MagicMock()
    chat._messages = [
        {"role": "system", "content": "system"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-complete",
                    "function": {"name": "execute_commands", "arguments": "{}"},
                },
                {
                    "id": "call-pending",
                    "function": {"name": "image_read", "arguments": "{}"},
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-complete",
            "content": "command output",
        },
    ]
    runtime = MagicMock()
    runtime._chat = chat
    runtime._pending_chat_state = {
        "schema_version": 1,
        "messages": json.loads(json.dumps(chat._messages)),
    }
    runtime.finalize = AsyncMock()
    agent._runtime = runtime
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent.finalize("deliver now", environment, context))

    assert chat._messages[-1] == {
        "role": "tool",
        "tool_call_id": "call-pending",
        "content": (
            "image_read was interrupted when the previous Harness Scaling target phase ended. "
            "Continue final delivery from the current workspace and inspect its state before "
            "assuming the tool completed."
        ),
    }
    assert runtime._pending_chat_state["messages"][-1] == chat._messages[-1]
    chat.reset_response_chain.assert_called_once_with()
    assert agent._complete_pending_tool_calls() == 0
    assert context.metadata["harness_scaling"]["repaired_pending_tool_calls"] == 1
    runtime.finalize.assert_awaited_once_with("deliver now", environment, context)


def test_prepare_final_checkpoint_only_marks_final_measurement(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    environment = AsyncMock()

    asyncio.run(agent.prepare_final_checkpoint(environment))

    assert agent._final_delivery is True
    environment.assert_not_awaited()
    summary = json.loads((tmp_path / "harness-scaling" / "state.json").read_text())
    assert summary["completed_at"] is not None


def test_resume_evolves_then_restarts_runtime_on_current_workspace(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._task_instruction = "optimize the task"
    agent._remaining_sec = 1_000
    current = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    agent._active_snapshot = current
    agent._runtime = MagicMock()
    agent._rounds = [
        HarnessScalingRound(
            round=1,
            runtime_commit=current.commit,
            measurement=Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=5.0,
            ),
            started_at=2.0,
            completed_at=3.0,
        )
    ]

    successor = RuntimeSnapshot(
        commit="1" * 40,
        tree="2" * 40,
        source_sha256="3" * 64,
    )
    agent._evolve = AsyncMock(
        return_value=EvolutionOutcome(
            snapshot=successor,
            retained=False,
            manifest_path=tmp_path / "manifest.json",
            result_path=tmp_path / "result.md",
        )
    )
    agent._replace_runtime = AsyncMock()
    agent._start_round = AsyncMock()
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent.resume("verifier feedback", environment, context))

    agent._evolve.assert_awaited_once_with(environment)
    agent._replace_runtime.assert_awaited_once_with(successor, environment)
    agent._start_round.assert_awaited_once_with(environment, context)
    assert agent._round_number == 2
    assert agent._rounds[0].successor_commit == successor.commit
    assert agent._rounds[0].transition_started_at is not None
    assert agent._rounds[0].transition_completed_at is not None


def test_resume_rolls_back_when_successor_activation_fails(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._task_instruction = "optimize"
    agent._remaining_sec = 1_000
    current = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    successor = RuntimeSnapshot(
        commit="1" * 40,
        tree="2" * 40,
        source_sha256="3" * 64,
    )
    agent._active_snapshot = current
    agent._last_verified_snapshot = current
    agent._runtime = MagicMock()
    agent._rounds = [
        HarnessScalingRound(
            round=1,
            runtime_commit=current.commit,
            measurement=Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=1.0,
            ),
            started_at=2.0,
            completed_at=3.0,
        )
    ]
    agent._evolve = AsyncMock(
        return_value=EvolutionOutcome(
            snapshot=successor,
            retained=False,
            manifest_path=tmp_path / "manifest.json",
            result_path=tmp_path / "result.md",
        )
    )
    agent._replace_runtime = AsyncMock(
        side_effect=[
            TypeError("runtime identity fields are not writable"),
            None,
        ]
    )
    agent._start_round = AsyncMock()
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent._resume_after_measurement(environment, context))

    assert agent._round_number == 2
    assert [call.args[0] for call in agent._replace_runtime.await_args_list] == [
        successor,
        current,
    ]
    assert agent._rounds[0].successor_commit == current.commit
    agent._start_round.assert_awaited_once_with(environment, context)
    failure = tmp_path / "harness-scaling" / "rounds" / "0001" / "runtime-activation-failure.json"
    assert json.loads(failure.read_text()) == {
        "failed_runtime": successor.commit,
        "rollback_runtime": current.commit,
        "failure": "TypeError: runtime identity fields are not writable",
    }


def test_start_round_uses_only_original_instruction(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent._task_instruction = "optimize the task"
    agent._remaining_sec = 1_000
    agent._active_snapshot = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    runtime = MagicMock()
    runtime.run = AsyncMock()
    runtime.session_id = "task-a-round-0001"
    agent._runtime = runtime
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent._start_round(environment, context))

    runtime.run.assert_awaited_once_with("optimize the task", environment, context)
    assert context.metadata["harness_scaling"]["runtime_session_id"] == "task-a-round-0001"


def test_runtime_fault_schedules_verified_harness_rollback(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent._task_instruction = "optimize"
    agent._remaining_sec = 1_000
    fallback = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    failed = RuntimeSnapshot(
        commit="1" * 40,
        tree="2" * 40,
        source_sha256="3" * 64,
    )
    runtime = MagicMock()
    runtime.run = AsyncMock(side_effect=ValueError("broken evolved runtime"))
    agent._runtime = runtime
    agent._active_snapshot = failed
    agent._last_verified_snapshot = fallback

    with pytest.raises(ValueError, match="broken evolved runtime"):
        asyncio.run(agent._start_round(AsyncMock(), AgentContext()))

    assert agent._pending_runtime_rollback == fallback
    assert agent._round_fault == "ValueError: broken evolved runtime"


def test_runtime_fault_restarts_even_when_verified_commit_is_unchanged(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent._task_instruction = "optimize"
    agent._remaining_sec = 1_000
    snapshot = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    runtime = MagicMock()
    runtime.run = AsyncMock(side_effect=ValueError("transient runtime failure"))
    agent._runtime = runtime
    agent._active_snapshot = snapshot
    agent._last_verified_snapshot = snapshot

    with pytest.raises(ValueError, match="transient runtime failure"):
        asyncio.run(agent._start_round(AsyncMock(), AgentContext()))

    assert agent._pending_runtime_rollback == snapshot


def test_resume_retains_verified_harness_when_evolver_fails(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._task_instruction = "optimize"
    agent._remaining_sec = 1_000
    snapshot = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    agent._active_snapshot = snapshot
    agent._rounds = [
        HarnessScalingRound(
            round=1,
            runtime_commit=snapshot.commit,
            measurement=Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=1.0,
            ),
            started_at=2.0,
            completed_at=3.0,
        )
    ]
    agent._runtime = MagicMock()
    agent._evolve = AsyncMock(side_effect=ValueError("invalid manifest"))
    agent._replace_runtime = AsyncMock()
    agent._start_round = AsyncMock()
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent._resume_after_measurement(environment, context))

    assert agent._round_number == 2
    assert agent._rounds[0].successor_commit == snapshot.commit
    assert agent._rounds[0].transition_completed_at is not None
    agent._replace_runtime.assert_awaited_once_with(snapshot, environment)
    agent._start_round.assert_awaited_once_with(environment, context)
    failure = tmp_path / "harness-scaling" / "rounds" / "0001" / "evolution-failure.json"
    assert json.loads(failure.read_text()) == {
        "runtime_commit": snapshot.commit,
        "failure": "ValueError: invalid manifest",
        "outcome": "retained",
    }


def test_evolution_without_transition_does_not_record_successor(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._task_instruction = "optimize"
    agent._minimum_stage_time_sec = 60
    agent._remaining_sec = 60.001
    current = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    successor = RuntimeSnapshot(
        commit="1" * 40,
        tree="2" * 40,
        source_sha256="3" * 64,
    )
    agent._active_snapshot = current
    agent._runtime = MagicMock()
    agent._rounds = [
        HarnessScalingRound(
            round=1,
            runtime_commit=current.commit,
            measurement=Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=1.0,
            ),
            started_at=2.0,
            completed_at=3.0,
        )
    ]

    async def evolve(_environment) -> EvolutionOutcome:
        await asyncio.sleep(0.01)
        return EvolutionOutcome(
            snapshot=successor,
            retained=False,
            manifest_path=tmp_path / "manifest.json",
            result_path=tmp_path / "result.md",
        )

    agent._evolve = AsyncMock(side_effect=evolve)
    agent._replace_runtime = AsyncMock()
    agent._start_round = AsyncMock()

    asyncio.run(agent._resume_after_measurement(AsyncMock(), AgentContext()))

    assert agent._rounds[0].successor_commit is None
    assert agent._rounds[0].evolution_started_at is not None
    assert agent._rounds[0].evolution_completed_at is not None
    assert agent.checkpoint_trial_skip_to_final_checkpoint() is True
    agent._replace_runtime.assert_not_awaited()
    agent._start_round.assert_not_awaited()


def test_resume_rolls_back_faulty_runtime_without_evolving(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    agent._task_instruction = "optimize"
    agent._remaining_sec = 1_000
    fallback = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    failed = RuntimeSnapshot(
        commit="1" * 40,
        tree="2" * 40,
        source_sha256="3" * 64,
    )
    agent._active_snapshot = failed
    agent._pending_runtime_rollback = fallback
    agent._round_fault = "ValueError: broken evolved runtime"
    agent._round_number = 2
    agent._rounds = [
        HarnessScalingRound(
            round=1,
            runtime_commit=failed.commit,
            measurement=Measurement(
                verdict="WRONG_ANSWER",
                metric="wall-clock",
                unit="seconds",
                value=None,
            ),
            started_at=2.0,
            completed_at=3.0,
        )
    ]
    agent._runtime = MagicMock()
    agent._replace_runtime = AsyncMock()
    agent._start_round = AsyncMock()
    agent._evolve = AsyncMock()
    environment = AsyncMock()
    context = AgentContext()

    asyncio.run(agent._resume_after_measurement(environment, context))

    agent._evolve.assert_not_awaited()
    agent._replace_runtime.assert_awaited_once_with(fallback, environment)
    assert agent._round_number == 2
    assert agent._rounds[0].successor_commit == fallback.commit
    assert agent._rounds[0].transition_completed_at is not None
    assert agent._pending_runtime_rollback is None
    assert agent._round_fault is None
    agent._start_round.assert_awaited_once_with(environment, context)
    rollback = tmp_path / "harness-scaling" / "rounds" / "0001" / "runtime-rollback.json"
    assert json.loads(rollback.read_text()) == {
        "failed_runtime": failed.commit,
        "rollback_runtime": fallback.commit,
        "fault": "ValueError: broken evolved runtime",
    }


def test_prepare_final_checkpoint_restores_verified_runtime(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.session_id = "task-a__trial__agent"
    agent._campaign_started_at = 1.0
    fallback = RuntimeSnapshot(
        commit="a" * 40,
        tree="b" * 40,
        source_sha256="c" * 64,
    )
    failed = RuntimeSnapshot(
        commit="1" * 40,
        tree="2" * 40,
        source_sha256="3" * 64,
    )
    agent._active_snapshot = failed
    agent._pending_runtime_rollback = fallback
    agent._round_fault = "TypeError: invalid evolved runtime"
    agent._round_number = 2
    agent._rounds = [
        HarnessScalingRound(
            round=1,
            runtime_commit=fallback.commit,
            measurement=Measurement(
                verdict="ACCEPTED",
                metric="wall-clock",
                unit="seconds",
                value=1.0,
            ),
            started_at=2.0,
            completed_at=3.0,
        )
    ]
    agent._replace_runtime = AsyncMock()
    environment = AsyncMock()

    asyncio.run(agent.prepare_final_checkpoint(environment))

    agent._replace_runtime.assert_awaited_once_with(fallback, environment)
    assert agent._round_number == 2
    assert agent._pending_runtime_rollback is None
    assert agent._round_fault is None
    assert agent._final_delivery is True
    rollback = tmp_path / "harness-scaling" / "final-runtime-rollback.json"
    assert json.loads(rollback.read_text()) == {
        "failed_runtime": failed.commit,
        "rollback_runtime": fallback.commit,
        "fault": "TypeError: invalid evolved runtime",
    }


def test_persist_round_evidence_records_context_terminal_and_diff(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent._round_number = 1
    agent._round_context = {"metadata": {"harness_scaling": {"round": 1}}}
    agent._target_entries = ("project",)
    agent._target_base_commits = {".": "a" * 40}
    agent._target_git_dirs = {".": "/var/lib/perfrace-harness-scaling/target-git/workspace.git"}
    session = AsyncMock()
    session.capture_pane.return_value = "terminal transcript\n"
    runtime = MagicMock()
    runtime._session = session
    agent._runtime = runtime
    environment = AsyncMock()
    environment.default_user = "user"
    environment.task_env_config.workdir = "/workspace"
    environment.exec.side_effect = [
        ExecResult(stdout=" M src/main.py\n", stderr="", return_code=0),
        ExecResult(stdout="diff --git a/src/main.py b/src/main.py\n", stderr="", return_code=0),
    ]
    measurement = Measurement(
        verdict="ACCEPTED",
        metric="wall-clock",
        unit="seconds",
        value=1.0,
    )

    asyncio.run(agent._persist_round_evidence(environment, measurement))

    target = tmp_path / "harness-scaling" / "rounds" / "0001" / "target"
    assert json.loads((target / "context.json").read_text()) == agent._round_context
    assert not (target / "chat-state.json").exists()
    assert (target / "terminal.txt").read_text() == "terminal transcript\n"
    assert (target / "workspace" / "workspace.status.txt").read_text() == " M src/main.py\n"
    assert "diff --git" in (target / "workspace" / "workspace.diff").read_text()
    assert json.loads((target / "measurement.json").read_text())["verdict"] == "ACCEPTED"
    assert all(call.kwargs["user"] == "root" for call in environment.exec.await_args_list)
