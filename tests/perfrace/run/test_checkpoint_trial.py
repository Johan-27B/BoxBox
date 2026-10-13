from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.models.agent.context import AgentContext
from harbor.models.trial.config import AgentConfig, TaskConfig, TrialConfig, VerifierConfig
from harbor.models.trial.paths import TrialPaths
from harbor.models.trial.result import ExceptionInfo, StepResult
from harbor.models.verifier.result import VerifierResult
from harbor.trial.errors import AgentTimeoutError

from perfrace.run.services.session_identity import decode_token_proxy_api_key
from perfrace.run.trial import (
    CheckpointTrial,
    _TokenProxyUsage,
    _with_trial_token_proxy_env,
)
from perfrace.run.types import Measurement


def _trial(
    tmp_path: Path,
    *,
    n_checkpoints: int,
) -> CheckpointTrial:
    """Build a CheckpointTrial bypassing __init__ (no real Docker/task
    setup needed), mirroring the object.__new__() + manual-attribute style
    Harbor's own test_multi_step_run_step.py uses for MultiStepTrial.
    """
    trial = object.__new__(CheckpointTrial)
    trial.logger = MagicMock()
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial._result = SimpleNamespace(step_results=None)
    trial._write_progress = MagicMock()
    trial.config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=n_checkpoints * 600))
    trial.agent = SimpleNamespace()
    trial.task = SimpleNamespace(
        instruction="the real task instruction",
        config=SimpleNamespace(
            agent=SimpleNamespace(user=None),
            verifier=SimpleNamespace(user=None),
        ),
    )
    trial._agent_timeout_sec = 3600
    trial._total_agent_budget_sec = 3600 * n_checkpoints
    trial._FINAL_DELIVERY_NOTICE_SEC = 0
    trial._verifier_timeout_sec = 1200
    trial._host_token_proxy_base_url = None
    trial._token_proxy_session_id = "candidate-trial__agent"
    trial._pending_token_proxy_usage = None
    trial._reset_agent_logs_for_checkpoint = AsyncMock()
    trial._reset_shared_verifier_dirs_for_checkpoint = AsyncMock()
    trial._sync_agent_output = AsyncMock()
    trial._upload_agent_logs = AsyncMock()
    trial._collect_artifacts_phased = AsyncMock()
    trial._stop_agent_environment = AsyncMock()
    trial._run_final_delivery = AsyncMock()
    trial._run_final_checkpoint = AsyncMock()
    trial._archive_checkpoint_outputs = MagicMock()
    run_agent_iteration = trial._run_agent_iteration

    async def consume_one_budget_unit(**kwargs):
        step_result, succeeded, _ = await run_agent_iteration(**kwargs)
        return step_result, succeeded, 3600

    trial._run_agent_iteration = AsyncMock(side_effect=consume_one_budget_unit)
    return trial


def test_checkpoint_agent_uses_trial_token_proxy_identity(tmp_path: Path) -> None:
    config = TrialConfig(
        task=TaskConfig(path=tmp_path),
        trial_name="candidate-trial",
        agent=AgentConfig(
            import_path="example:Agent",
            model_name="gpt-5.6-luna",
            task_budget_sec=600,
            env={
                "LLM_BASE_URL": "http://host.docker.internal:4001/v1",
                "LLM_API_KEY": "shared-key",
                "CUSTOM": "preserved",
            },
        ),
        verifier=VerifierConfig(
            kwargs={
                "container_token_proxy_base_url": "http://host.docker.internal:44071",
                "token_proxy_secret": "test-secret",
            }
        ),
    )

    routed = _with_trial_token_proxy_env(config)

    assert routed.agent.env["LLM_BASE_URL"] == "http://host.docker.internal:44071/v1"
    assert routed.agent.env["LLM_MODEL"] == "gpt-5.6-luna"
    assert routed.agent.env["CUSTOM"] == "preserved"
    assert decode_token_proxy_api_key(
        routed.agent.env["LLM_API_KEY"],
        secret="test-secret",
    ) == ("candidate-trial__agent", "gpt-5.6-luna")
    assert config.agent.env["LLM_API_KEY"] == "shared-key"


def test_checkpoint_proxy_usage_overrides_agent_report_after_verification(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    trial._host_token_proxy_base_url = "http://127.0.0.1:44071"
    trial._read_agent_token_proxy_usage = AsyncMock(
        side_effect=[
            _TokenProxyUsage(0, 0, 0, 0, None),
            _TokenProxyUsage(250, 220, 25, 4, 1.25),
        ]
    )
    trial._run_budgeted_verifier_iteration = AsyncMock(return_value=(5.0, None))
    step_result = StepResult(
        step_name="checkpoint-01",
        agent_result=AgentContext(
            n_input_tokens=999,
            n_cache_tokens=999,
            n_output_tokens=999,
            cost_usd=999.0,
            metadata={"agent": "preserved"},
        ),
    )

    async def run() -> None:
        await trial._begin_checkpoint_token_accounting()
        await trial._run_checkpoint_verifier(
            name="checkpoint-01",
            step_result=step_result,
            preserve_agent=True,
            fingerprint=None,
            last_verified_fingerprint=None,
            last_verified_name=None,
        )

    asyncio.run(run())

    assert step_result.agent_result.n_input_tokens == 250
    assert step_result.agent_result.n_cache_tokens == 220
    assert step_result.agent_result.n_output_tokens == 25
    assert step_result.agent_result.cost_usd == pytest.approx(1.25)
    assert step_result.agent_result.metadata == {
        "agent": "preserved",
        "token_accounting": {"source": "token-proxy", "requests": 4},
    }
    assert trial._pending_token_proxy_usage is None


def test_checkpoint_proxy_usage_spans_unverified_turn_until_next_verifier(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    trial._host_token_proxy_base_url = "http://127.0.0.1:44071"
    trial._read_agent_token_proxy_usage = AsyncMock(
        side_effect=[
            _TokenProxyUsage(10, 5, 2, 1, 0.1),
            _TokenProxyUsage(110, 75, 12, 4, 0.8),
        ]
    )
    final_step = StepResult(step_name="final-delivery")

    async def run() -> None:
        await trial._begin_checkpoint_token_accounting()
        await trial._begin_checkpoint_token_accounting()
        await trial._settle_checkpoint_token_accounting(final_step)

    asyncio.run(run())

    assert trial._read_agent_token_proxy_usage.await_count == 2
    assert final_step.agent_result.n_input_tokens == 100
    assert final_step.agent_result.n_cache_tokens == 70
    assert final_step.agent_result.n_output_tokens == 10
    assert final_step.agent_result.cost_usd == pytest.approx(0.7)


def test_checkpoint_without_proxy_preserves_agent_report(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    context = AgentContext(
        n_input_tokens=100,
        n_cache_tokens=80,
        n_output_tokens=10,
        cost_usd=0.5,
    )
    step_result = StepResult(step_name="checkpoint-01", agent_result=context)

    asyncio.run(trial._settle_checkpoint_token_accounting(step_result))

    assert step_result.agent_result == context


def test_checkpoint_proxy_clears_unverified_agent_report(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    trial._host_token_proxy_base_url = "http://127.0.0.1:44071"
    step_result = StepResult(
        step_name="checkpoint-01",
        agent_result=AgentContext(
            n_input_tokens=100,
            n_cache_tokens=80,
            n_output_tokens=10,
            cost_usd=0.5,
            metadata={"agent": "preserved"},
        ),
    )

    trial._clear_agent_reported_token_usage(step_result)

    assert step_result.agent_result.n_input_tokens is None
    assert step_result.agent_result.n_cache_tokens is None
    assert step_result.agent_result.n_output_tokens is None
    assert step_result.agent_result.cost_usd is None
    assert step_result.agent_result.metadata == {"agent": "preserved"}


def test_run_uses_budget_across_natural_returns_with_resume(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=3)
    trial.agent_environment = "environment"
    trial.agent.prepare_checkpoint_trial = AsyncMock()

    agent_phase_calls: list[dict[str, object]] = []

    async def fake_run_agent_phase(*, target, instruction, timeout_sec, user, resume):
        agent_phase_calls.append({"instruction": instruction, "resume": resume})

    trial._run_agent_phase = AsyncMock(side_effect=fake_run_agent_phase)

    verifier_calls: list[str] = []

    async def fake_run_shared_verifier(*, timeout_sec, user, step_name):
        verifier_calls.append(step_name)
        return VerifierResult(rewards=None)

    trial._run_shared_verifier = AsyncMock(side_effect=fake_run_shared_verifier)

    asyncio.run(trial._run())

    assert [call["resume"] for call in agent_phase_calls] == [False, True, True]
    assert str(agent_phase_calls[0]["instruction"]).startswith("the real task instruction")
    assert "Official verification elapsed time is deducted" in str(
        agent_phase_calls[0]["instruction"]
    )
    assert all(
        "No verifier report is available" in str(call["instruction"])
        for call in agent_phase_calls[1:]
    )
    assert verifier_calls == ["checkpoint-01", "checkpoint-02"]
    assert [sr.step_name for sr in trial.result.step_results] == [
        "checkpoint-01",
        "checkpoint-02",
        "checkpoint-03",
    ]
    assert all(sr.verifier_result is not None for sr in trial.result.step_results[:2])
    assert trial.result.step_results[2].verifier_result is None
    trial._run_final_checkpoint.assert_awaited_once()
    trial.agent.prepare_checkpoint_trial.assert_awaited_once_with("environment")
    trial._stop_agent_environment.assert_awaited_once()


def test_run_reuses_measurement_for_unchanged_checkpoint_fingerprint(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=3)
    trial.agent_environment = "environment"
    trial.agent.checkpoint_fingerprint = AsyncMock(return_value="same-tree")
    trial.agent.record_measurement = AsyncMock()
    measurement = Measurement(
        verdict="ACCEPTED",
        metric="wall-clock",
        unit="seconds",
        value=1.5,
    )
    trial._run_verifier_iteration = AsyncMock(return_value=measurement)
    trial._reuse_checkpoint_measurement = AsyncMock(return_value=measurement)

    asyncio.run(trial._run())

    trial._run_verifier_iteration.assert_awaited_once()
    assert trial._reuse_checkpoint_measurement.await_count == 1
    assert [
        call.kwargs["source_name"] for call in trial._reuse_checkpoint_measurement.await_args_list
    ] == ["checkpoint-01"]
    trial.agent.record_measurement.assert_awaited_once_with(measurement, "environment")


def test_checkpoint_trial_shares_one_work_budget(tmp_path: Path, monkeypatch) -> None:
    trial = _trial(tmp_path, n_checkpoints=3)
    trial._total_agent_budget_sec = 30
    observed_timeouts: list[float | None] = []

    async def fake_agent_iteration(**kwargs):
        observed_timeouts.append(kwargs["timeout_sec"])
        step_result = StepResult(step_name=kwargs["name"])
        trial.result.step_results.append(step_result)
        return step_result, True, 7.0

    trial._run_agent_iteration = AsyncMock(side_effect=fake_agent_iteration)
    trial._run_verifier_iteration = AsyncMock(return_value=None)
    monkeypatch.setattr("perfrace.run.trial.monotonic", lambda: 0.0)

    asyncio.run(trial._run())

    assert observed_timeouts == [30, 23, 16, 9, 2]
    assert trial._run_verifier_iteration.await_count == 4
    trial._run_final_checkpoint.assert_awaited_once()


def test_checkpoint_trial_charges_verifier_time_to_shared_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=3)
    trial._total_agent_budget_sec = 30
    observed_timeouts: list[float | None] = []

    async def fake_agent_iteration(**kwargs):
        observed_timeouts.append(kwargs["timeout_sec"])
        step_result = StepResult(step_name=kwargs["name"])
        trial.result.step_results.append(step_result)
        return step_result, True, 7.0

    trial._run_agent_iteration = AsyncMock(side_effect=fake_agent_iteration)
    trial._run_verifier_iteration = AsyncMock(return_value=None)
    verifier_clock = iter((0.0, 11.0, 20.0, 31.0))
    monkeypatch.setattr("perfrace.run.trial.monotonic", lambda: next(verifier_clock))

    asyncio.run(trial._run())

    assert observed_timeouts == [30, 12]
    assert trial._run_verifier_iteration.await_count == 2
    trial._run_final_checkpoint.assert_awaited_once()


def test_checkpoint_trial_verifies_workspace_when_total_budget_expires(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=5)
    trial._total_agent_budget_sec = 50

    async def exhaust_budget(**kwargs):
        step_result = StepResult(step_name=kwargs["name"])
        trial.result.step_results.append(step_result)
        return step_result, False, 50.0

    trial._run_agent_iteration = AsyncMock(side_effect=exhaust_budget)
    trial._run_verifier_iteration = AsyncMock(return_value=None)

    asyncio.run(trial._run())

    trial._run_agent_iteration.assert_awaited_once()
    trial._run_final_checkpoint.assert_awaited_once()
    assert trial._run_final_checkpoint.await_args.kwargs["delivery_timeout_sec"] == 0
    trial._run_verifier_iteration.assert_not_awaited()
    assert trial._run_agent_iteration.await_args.kwargs["timeout_sec"] == 50


def test_checkpoint_turn_can_cross_delivery_notice_without_interruption(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    trial._total_agent_budget_sec = 30
    trial._FINAL_DELIVERY_NOTICE_SEC = 10

    async def cross_notice(**kwargs):
        step_result = StepResult(step_name=kwargs["name"])
        trial.result.step_results.append(step_result)
        return step_result, True, 25.0

    trial._run_agent_iteration = AsyncMock(side_effect=cross_notice)
    trial._run_verifier_iteration = AsyncMock(return_value=None)

    asyncio.run(trial._run())

    assert trial._run_agent_iteration.await_args.kwargs["timeout_sec"] == 30
    trial._run_verifier_iteration.assert_not_awaited()
    assert trial._run_final_checkpoint.await_args.kwargs["delivery_timeout_sec"] == 5


def test_final_delivery_runs_with_agent_phase_context(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    trial._FINAL_DELIVERY_NOTICE_SEC = 1
    trial.agent = SimpleNamespace(extra_env={}, finalize=AsyncMock())
    trial.agent_environment = SimpleNamespace(
        with_default_user=MagicMock(return_value=nullcontext()),
        scoped_exec_env=MagicMock(return_value=nullcontext()),
    )
    trial._network_plan = MagicMock(
        return_value=SimpleNamespace(agent_env_baseline="baseline", agent_phase="agent")
    )

    @asynccontextmanager
    async def phase_network_policy(*args, **kwargs):
        yield

    trial._phase_network_policy = phase_network_policy
    trial._log_context = MagicMock(return_value=nullcontext())
    step_result = StepResult(step_name="checkpoint-01")
    step_result.exception_info = ExceptionInfo.from_exception(
        AgentTimeoutError("planned research cutoff")
    )

    asyncio.run(
        CheckpointTrial._run_final_delivery(
            trial,
            step_result=step_result,
            timeout_sec=1,
        )
    )

    trial.agent.finalize.assert_awaited_once_with(
        trial._FINAL_DELIVERY_INSTRUCTION,
        trial.agent_environment,
        step_result.agent_result,
    )
    assert step_result.exception_info is None
    assert step_result.agent_result is not None
    assert step_result.agent_execution is not None
    assert step_result.agent_execution.started_at is not None
    assert step_result.agent_execution.finished_at is not None
    trial._sync_agent_output.assert_awaited_once()
    trial._upload_agent_logs.assert_awaited_once()


def test_final_checkpoint_delivers_before_scoring_workspace(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=1)
    trial.result.step_results = []
    trial.agent_environment = "environment"
    trial.agent.record_measurement = AsyncMock()
    measurement = Measurement(
        verdict="ACCEPTED",
        metric="wall-clock",
        unit="seconds",
        value=1.5,
    )
    events: list[str] = []

    async def final_delivery(*, step_result, timeout_sec):
        events.append("delivery")

    async def checkpoint_verifier(**kwargs):
        events.append("verifier")
        return 1.0, measurement, False

    trial._run_final_delivery = AsyncMock(side_effect=final_delivery)
    trial._workspace_fingerprint = AsyncMock(return_value="delivered-tree")
    trial._run_checkpoint_verifier = AsyncMock(side_effect=checkpoint_verifier)

    asyncio.run(
        CheckpointTrial._run_final_checkpoint(
            trial,
            last_verified_fingerprint="previous-tree",
            last_verified_name="checkpoint-02",
            delivery_timeout_sec=120,
        )
    )

    assert events == ["delivery", "verifier"]
    assert trial._run_final_delivery.await_args.kwargs["timeout_sec"] == 120
    assert [step.step_name for step in trial.result.step_results] == ["final-delivery"]
    assert trial._run_checkpoint_verifier.await_args.kwargs["preserve_agent"] is False
    assert trial._run_checkpoint_verifier.await_args.kwargs["fingerprint"] == "delivered-tree"
    trial.agent.record_measurement.assert_awaited_once_with(measurement, "environment")


def test_run_passes_each_checkpoints_report_to_the_next_resume(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=2)
    trial.agent_environment = "environment"
    trial.agent.record_measurement = AsyncMock()
    trial._run_agent_phase = AsyncMock()
    trial._run_shared_verifier = AsyncMock(return_value=VerifierResult(rewards=None))

    def fake_archive(name, *, preserve_agent):
        verifier_dir = trial._checkpoint_verifier_dir(name)
        verifier_dir.mkdir(parents=True, exist_ok=True)
        value = 1.0 if name == "checkpoint-01" else 2.0
        (verifier_dir / "measurement.json").write_text(
            Measurement(
                verdict="ACCEPTED", metric="wall-clock", unit="seconds", value=value
            ).model_dump_json()
        )

    trial._archive_checkpoint_outputs = MagicMock(side_effect=fake_archive)

    asyncio.run(trial._run())

    calls = trial._run_agent_phase.await_args_list
    assert "the real task instruction" in calls[0].kwargs["instruction"]
    assert "Last checkpoint: ACCEPTED, 1.0 seconds" in calls[1].kwargs["instruction"]
    recorded = trial.agent.record_measurement.await_args_list
    assert [call.args[0].value for call in recorded] == [1.0]
    assert all(call.args[1] == "environment" for call in recorded)


def test_run_preserves_agent_dir_only_on_checkpoints_before_a_resumed_one(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=3)
    trial._run_agent_phase = AsyncMock()
    trial._run_shared_verifier = AsyncMock(return_value=VerifierResult(rewards=None))

    asyncio.run(trial._run())

    calls = trial._archive_checkpoint_outputs.call_args_list
    assert [c.kwargs["preserve_agent"] for c in calls] == [True, True]
    assert [c.args[0] for c in calls] == [
        "checkpoint-01",
        "checkpoint-02",
    ]


def test_run_creates_checkpoint_directories(tmp_path: Path) -> None:
    trial = _trial(tmp_path, n_checkpoints=2)
    trial._run_agent_phase = AsyncMock()
    trial._run_shared_verifier = AsyncMock(return_value=VerifierResult(rewards=None))

    asyncio.run(trial._run())

    assert (tmp_path / "checkpoints" / "checkpoint-01").is_dir()
    assert (tmp_path / "checkpoints" / "checkpoint-02").is_dir()


def test_run_verifies_even_after_a_recovered_agent_failure(tmp_path: Path) -> None:
    """A NonZeroAgentExitCodeError/AgentTimeoutError is caught and recorded,
    but the checkpoint is still verified (whatever partial state exists) --
    matching SingleStepTrial's own "always verify" behavior.
    """
    trial = _trial(tmp_path, n_checkpoints=2)

    async def failing_agent_phase(*, target, instruction, timeout_sec, user, resume):
        raise NonZeroAgentExitCodeError("agent exited 1")

    trial._run_agent_phase = AsyncMock(side_effect=failing_agent_phase)
    trial._run_shared_verifier = AsyncMock(return_value=VerifierResult(rewards=None))

    asyncio.run(trial._run())

    # Both checkpoints ran (agent failure alone does not abort the loop, and
    # the verifier still ran and returned a result each time).
    assert len(trial.result.step_results) == 2
    assert trial.result.step_results[0].exception_info is not None
    assert trial.result.step_results[0].verifier_result is not None


def test_run_continues_remaining_checkpoints_when_verifier_never_produces_a_result(
    tmp_path: Path,
) -> None:
    """If a checkpoint's agent AND verifier both fail (no verifier_result at
    all), the loop still runs every remaining checkpoint -- the resume
    mechanism (--continue) is trusted to recover from a checkpoint that
    ran out of time, not just from a normal WRONG_ANSWER/OOM verdict.
    """
    trial = _trial(tmp_path, n_checkpoints=3)

    async def failing_agent_phase(*, target, instruction, timeout_sec, user, resume):
        raise NonZeroAgentExitCodeError("agent exited 1")

    call_count = 0

    async def failing_verifier(*, timeout_sec, user, step_name):
        nonlocal call_count
        call_count += 1
        raise asyncio.TimeoutError("verifier timed out")

    trial._run_agent_phase = AsyncMock(side_effect=failing_agent_phase)
    trial._run_shared_verifier = AsyncMock(side_effect=failing_verifier)

    asyncio.run(trial._run())

    assert call_count == 2
    assert len(trial.result.step_results) == 3
    trial._stop_agent_environment.assert_awaited_once()


def test_run_continues_remaining_checkpoints_after_a_generic_agent_phase_exception(
    tmp_path: Path,
) -> None:
    """An installed agent's own internal call (e.g. CopilotCli's
    session-state sync) can raise something other than
    AgentTimeoutError/NonZeroAgentExitCodeError -- this must still fail
    only the one checkpoint, not the whole trial.
    """
    trial = _trial(tmp_path, n_checkpoints=3)

    async def failing_agent_phase(*, target, instruction, timeout_sec, user, resume):
        raise RuntimeError("Command timed out after 10 seconds")

    trial._run_agent_phase = AsyncMock(side_effect=failing_agent_phase)
    trial._run_shared_verifier = AsyncMock(return_value=VerifierResult(rewards=None))

    asyncio.run(trial._run())

    assert len(trial.result.step_results) == 3
    assert all(step.exception_info is not None for step in trial.result.step_results)


def test_run_continues_remaining_checkpoints_when_log_sync_hangs(
    tmp_path: Path,
) -> None:
    """A stuck docker exec inside _sync_agent_output()/_upload_agent_logs()
    has no timeout of its own and can hang indefinitely -- _run_log_sync()
    must bound it so this checkpoint fails (recorded on step_result)
    instead of blocking every remaining checkpoint forever.
    """
    trial = _trial(tmp_path, n_checkpoints=2)
    trial._LOG_SYNC_TIMEOUT_SEC = 0.05

    async def hangs_forever(*_args, **_kwargs) -> None:
        await asyncio.sleep(10)

    trial._sync_agent_output = hangs_forever
    trial._run_shared_verifier = AsyncMock(return_value=VerifierResult(rewards=None))

    asyncio.run(trial._run())

    assert len(trial.result.step_results) == 2
    assert all(step.exception_info is not None for step in trial.result.step_results)


def test_init_rejects_zero_or_missing_checkpoints() -> None:
    for bad_value in (None, 0):
        config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=bad_value))
        try:
            CheckpointTrial(config, _task=None, _task_download_result=None)
        except ValueError as exc:
            assert "task_budget_sec" in str(exc)
        else:
            raise AssertionError("expected ValueError")


def test_prepare_installs_and_finalizes_trial_cpu_lease(tmp_path: Path, monkeypatch) -> None:
    from perfrace.run.services.resources import (
        CpuCore,
        HostCpuAllocator,
        get_environment_cpu_lease,
    )

    class FakeDockerEnvironment:
        effective_cpus = 2

        def __init__(self) -> None:
            self.extra_docker_compose_paths: list[Path] = []

    allocator = HostCpuAllocator(
        (
            CpuCore(logical_cpus=(0,), core_id=0, socket_id=0, numa_node=0),
            CpuCore(logical_cpus=(4,), core_id=1, socket_id=0, numa_node=0),
        )
    )
    environment = FakeDockerEnvironment()
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial.agent_environment = environment
    trial._trial_cpu_lease = None
    prepare = AsyncMock()
    finalize = AsyncMock()
    compose_path = tmp_path / "trial-cpu-resources.json"
    monkeypatch.setattr("perfrace.run.trial.DockerEnvironment", FakeDockerEnvironment)
    monkeypatch.setattr("perfrace.run.trial.trial_cpu_leases_enabled", lambda: True)
    monkeypatch.setattr("perfrace.run.trial.get_host_cpu_allocator", lambda: allocator)
    monkeypatch.setattr(
        "perfrace.run.trial.write_cpu_compose_override",
        MagicMock(return_value=compose_path),
    )
    monkeypatch.setattr("harbor.trial.trial.Trial._prepare", prepare)
    monkeypatch.setattr("harbor.trial.trial.Trial._finalize", finalize)

    asyncio.run(trial._prepare())

    lease = get_environment_cpu_lease(environment)
    assert lease is trial._trial_cpu_lease
    assert environment.extra_docker_compose_paths == [compose_path]
    prepare.assert_awaited_once()

    asyncio.run(trial._finalize())

    finalize.assert_awaited_once()
    assert get_environment_cpu_lease(environment) is None
    assert trial._trial_cpu_lease is None
    reacquired = asyncio.run(allocator.acquire(2))
    asyncio.run(reacquired.release())


def test_finalize_releases_trial_cpu_lease_after_prepare_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from perfrace.run.services.resources import CpuCore, HostCpuAllocator

    class FakeDockerEnvironment:
        effective_cpus = 2

        def __init__(self) -> None:
            self.extra_docker_compose_paths: list[Path] = []

    allocator = HostCpuAllocator(
        (
            CpuCore(
                logical_cpus=(0, 1),
                core_id=0,
                socket_id=0,
                numa_node=0,
            ),
        )
    )
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial.agent_environment = FakeDockerEnvironment()
    trial._trial_cpu_lease = None
    monkeypatch.setattr("perfrace.run.trial.DockerEnvironment", FakeDockerEnvironment)
    monkeypatch.setattr("perfrace.run.trial.trial_cpu_leases_enabled", lambda: True)
    monkeypatch.setattr("perfrace.run.trial.get_host_cpu_allocator", lambda: allocator)
    monkeypatch.setattr(
        "perfrace.run.trial.write_cpu_compose_override",
        MagicMock(return_value=tmp_path / "trial-cpu-resources.json"),
    )
    monkeypatch.setattr(
        "harbor.trial.trial.Trial._prepare",
        AsyncMock(side_effect=RuntimeError("prepare failed")),
    )
    monkeypatch.setattr("harbor.trial.trial.Trial._finalize", AsyncMock())

    with pytest.raises(RuntimeError, match="prepare failed"):
        asyncio.run(trial._prepare())
    asyncio.run(trial._finalize())

    reacquired = asyncio.run(allocator.acquire(2))
    asyncio.run(reacquired.release())


def test_init_rejects_external_repetitions_with_trial_cpu_leases(monkeypatch) -> None:
    def init_trial(self, config, **kwargs) -> None:
        self.task = SimpleNamespace(task_dir=Path("/task"))
        self._agent_timeout_sec = 3600
        self.agent = SimpleNamespace(SUPPORTS_RESUME=True, finalize=AsyncMock())

    monkeypatch.setattr("harbor.trial.trial.Trial.__init__", init_trial)
    monkeypatch.setattr("perfrace.run.trial.trial_cpu_leases_enabled", lambda: True)
    monkeypatch.setattr(
        "perfrace.run.trial.PerfRaceConfig.from_task_dir",
        lambda task_dir: SimpleNamespace(measurement=SimpleNamespace(repetition_scope="external")),
    )
    trial = object.__new__(CheckpointTrial)
    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=1800))

    with pytest.raises(ValueError, match="internal-repetition"):
        CheckpointTrial.__init__(trial, config, _task=None, _task_download_result=None)


def test_init_rejects_missing_agent_timeout(monkeypatch) -> None:
    def init_trial(self, config, **kwargs) -> None:
        self._agent_timeout_sec = None
        self.agent = SimpleNamespace(SUPPORTS_RESUME=True)

    monkeypatch.setattr("harbor.trial.trial.Trial.__init__", init_trial)
    trial = object.__new__(CheckpointTrial)
    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=1800))

    try:
        CheckpointTrial.__init__(trial, config, _task=None, _task_download_result=None)
    except ValueError as exc:
        assert "finite positive agent timeout" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_init_rejects_budget_not_longer_than_delivery_notice(monkeypatch) -> None:
    def init_trial(self, config, **kwargs) -> None:
        self._agent_timeout_sec = 100
        self.agent = SimpleNamespace(SUPPORTS_RESUME=True, finalize=AsyncMock())

    monkeypatch.setattr("harbor.trial.trial.Trial.__init__", init_trial)
    trial = object.__new__(CheckpointTrial)
    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=300))

    try:
        CheckpointTrial.__init__(trial, config, _task=None, _task_download_result=None)
    except ValueError as exc:
        assert "task_budget_sec" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_init_converts_checkpoints_to_total_agent_budget(monkeypatch) -> None:
    def init_trial(self, config, **kwargs) -> None:
        self._agent_timeout_sec = 600
        self.agent = SimpleNamespace(SUPPORTS_RESUME=True, finalize=AsyncMock())

    monkeypatch.setattr("harbor.trial.trial.Trial.__init__", init_trial)
    trial = object.__new__(CheckpointTrial)
    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=1800))

    CheckpointTrial.__init__(trial, config, _task=None, _task_download_result=None)

    assert trial._total_agent_budget_sec == 1800


def test_init_rejects_agent_that_cannot_resume(monkeypatch) -> None:
    def init_trial(self, config, **kwargs) -> None:
        self._agent_timeout_sec = 600

    monkeypatch.setattr("harbor.trial.trial.Trial.__init__", init_trial)
    trial = object.__new__(CheckpointTrial)
    trial.agent = SimpleNamespace(SUPPORTS_RESUME=False, name=lambda: "some-agent")
    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=1800))

    try:
        CheckpointTrial.__init__(trial, config, _task=None, _task_download_result=None)
    except ValueError as exc:
        assert "does not support resume" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_init_rejects_agent_without_final_delivery(monkeypatch) -> None:
    def init_trial(self, config, **kwargs) -> None:
        self._agent_timeout_sec = 600
        self.agent = SimpleNamespace(SUPPORTS_RESUME=True, name=lambda: "some-agent")

    monkeypatch.setattr("harbor.trial.trial.Trial.__init__", init_trial)
    trial = object.__new__(CheckpointTrial)
    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=600))

    try:
        CheckpointTrial.__init__(trial, config, _task=None, _task_download_result=None)
    except ValueError as exc:
        assert "does not support final delivery" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_archive_checkpoint_outputs_moves_verifier_and_agent_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial.paths.mkdir()
    (trial.paths.verifier_dir / "measurement.json").write_text("{}")
    (trial.paths.agent_dir / "copilot-cli.jsonl").write_text("log")

    from harbor.trial.artifact_handler import ArtifactHandler

    trial._artifact_handler = ArtifactHandler(artifacts=[], logger=MagicMock())
    main_mount = tmp_path / "mount"
    main_mount.mkdir()
    monkeypatch.setattr(
        CheckpointTrial, "_main_artifacts_mount_dir", property(lambda self: main_mount)
    )

    trial._archive_checkpoint_outputs("checkpoint-01", preserve_agent=False)

    assert (tmp_path / "checkpoints" / "checkpoint-01" / "verifier" / "measurement.json").is_file()
    assert (tmp_path / "checkpoints" / "checkpoint-01" / "agent" / "copilot-cli.jsonl").is_file()
    # Moved away, not left behind, since preserve_agent=False.
    assert not (trial.paths.agent_dir / "copilot-cli.jsonl").exists()


def test_archive_checkpoint_outputs_copies_agent_dir_when_preserving(
    tmp_path: Path, monkeypatch
) -> None:
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial.paths.mkdir()
    (trial.paths.agent_dir / "copilot-cli.jsonl").write_text("log")

    from harbor.trial.artifact_handler import ArtifactHandler

    trial._artifact_handler = ArtifactHandler(artifacts=[], logger=MagicMock())
    main_mount = tmp_path / "mount"
    main_mount.mkdir()
    monkeypatch.setattr(
        CheckpointTrial, "_main_artifacts_mount_dir", property(lambda self: main_mount)
    )

    trial._archive_checkpoint_outputs("checkpoint-01", preserve_agent=True)

    assert (tmp_path / "checkpoints" / "checkpoint-01" / "agent" / "copilot-cli.jsonl").is_file()
    # Kept in place (copied, not moved), since the next checkpoint resumes it.
    assert (trial.paths.agent_dir / "copilot-cli.jsonl").is_file()


def test_archive_checkpoint_outputs_survives_a_failed_agent_dir_copy(
    tmp_path: Path, monkeypatch
) -> None:
    """An archive-copy failure preserves the live session and allows continuation."""
    trial = object.__new__(CheckpointTrial)
    trial.logger = MagicMock()
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial.paths.mkdir()
    (trial.paths.verifier_dir / "measurement.json").write_text("{}")
    (trial.paths.agent_dir / "copilot-cli.jsonl").write_text("log")

    from harbor.trial.artifact_handler import ArtifactHandler

    trial._artifact_handler = ArtifactHandler(artifacts=[], logger=MagicMock())
    main_mount = tmp_path / "mount"
    main_mount.mkdir()
    monkeypatch.setattr(
        CheckpointTrial, "_main_artifacts_mount_dir", property(lambda self: main_mount)
    )
    monkeypatch.setattr(
        "shutil.copytree",
        MagicMock(side_effect=PermissionError("[Errno 13] Permission denied")),
    )

    # Must not raise.
    trial._archive_checkpoint_outputs("checkpoint-01", preserve_agent=True)

    trial.logger.warning.assert_called_once()
    # The live agent dir is untouched -- the next checkpoint can still resume.
    assert (trial.paths.agent_dir / "copilot-cli.jsonl").is_file()
    # Verifier archiving still succeeded independently of the agent-dir failure.
    assert (tmp_path / "checkpoints" / "checkpoint-01" / "verifier" / "measurement.json").is_file()


def test_trial_create_dispatches_to_checkpoint_trial_when_checkpoints_set(
    monkeypatch,
) -> None:
    """The vendor/harbor Trial.create() dispatch branch: checkpoints
    routes to perfrace.run.trial.CheckpointTrial, independent of
    task.has_steps -- confirming a plain, [[steps]]-free task instance can
    still be evaluated as a multi-checkpoint trial.
    """
    from harbor.trial.trial import Trial

    import perfrace.run.trial as pb_trial_module

    created: list[tuple[object, object, object]] = []

    class FakeCheckpointTrial:
        def __init__(self, config, *, _task, _task_download_result):
            created.append((config, _task, _task_download_result))

    monkeypatch.setattr(pb_trial_module, "CheckpointTrial", FakeCheckpointTrial)

    fake_task = SimpleNamespace(has_steps=False)
    fake_download_result = object()

    async def fake_load_task(config):
        return (fake_task, fake_download_result)

    monkeypatch.setattr(Trial, "_load_task", staticmethod(fake_load_task))

    config = SimpleNamespace(
        agent=SimpleNamespace(
            task_budget_sec=6000,
            skills=[],
            name="nop",
            import_path=None,
        )
    )

    result = asyncio.run(Trial.create(config))

    assert isinstance(result, FakeCheckpointTrial)
    assert created == [(config, fake_task, fake_download_result)]


def test_trial_create_ignores_has_steps_when_checkpoints_unset(monkeypatch) -> None:
    """Sanity check: without checkpoints, Trial.create() falls back
    to Harbor's normal has_steps dispatch (SingleStepTrial here), i.e. the
    new branch does not accidentally shadow existing behavior.
    """
    from harbor.trial.trial import Trial

    fake_task = SimpleNamespace(has_steps=False)
    fake_download_result = object()

    async def fake_load_task(config):
        return (fake_task, fake_download_result)

    monkeypatch.setattr(Trial, "_load_task", staticmethod(fake_load_task))

    created: list[object] = []

    class FakeSingleStepTrial:
        def __init__(self, config, *, _task, _task_download_result):
            created.append(config)

    monkeypatch.setattr("harbor.trial.single_step.SingleStepTrial", FakeSingleStepTrial)

    config = SimpleNamespace(agent=SimpleNamespace(task_budget_sec=None, skills=[]))

    result = asyncio.run(Trial.create(config))

    assert isinstance(result, FakeSingleStepTrial)
    assert created == [config]


def _write_checkpoint_measurement(
    trial: CheckpointTrial, name: str, measurement: Measurement
) -> None:
    verifier_dir = trial._checkpoint_verifier_dir(name)
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (verifier_dir / "measurement.json").write_text(measurement.model_dump_json())


def test_checkpoint_measurement_reads_the_archived_report(tmp_path: Path) -> None:
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    _write_checkpoint_measurement(
        trial,
        "checkpoint-01",
        Measurement(verdict="ACCEPTED", metric="wall-clock", unit="seconds", value=1.5),
    )

    measurement = trial._checkpoint_measurement("checkpoint-01")

    assert measurement is not None
    assert measurement.verdict == "ACCEPTED"
    assert measurement.value == 1.5


def test_checkpoint_measurement_returns_none_when_report_is_missing(tmp_path: Path) -> None:
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)

    assert trial._checkpoint_measurement("checkpoint-01") is None


def test_checkpoint_measurement_returns_none_when_report_is_unparseable(tmp_path: Path) -> None:
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    verifier_dir = trial._checkpoint_verifier_dir("checkpoint-01")
    verifier_dir.mkdir(parents=True)
    (verifier_dir / "measurement.json").write_text("not json")

    assert trial._checkpoint_measurement("checkpoint-01") is None


def test_reuse_checkpoint_measurement_copies_report_and_archives_outputs(
    tmp_path: Path,
) -> None:
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    trial.logger = MagicMock()
    trial._collect_artifacts_phased = AsyncMock()
    trial._archive_checkpoint_outputs = MagicMock()
    measurement = Measurement(
        verdict="ACCEPTED",
        metric="wall-clock",
        unit="seconds",
        value=1.5,
    )
    _write_checkpoint_measurement(trial, "checkpoint-01", measurement)

    reused = asyncio.run(
        trial._reuse_checkpoint_measurement(
            name="checkpoint-02",
            source_name="checkpoint-01",
            preserve_agent=True,
        )
    )

    assert reused == measurement
    assert trial._checkpoint_measurement("checkpoint-02") == measurement
    trial._collect_artifacts_phased.assert_awaited_once()
    trial._archive_checkpoint_outputs.assert_called_once_with(
        "checkpoint-02",
        preserve_agent=True,
    )


def test_checkpoint_measurement_never_reads_raw_test_stdout(tmp_path: Path) -> None:
    """Feedback reads measurement.json without exposing raw verifier output."""
    trial = object.__new__(CheckpointTrial)
    trial.paths = TrialPaths(trial_dir=tmp_path)
    verifier_dir = trial._checkpoint_verifier_dir("checkpoint-01")
    verifier_dir.mkdir(parents=True)
    (verifier_dir / "test-stdout.txt").write_text(
        "FAIL: day09-part-1 -- got '', expected '4744899849'\n"
    )
    _write_checkpoint_measurement(
        trial,
        "checkpoint-01",
        Measurement(verdict="WRONG_ANSWER", metric="wall-clock", unit="seconds", value=None),
    )

    measurement = trial._checkpoint_measurement("checkpoint-01")

    assert measurement is not None
    assert "day09" not in measurement.model_dump_json()
    assert "4744899849" not in measurement.model_dump_json()


def test_agent_can_skip_bookkeeping_verifier_and_continue_to_final_delivery(
    tmp_path: Path,
) -> None:
    trial = _trial(tmp_path, n_checkpoints=2)
    trial.agent_environment = "environment"
    trial.agent.checkpoint_trial_skip_to_final_checkpoint = MagicMock(return_value=True)
    trial.agent.set_checkpoint_budget = MagicMock()
    trial._settle_checkpoint_token_accounting = AsyncMock()
    trial._run_checkpoint_verifier = AsyncMock()

    asyncio.run(trial._run())

    trial.agent.checkpoint_trial_skip_to_final_checkpoint.assert_called_once_with()
    trial.agent.set_checkpoint_budget.assert_called_once_with(
        total_sec=7200,
        remaining_sec=7200,
    )
    trial._settle_checkpoint_token_accounting.assert_awaited_once()
    trial._collect_artifacts_phased.assert_awaited_once()
    trial._archive_checkpoint_outputs.assert_called_once_with(
        "checkpoint-01",
        preserve_agent=True,
    )
    trial._run_checkpoint_verifier.assert_not_awaited()
    trial._run_final_checkpoint.assert_awaited_once()
    trial._stop_agent_environment.assert_awaited_once()
