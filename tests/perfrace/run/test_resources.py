from __future__ import annotations

import asyncio
import multiprocessing
import os
from pathlib import Path
from typing import Any

import pytest

from perfrace.run.services.resources import CpuCore, HostCpuAllocator


def _hold_host_lock(lock_dir: str, ready: Any) -> None:
    async def run() -> None:
        allocator = HostCpuAllocator(
            (
                CpuCore(
                    logical_cpus=(0, 1),
                    core_id=0,
                    socket_id=0,
                    numa_node=0,
                ),
            ),
            lock_dir=Path(lock_dir),
        )
        lease = await allocator.acquire(2)
        ready.set()
        await asyncio.Event().wait()
        await lease.release()

    asyncio.run(run())


def _allocator() -> HostCpuAllocator:
    return HostCpuAllocator(
        (
            CpuCore(logical_cpus=(0,), core_id=0, socket_id=0, numa_node=0),
            CpuCore(logical_cpus=(2,), core_id=1, socket_id=0, numa_node=0),
            CpuCore(logical_cpus=(4,), core_id=2, socket_id=0, numa_node=0),
            CpuCore(logical_cpus=(1,), core_id=0, socket_id=1, numa_node=1),
            CpuCore(logical_cpus=(3,), core_id=1, socket_id=1, numa_node=1),
            CpuCore(logical_cpus=(5,), core_id=2, socket_id=1, numa_node=1),
        )
    )


def _smt_allocator() -> HostCpuAllocator:
    return HostCpuAllocator(
        (
            CpuCore(
                logical_cpus=(0, 1),
                core_id=0,
                socket_id=0,
                numa_node=0,
            ),
            CpuCore(
                logical_cpus=(2, 3),
                core_id=1,
                socket_id=0,
                numa_node=0,
            ),
        )
    )


def test_allocator_packs_siblings_without_sharing_physical_cores() -> None:
    async def run() -> None:
        allocator = _smt_allocator()
        first = await allocator.acquire(2)
        second = await allocator.acquire(2)

        assert first.cpus == (0, 1)
        assert second.cpus == (2, 3)
        assert first.physical_cores == ((0, 0),)
        assert second.physical_cores == ((0, 1),)

        await first.release()
        await second.release()

    asyncio.run(run())


def test_allocator_rejects_odd_cpu_count() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="positive even number"):
            await _smt_allocator().acquire(3)

    asyncio.run(run())


def test_allocator_returns_non_overlapping_same_numa_leases() -> None:
    async def run() -> None:
        allocator = _allocator()
        first = await allocator.acquire(2)
        second = await allocator.acquire(2)
        assert first.numa_node != second.numa_node
        assert set(first.cpus).isdisjoint(second.cpus)
        assert first.cpus == (0, 2)
        assert second.cpus == (1, 3)
        assert first.to_details()["physical_cores"] == [
            {"socket": 0, "core": 0},
            {"socket": 0, "core": 1},
        ]
        await first.release()
        await second.release()

    asyncio.run(run())


def test_allocator_waits_in_fifo_order() -> None:
    async def run() -> None:
        allocator = _allocator()
        held = [await allocator.acquire(2), await allocator.acquire(2)]
        order: list[str] = []

        async def wait_for_lease(label: str, count: int) -> None:
            lease = await allocator.acquire(count)
            order.append(label)
            await lease.release()

        first = asyncio.create_task(wait_for_lease("first", 2))
        second = asyncio.create_task(wait_for_lease("second", 2))
        await asyncio.sleep(0)
        await held[0].release()
        await asyncio.gather(first, second)
        await held[1].release()
        assert order == ["first", "second"]

    asyncio.run(run())


def test_allocator_rejects_request_larger_than_one_numa_node() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="largest NUMA node has 3"):
            await _allocator().acquire(4)

    asyncio.run(run())


def test_host_locks_coordinate_independent_allocators(tmp_path) -> None:
    async def run() -> None:
        cores = (
            CpuCore(
                logical_cpus=(0, 1),
                core_id=0,
                socket_id=0,
                numa_node=0,
            ),
        )
        first_allocator = HostCpuAllocator(cores, lock_dir=tmp_path / "locks")
        second_allocator = HostCpuAllocator(cores, lock_dir=tmp_path / "locks")
        first = await first_allocator.acquire(2)
        waiting = asyncio.create_task(second_allocator.acquire(2))

        await asyncio.sleep(0.15)
        assert waiting.done() is False
        assert first.to_details()["allocator_scope"] == "host"

        await first.release()
        second = await asyncio.wait_for(waiting, timeout=1)
        await second.release()

    asyncio.run(run())


def test_host_lock_files_ignore_restrictive_umask(tmp_path) -> None:
    previous_umask = os.umask(0o077)
    try:
        HostCpuAllocator(
            (CpuCore(logical_cpus=(0,), core_id=0, socket_id=0, numa_node=0),),
            lock_dir=tmp_path / "locks",
        )
    finally:
        os.umask(previous_umask)

    assert ((tmp_path / "locks" / "allocator.lock").stat().st_mode & 0o777) == 0o666
    assert ((tmp_path / "locks" / "socket-0-core-0.lock").stat().st_mode & 0o777) == 0o666


def test_host_locks_are_released_when_owner_process_exits(tmp_path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    process = context.Process(
        target=_hold_host_lock,
        args=(str(tmp_path / "locks"), ready),
    )
    process.start()
    try:
        assert ready.wait(timeout=5)

        async def run() -> None:
            allocator = HostCpuAllocator(
                (
                    CpuCore(
                        logical_cpus=(0, 1),
                        core_id=0,
                        socket_id=0,
                        numa_node=0,
                    ),
                ),
                lock_dir=tmp_path / "locks",
            )
            waiting = asyncio.create_task(allocator.acquire(2))
            await asyncio.sleep(0.15)
            assert waiting.done() is False

            process.terminate()
            process.join(timeout=5)
            assert process.is_alive() is False

            lease = await asyncio.wait_for(waiting, timeout=1)
            await lease.release()

        asyncio.run(run())
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)


def test_discovery_groups_logical_siblings_by_physical_core(tmp_path, monkeypatch) -> None:
    from perfrace.run.services import resources

    for cpu, socket, core, node in ((0, 0, 0, 0), (4, 0, 0, 0)):
        cpu_path = tmp_path / f"cpu{cpu}"
        topology = cpu_path / "topology"
        topology.mkdir(parents=True)
        (topology / "physical_package_id").write_text(str(socket))
        (topology / "core_id").write_text(str(core))
        (cpu_path / f"node{node}").mkdir()
    monkeypatch.setattr(resources, "SYS_CPU_ROOT", tmp_path)
    monkeypatch.setattr(resources.os, "sched_getaffinity", lambda _pid: {0, 4})

    allocator = resources.HostCpuAllocator.discover()

    assert allocator._cores == (
        CpuCore(
            logical_cpus=(0, 4),
            core_id=0,
            socket_id=0,
            numa_node=0,
        ),
    )


def test_configure_falls_back_when_host_allocation_is_unsupported(
    tmp_path, monkeypatch, caplog
) -> None:
    from perfrace.run.services import resources

    monkeypatch.setattr(resources, "host_cpu_allocation_supported", lambda: False)

    resources.configure_host_cpu_allocator(enabled=True, lock_dir=tmp_path / "locks")

    assert resources.get_host_cpu_allocator() is None
    assert "unavailable on this platform" in caplog.text


def test_configure_falls_back_when_topology_discovery_fails(tmp_path, monkeypatch, caplog) -> None:
    from perfrace.run.services import resources

    monkeypatch.setattr(resources, "SYS_CPU_ROOT", tmp_path)
    monkeypatch.setattr(resources.os, "sched_getaffinity", lambda _pid: {0})

    resources.configure_host_cpu_allocator(enabled=True, lock_dir=tmp_path / "locks")

    assert resources.get_host_cpu_allocator() is None
    assert "allocator setup failed" in caplog.text


def test_configure_falls_back_when_affinity_lookup_fails(tmp_path, monkeypatch, caplog) -> None:
    from perfrace.run.services import resources

    def fail_affinity(_pid: int) -> set[int]:
        raise OSError("denied")

    monkeypatch.setattr(resources, "SYS_CPU_ROOT", tmp_path)
    monkeypatch.setattr(resources.os, "sched_getaffinity", fail_affinity)

    resources.configure_host_cpu_allocator(enabled=True, lock_dir=tmp_path / "locks")

    assert resources.get_host_cpu_allocator() is None
    assert "allocator setup failed" in caplog.text


def test_configure_falls_back_when_host_lock_setup_fails(tmp_path, monkeypatch, caplog) -> None:
    from perfrace.run.services import resources

    cpu_path = tmp_path / "sys" / "cpu0"
    topology = cpu_path / "topology"
    topology.mkdir(parents=True)
    (topology / "physical_package_id").write_text("0")
    (topology / "core_id").write_text("0")
    (cpu_path / "node0").mkdir()

    def fail_lock_open(_path: Path) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(resources, "SYS_CPU_ROOT", tmp_path / "sys")
    monkeypatch.setattr(resources.os, "sched_getaffinity", lambda _pid: {0})
    monkeypatch.setattr(resources, "_open_lock_file", fail_lock_open)

    configured = resources.configure_host_cpu_allocator(
        enabled=True,
        lock_dir=tmp_path / "locks",
    )

    assert configured is False
    assert resources.get_host_cpu_allocator() is None
    assert "allocator setup failed" in caplog.text
