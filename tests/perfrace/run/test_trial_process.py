from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from harbor.models.job.config import RetryConfig
from harbor.models.job.lock import TaskLock, TrialLock
from harbor.models.trial.config import AgentConfig, TaskConfig, TrialConfig
from harbor.models.trial.paths import TrialPaths
from harbor.models.trial.result import AgentInfo, ExceptionInfo, TrialResult
from harbor.trial.hooks import TrialEvent, TrialHookEvent

from perfrace.run.isolation import (
    ControllerHookError,
    ControllerMemoryLimitError,
    ProcessIsolatedTrial,
    ProcessIsolatedTrialQueue,
    _run_trial,
)


def _config(tmp_path: Path, trial_name: str = "task-a__trial") -> TrialConfig:
    return TrialConfig(
        task=TaskConfig(path=tmp_path / "task-a"),
        trial_name=trial_name,
        trials_dir=tmp_path / "trials",
        agent=AgentConfig(name="nop"),
    )


def _event(config: TrialConfig, event: TrialEvent) -> TrialHookEvent:
    result = TrialResult(
        task_name="perfrace/task-a",
        trial_name=config.trial_name,
        trial_uri=(config.trials_dir / config.trial_name).resolve().as_uri(),
        task_id=config.task.get_task_id(),
        task_checksum="sha256:" + "0" * 64,
        config=config,
        agent_info=AgentInfo(name="nop", version="1.0.0"),
    )
    lock = TrialLock(
        task=TaskLock(
            name=result.task_name,
            type="local",
            digest="sha256:" + "0" * 64,
        ),
        agent=config.agent,
        environment=config.environment,
        verifier=config.verifier,
    )
    return TrialHookEvent(
        event=event,
        task_name=result.task_name,
        config=config,
        result=result,
        lock=lock,
    )


def test_worker_command_applies_memory_limit_and_redirects_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "perfrace.run.isolation.shutil.which",
        lambda command: f"/usr/bin/{command}",
    )
    trial = ProcessIsolatedTrial(
        _config(tmp_path),
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=True,
    )

    command = trial._worker_command()

    assert "--scope" in command
    assert "MemoryMax=8192M" in command
    assert "MemorySwapMax=0" in command
    assert not any(value.startswith("StandardOutput=") for value in command)
    assert not any(value.startswith("StandardError=") for value in command)
    assert "perfrace.run.isolation" in command
    assert "worker" in command
    assert str(tmp_path / "locks") in command
    assert "--host-resources-enabled" in command
    assert "--trial-cpu-leases" in command


def test_systemctl_operations_target_scope_unit(tmp_path: Path, monkeypatch) -> None:
    commands: list[tuple[str, ...]] = []

    class FakeProcess:
        returncode = 0

        async def wait(self) -> int:
            return self.returncode

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"inactive\n", b""

    async def create_subprocess_exec(*command: str, **_kwargs) -> FakeProcess:
        commands.append(command)
        return FakeProcess()

    async def sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        "perfrace.run.isolation.shutil.which",
        lambda command: f"/usr/bin/{command}",
    )
    monkeypatch.setattr(
        "perfrace.run.isolation.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )
    monkeypatch.setattr("perfrace.run.isolation.asyncio.sleep", sleep)
    trial = ProcessIsolatedTrial(
        _config(tmp_path),
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=False,
    )

    async def exercise_systemctl() -> None:
        await trial._stop_unit()
        await trial._unit_property("ActiveState")
        await trial._reset_unit()

    asyncio.run(exercise_systemctl())

    assert commands
    assert all(trial._scope_unit_name in command for command in commands)
    assert all(trial._unit_name not in command for command in commands)


def test_event_relay_invokes_parent_hook_and_acknowledges_worker(
    tmp_path: Path,
) -> None:
    trial = ProcessIsolatedTrial(
        _config(tmp_path),
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=False,
    )
    trial._event_dir.mkdir(parents=True)
    event = _event(trial.config, TrialEvent.START)
    event_path = trial._event_dir / "0000-start.json"
    event_path.write_text(event.model_dump_json(), encoding="utf-8")
    seen: list[TrialEvent] = []

    async def hook(hook_event: TrialHookEvent) -> None:
        seen.append(hook_event.event)

    trial.add_hook(TrialEvent.START, hook)
    asyncio.run(trial._relay_events(SimpleNamespace(returncode=0)))

    assert seen == [TrialEvent.START]
    assert event_path.with_suffix(".ack").is_file()


def test_memory_limit_failure_writes_result_and_emits_end(tmp_path: Path) -> None:
    trial = ProcessIsolatedTrial(
        _config(tmp_path),
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=False,
    )
    trial._last_event = _event(trial.config, TrialEvent.START)
    seen: list[TrialEvent] = []

    async def hook(hook_event: TrialHookEvent) -> None:
        seen.append(hook_event.event)

    trial.add_hook(TrialEvent.END, hook)
    result = asyncio.run(
        trial._synthesize_failure(
            exception_type=ControllerMemoryLimitError.__name__,
            message="memory limit exceeded",
            details="Finished with result: oom-kill",
        )
    )

    assert result.exception_info is not None
    assert result.exception_info.exception_type == "ControllerMemoryLimitError"
    assert result.exception_info.exception_message == "memory limit exceeded"
    assert seen == [TrialEvent.END]
    persisted = TrialResult.model_validate_json(trial.paths.result_path.read_text())
    assert persisted.exception_info == result.exception_info


def test_failure_before_start_uses_precomputed_lock(tmp_path: Path) -> None:
    config = _config(tmp_path)
    trial_lock = _event(config, TrialEvent.START).lock
    trial = ProcessIsolatedTrial(
        config,
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=False,
        trial_lock=trial_lock,
        task_name="perfrace/task-a",
        task_checksum="real-task-checksum",
    )
    seen: list[TrialEvent] = []

    async def hook(event: TrialHookEvent) -> None:
        seen.append(event.event)

    trial.add_hook(TrialEvent.START, hook)
    trial.add_hook(TrialEvent.END, hook)
    result = asyncio.run(
        trial._synthesize_failure(
            exception_type="ControllerWorkerError",
            message="worker failed before start",
            details="native crash",
        )
    )

    assert result.task_name == "perfrace/task-a"
    assert result.task_checksum == "real-task-checksum"
    assert result.exception_info is not None
    assert result.exception_info.exception_type == "ControllerWorkerError"
    assert seen == [TrialEvent.START, TrialEvent.END]
    assert trial.paths.lock_path.is_file()


def test_parent_hook_failure_becomes_trial_result(tmp_path: Path, monkeypatch) -> None:
    trial = ProcessIsolatedTrial(
        _config(tmp_path),
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=False,
    )
    trial._event_dir.mkdir(parents=True)
    event = _event(trial.config, TrialEvent.AGENT_START)
    (trial._event_dir / "0000-agent-start.json").write_text(
        event.model_dump_json(),
        encoding="utf-8",
    )
    stopped = asyncio.Event()
    seen_end = False

    class FakeProcess:
        returncode: int | None = None

        async def wait(self) -> int:
            await stopped.wait()
            assert self.returncode is not None
            return self.returncode

    process = FakeProcess()

    async def create_subprocess_exec(*_args, **_kwargs) -> FakeProcess:
        return process

    async def stop_unit() -> None:
        process.returncode = -15
        stopped.set()

    async def noop() -> None:
        return None

    async def fail_hook(_event: TrialHookEvent) -> None:
        raise OSError("progress write failed")

    async def end_hook(_event: TrialHookEvent) -> None:
        nonlocal seen_end
        seen_end = True

    monkeypatch.setattr(
        "perfrace.run.isolation.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )
    monkeypatch.setattr(trial, "_stop_unit", stop_unit)
    monkeypatch.setattr(trial, "_cleanup_trial_runtime", noop)
    monkeypatch.setattr(trial, "_wait_for_unit_settle", noop)
    monkeypatch.setattr(trial, "_reset_unit", noop)
    trial.add_hook(TrialEvent.AGENT_START, fail_hook)
    trial.add_hook(TrialEvent.END, end_hook)

    result = asyncio.run(trial.run())

    assert result.exception_info is not None
    assert result.exception_info.exception_type == ControllerHookError.__name__
    assert "progress write failed" in result.exception_info.exception_message
    assert seen_end is True


def test_memory_failure_retries_without_cancelling_sibling(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: dict[str, int] = {}

    class FakeProcessTrial:
        def __init__(
            self,
            config: TrialConfig,
            *,
            controller_memory_mb: int,
            host_resources_enabled: bool,
            host_resource_lock_dir: Path,
            trial_cpu_leases: bool,
            trial_lock,
            task_name: str,
            task_checksum: str,
        ) -> None:
            self.config = config
            self.paths = TrialPaths(config.trials_dir / config.trial_name)
            self._hooks = {event: [] for event in TrialEvent}
            assert controller_memory_mb == 8192
            assert host_resources_enabled is True
            assert host_resource_lock_dir == tmp_path / "locks"
            assert trial_cpu_leases is False
            assert trial_lock == locks[config.trial_name]
            assert task_name == "perfrace/task-a"
            assert task_checksum == "real-task-checksum"

        def add_hook(self, event: TrialEvent, hook) -> None:
            self._hooks[event].append(hook)

        async def run(self) -> TrialResult:
            calls[self.config.trial_name] = calls.get(self.config.trial_name, 0) + 1
            result = _event(self.config, TrialEvent.END).result
            if self.config.trial_name == "oom-trial" and calls[self.config.trial_name] == 1:
                result.exception_info = ExceptionInfo(
                    exception_type=ControllerMemoryLimitError.__name__,
                    exception_message="memory limit exceeded",
                    exception_traceback="oom-kill",
                    occurred_at=datetime.now(),
                )
            return result

    monkeypatch.setattr(
        "perfrace.run.isolation.ProcessIsolatedTrial",
        FakeProcessTrial,
    )
    oom = _config(tmp_path, "oom-trial")
    sibling = _config(tmp_path, "sibling-trial")
    locks = {config.trial_name: _event(config, TrialEvent.START).lock for config in (oom, sibling)}
    queue = ProcessIsolatedTrialQueue(
        n_concurrent=2,
        retry_config=RetryConfig(max_retries=1, min_wait_sec=0),
        controller_memory_mb=8192,
        host_resources_enabled=True,
        host_resource_lock_dir=tmp_path / "locks",
        trial_cpu_leases=False,
        trial_locks=locks,
        trial_task_metadata={
            config.trial_name: ("perfrace/task-a", "real-task-checksum")
            for config in (oom, sibling)
        },
    )

    async def run() -> list[TrialResult]:
        return list(await asyncio.gather(*queue.submit_batch([oom, sibling])))

    results = asyncio.run(run())

    assert [result.exception_info for result in results] == [None, None]
    assert calls == {"oom-trial": 2, "sibling-trial": 1}


def test_trial_worker_waits_for_parent_hook_acknowledgements(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    event_dir = tmp_path / "events"

    class FakeTrial:
        def __init__(self) -> None:
            self.hooks = {event: [] for event in TrialEvent}

        def add_hook(self, event: TrialEvent, hook) -> None:
            self.hooks[event].append(hook)

        async def run(self) -> None:
            for event_type in (TrialEvent.START, TrialEvent.END):
                event = _event(config, event_type)
                for hook in self.hooks[event_type]:
                    await hook(event)

    fake = FakeTrial()
    allocator_calls: list[tuple[bool, Path]] = []
    lease_calls: list[bool] = []
    shadow_calls: list[int] = []

    async def create(_config: TrialConfig):
        return fake

    monkeypatch.setattr("harbor.trial.trial.Trial.create", create)
    monkeypatch.setattr(
        "perfrace.run.services.resources.configure_host_cpu_allocator",
        lambda enabled, *, lock_dir: allocator_calls.append((enabled, lock_dir)) or True,
    )
    monkeypatch.setattr(
        "perfrace.run.services.resources.configure_trial_cpu_leases",
        lease_calls.append,
    )
    monkeypatch.setattr(
        "perfrace.run.verifier.shadow.configure_shared_shadow_pool",
        shadow_calls.append,
    )
    observed: list[str] = []

    async def acknowledge() -> None:
        for sequence in range(2):
            while True:
                matches = sorted(event_dir.glob(f"{sequence:04d}-*.json"))
                if matches:
                    observed.append(matches[0].name)
                    matches[0].with_suffix(".ack").write_text("", encoding="utf-8")
                    break
                await asyncio.sleep(0.01)

    async def run() -> None:
        await asyncio.gather(
            _run_trial(
                config_path,
                event_dir,
                parent_pid=os.getpid(),
                host_resources_enabled=True,
                host_resource_lock_dir=tmp_path / "locks",
                trial_cpu_leases=True,
            ),
            acknowledge(),
        )

    asyncio.run(run())

    assert observed == [
        "0000-start.json",
        "0001-end.json",
    ]
    assert list(event_dir.iterdir()) == []
    assert allocator_calls == [(True, tmp_path / "locks")]
    assert lease_calls == [True]
    assert shadow_calls == [1]
