from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.trial.paths import TrialPaths

from perfrace.run.services.resources import (
    CpuCore,
    HostCpuAllocator,
    bind_environment_cpu_lease,
    unbind_environment_cpu_lease,
)
from perfrace.run.verifier import shadow
from perfrace.run.verifier.shadow import ShadowRunResult, cpu_compose_path


@pytest.fixture(autouse=True)
def snapshot_cleanup(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    cleanup = AsyncMock()
    monkeypatch.setattr(shadow, "remove_snapshot", cleanup)
    return cleanup


def test_cpu_compose_override_pins_shadow_to_lease(tmp_path) -> None:
    async def run() -> None:
        allocator = HostCpuAllocator(
            (
                CpuCore(logical_cpus=(0,), core_id=0, socket_id=0, numa_node=0),
                CpuCore(logical_cpus=(4,), core_id=1, socket_id=0, numa_node=0),
            )
        )
        lease = await allocator.acquire(2)
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        path = cpu_compose_path(paths, "shadow-1", lease)

        assert json.loads(path.read_text()) == {"services": {"main": {"cpuset": "0,4"}}}
        await lease.release()

    asyncio.run(run())


def test_measurement_shadows_hold_non_overlapping_leases(
    tmp_path, monkeypatch, snapshot_cleanup
) -> None:
    async def run() -> None:
        allocator = HostCpuAllocator(
            tuple(
                CpuCore(logical_cpus=(cpu,), core_id=index, socket_id=0, numa_node=0)
                for index, cpu in enumerate((0, 4, 8, 12))
            )
        )
        monkeypatch.setattr(shadow, "get_host_cpu_allocator", lambda: allocator)
        spawn = AsyncMock(side_effect=[SimpleNamespace(name="a"), SimpleNamespace(name="b")])
        monkeypatch.setattr(shadow, "spawn_shadow", spawn)
        both_running = asyncio.Event()
        started = 0

        async def run_in_shadow(*_args, **_kwargs) -> ShadowRunResult:
            nonlocal started
            started += 1
            if started == 2:
                both_running.set()
            await both_running.wait()
            return ShadowRunResult(
                exit_code=0,
                oom_killed=False,
                stdout='{"correct":true,"value":1}\n',
            )

        monkeypatch.setattr(
            shadow,
            "run_in_shadow",
            AsyncMock(side_effect=run_in_shadow),
        )
        monkeypatch.setattr(shadow, "teardown_shadow", AsyncMock(return_value=True))
        shadow.configure_shared_shadow_pool(2)
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        results = await shadow.run_measurement(
            SimpleNamespace(effective_cpus=2),
            "snapshot",
            "bash /tests/test.sh",
            n=2,
            timeout_sec=30,
            trial_paths=paths,
            environment_name="demo",
            base_session_id="trial",
        )

        cpu_sets = [call.kwargs["cpu_lease"].cpus for call in spawn.await_args_list]
        assert cpu_sets == [(0, 4), (8, 12)]
        snapshot_cleanup.assert_awaited_once_with("snapshot")
        assert [result.host_resources["logical_cpus"] for result in results] == [
            [0, 4],
            [8, 12],
        ]
        reacquired = await allocator.acquire(4)
        await reacquired.release()

    asyncio.run(run())


def test_measurement_shadow_inherits_trial_lease_without_releasing_it(
    tmp_path,
    monkeypatch,
) -> None:
    async def run() -> None:
        allocator = HostCpuAllocator(
            (
                CpuCore(logical_cpus=(0,), core_id=0, socket_id=0, numa_node=0),
                CpuCore(logical_cpus=(4,), core_id=1, socket_id=0, numa_node=0),
            )
        )
        source = SimpleNamespace(effective_cpus=2)
        lease = await allocator.acquire(2)
        bind_environment_cpu_lease(source, lease)
        spawn = AsyncMock(return_value=SimpleNamespace(name="shadow"))
        monkeypatch.setattr(shadow, "spawn_shadow", spawn)
        monkeypatch.setattr(
            shadow,
            "run_in_shadow",
            AsyncMock(
                return_value=ShadowRunResult(
                    exit_code=0,
                    oom_killed=False,
                    stdout='{"correct":true,"value":1}\n',
                )
            ),
        )
        monkeypatch.setattr(shadow, "teardown_shadow", AsyncMock(return_value=True))
        shadow.configure_shared_shadow_pool(1)
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        [result] = await shadow.run_measurement(
            source,
            "snapshot",
            "bash /tests/test.sh",
            n=1,
            timeout_sec=30,
            trial_paths=paths,
            environment_name="demo",
            base_session_id="trial",
        )

        assert spawn.await_args.kwargs["cpu_lease"] is None
        assert result.host_resources == lease.to_details()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(allocator.acquire(2), timeout=0.01)

        assert unbind_environment_cpu_lease(source) is lease
        await lease.release()
        reacquired = await allocator.acquire(2)
        await reacquired.release()

    asyncio.run(run())


def test_cancellation_during_teardown_releases_cpu_lease(
    tmp_path, monkeypatch, snapshot_cleanup
) -> None:
    async def run() -> None:
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
        monkeypatch.setattr(shadow, "get_host_cpu_allocator", lambda: allocator)
        monkeypatch.setattr(
            shadow,
            "spawn_shadow",
            AsyncMock(return_value=SimpleNamespace(name="shadow")),
        )
        monkeypatch.setattr(
            shadow,
            "run_in_shadow",
            AsyncMock(
                return_value=ShadowRunResult(
                    exit_code=0,
                    oom_killed=False,
                    stdout='{"correct":true,"value":1}\n',
                )
            ),
        )
        teardown_started = asyncio.Event()
        finish_teardown = asyncio.Event()

        async def teardown(_shadow) -> bool:
            teardown_started.set()
            await finish_teardown.wait()
            return True

        monkeypatch.setattr(shadow, "teardown_shadow", teardown)
        shadow.configure_shared_shadow_pool(1)
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        measurement = asyncio.create_task(
            shadow.run_measurement(
                SimpleNamespace(effective_cpus=2),
                "snapshot",
                "bash /tests/test.sh",
                n=1,
                timeout_sec=30,
                trial_paths=paths,
                environment_name="demo",
                base_session_id="trial",
            )
        )
        await teardown_started.wait()
        measurement.cancel()
        await asyncio.sleep(0)
        finish_teardown.set()
        with pytest.raises(asyncio.CancelledError):
            await measurement

        snapshot_cleanup.assert_awaited_once_with("snapshot")
        reacquired = await asyncio.wait_for(allocator.acquire(2), timeout=1)
        await reacquired.release()

    asyncio.run(run())


def test_cancellation_during_shadow_start_runs_teardown(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        start_entered = asyncio.Event()
        keep_starting = asyncio.Event()

        async def start(*, force_build: bool) -> None:
            assert force_build is False
            start_entered.set()
            await keep_starting.wait()

        candidate = Mock(spec=DockerEnvironment)
        candidate.start = AsyncMock(side_effect=start)
        monkeypatch.setattr(
            shadow.EnvironmentFactory,
            "create_environment",
            Mock(return_value=candidate),
        )
        teardown = AsyncMock(return_value=True)
        monkeypatch.setattr(shadow, "teardown_shadow", teardown)
        task_env_config = Mock()
        task_env_config.model_copy.return_value = task_env_config
        source = SimpleNamespace(
            task_env_config=task_env_config,
            extra_docker_compose_paths=[],
            environment_dir=tmp_path,
            network_policy=None,
        )
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        spawning = asyncio.create_task(
            shadow.spawn_shadow(
                source,
                "snapshot",
                environment_name="demo",
                session_id="trial",
                trial_paths=paths,
            )
        )
        await start_entered.wait()
        spawning.cancel()
        with pytest.raises(asyncio.CancelledError):
            await spawning

        teardown.assert_awaited_once_with(candidate)

    asyncio.run(run())


def test_failed_teardown_quarantines_cpu_lease(tmp_path, monkeypatch) -> None:
    async def run() -> None:
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
        monkeypatch.setattr(shadow, "get_host_cpu_allocator", lambda: allocator)
        monkeypatch.setattr(
            shadow,
            "spawn_shadow",
            AsyncMock(return_value=SimpleNamespace(name="shadow")),
        )
        monkeypatch.setattr(
            shadow,
            "run_in_shadow",
            AsyncMock(
                return_value=ShadowRunResult(
                    exit_code=0,
                    oom_killed=False,
                    stdout='{"correct":true,"value":1}\n',
                )
            ),
        )
        monkeypatch.setattr(shadow, "teardown_shadow", AsyncMock(return_value=False))
        shadow.configure_shared_shadow_pool(1)
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        await shadow.run_measurement(
            SimpleNamespace(effective_cpus=2),
            "snapshot",
            "bash /tests/test.sh",
            n=1,
            timeout_sec=30,
            trial_paths=paths,
            environment_name="demo",
            base_session_id="trial",
        )

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(allocator.acquire(2), timeout=0.01)

    asyncio.run(run())


def test_pause_cancellation_completes_unpause(monkeypatch) -> None:
    async def run() -> None:
        environment = AsyncMock()
        environment.resolve_service_container_id.return_value = "container-1"
        transitions: list[bool] = []
        unpaused = asyncio.Event()

        async def set_paused(_container_id: str, *, paused: bool) -> None:
            transitions.append(paused)
            if paused:
                raise asyncio.CancelledError
            await asyncio.sleep(0)
            unpaused.set()

        monkeypatch.setattr(shadow, "_set_container_paused", set_paused)

        with pytest.raises(asyncio.CancelledError):
            async with shadow.paused_main_container(environment):
                raise AssertionError("measurement must not start")

        assert unpaused.is_set()
        assert transitions == [True, False]

    asyncio.run(run())


def test_cancelled_docker_pause_terminates_and_reaps_process(monkeypatch) -> None:
    async def run() -> None:
        communicate_started = asyncio.Event()
        blocked = asyncio.Event()

        async def communicate():
            communicate_started.set()
            await blocked.wait()

        process = SimpleNamespace(
            communicate=communicate,
            returncode=None,
            terminate=Mock(),
            wait=AsyncMock(),
        )
        monkeypatch.setattr(
            shadow.asyncio,
            "create_subprocess_exec",
            AsyncMock(return_value=process),
        )

        pause = asyncio.create_task(shadow._set_container_paused("container-1", paused=True))
        await communicate_started.wait()
        pause.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pause

        process.terminate.assert_called_once_with()
        process.wait.assert_awaited_once_with()

    asyncio.run(run())


def test_task_without_cpu_count_runs_without_lease(monkeypatch, caplog) -> None:
    async def run() -> None:
        allocator = SimpleNamespace(acquire=AsyncMock())
        monkeypatch.setattr(shadow, "get_host_cpu_allocator", lambda: allocator)

        lease = await shadow.acquire_cpu_lease(SimpleNamespace(effective_cpus=None))

        assert lease is None
        allocator.acquire.assert_not_awaited()
        assert "no effective CPU count" in caplog.text

    asyncio.run(run())


def test_task_without_cpu_count_uses_serial_unpinned_pool(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        allocator = HostCpuAllocator(
            (CpuCore(logical_cpus=(0,), core_id=0, socket_id=0, numa_node=0),)
        )
        monkeypatch.setattr(shadow, "get_host_cpu_allocator", lambda: allocator)
        monkeypatch.setattr(
            shadow,
            "spawn_shadow",
            AsyncMock(side_effect=[SimpleNamespace(name="a"), SimpleNamespace(name="b")]),
        )
        active = 0
        max_active = 0

        async def run_in_shadow(*_args, **_kwargs) -> ShadowRunResult:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1
            return ShadowRunResult(
                exit_code=0,
                oom_killed=False,
                stdout='{"correct":true,"value":1}\n',
            )

        monkeypatch.setattr(shadow, "run_in_shadow", run_in_shadow)
        monkeypatch.setattr(shadow, "teardown_shadow", AsyncMock(return_value=True))
        shadow.configure_shared_shadow_pool(2)
        paths = TrialPaths(trial_dir=tmp_path / "trial")
        paths.mkdir()

        await shadow.run_measurement(
            SimpleNamespace(effective_cpus=None),
            "snapshot",
            "bash /tests/test.sh",
            n=2,
            timeout_sec=30,
            trial_paths=paths,
            environment_name="demo",
            base_session_id="trial",
        )

        assert max_active == 1

    asyncio.run(run())
