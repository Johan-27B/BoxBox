"""Per-run SMT-packed CPU allocation for local measurement shadows."""

from __future__ import annotations

import asyncio
import contextvars
import fcntl
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

SYS_CPU_ROOT = Path("/sys/devices/system/cpu")
HOST_LOCK_POLL_SECONDS = 0.1
logger = logging.getLogger(__name__)


def host_cpu_allocation_supported() -> bool:
    """Return whether this process exposes Linux affinity and sysfs topology."""
    return hasattr(os, "sched_getaffinity") and SYS_CPU_ROOT.is_dir()


def _cpu_numa_node(cpu_path: Path) -> int:
    """Return the NUMA node linked from one Linux sysfs CPU directory."""
    nodes = sorted(cpu_path.glob("node[0-9]*"))
    if not nodes:
        return 0
    return int(nodes[0].name.removeprefix("node"))


def _prepare_lock_dir(path: Path) -> Path:
    """Create a shared sticky lock directory without changing an existing one."""
    resolved = path.expanduser().resolve()
    try:
        resolved.mkdir(parents=True, mode=0o1777)
    except FileExistsError:
        pass
    else:
        resolved.chmod(0o1777)
    if not resolved.is_dir():
        raise RuntimeError(f"host resource lock path is not a directory: {resolved}")
    return resolved


def _open_lock_file(path: Path) -> BinaryIO:
    """Open or create a lock file that other server users can read-lock."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError:
        fd = os.open(path, flags)
    else:
        try:
            os.fchmod(fd, 0o666)
        except OSError:
            os.close(fd)
            try:
                path.unlink()
            except OSError:
                pass
            raise
    return os.fdopen(fd, "rb", buffering=0)


@dataclass(frozen=True)
class CpuCore:
    """One allocatable physical core and its logical CPU siblings."""

    logical_cpus: tuple[int, ...]
    core_id: int
    socket_id: int
    numa_node: int

    @property
    def key(self) -> tuple[int, int]:
        """Return the host-wide physical-core identity."""
        return self.socket_id, self.core_id


@dataclass
class CpuLease:
    """A same-NUMA CPU set held by one active measurement shadow."""

    cpus: tuple[int, ...]
    physical_cores: tuple[tuple[int, int], ...]
    numa_node: int
    wait_seconds: float
    _allocator: "HostCpuAllocator" = field(repr=False)
    _lock_files: tuple[BinaryIO, ...] = field(default=(), repr=False)
    _released: bool = field(default=False, init=False, repr=False)
    _quarantined: bool = field(default=False, init=False, repr=False)

    async def __aenter__(self) -> "CpuLease":
        """Return this acquired lease."""
        return self

    def to_details(self) -> dict[str, object]:
        """Render the allocation metadata stored with one repetition."""
        return {
            "logical_cpus": list(self.cpus),
            "physical_cores": [
                {"socket": socket, "core": core} for socket, core in self.physical_cores
            ],
            "numa_node": self.numa_node,
            "wait_seconds": self.wait_seconds,
            "allocator_scope": "host" if self._lock_files else "process",
        }

    async def release(self) -> None:
        """Return the leased cores to the allocator once."""
        if self._released or self._quarantined:
            return
        await self._allocator.release(self.physical_cores, self._lock_files)
        self._released = True

    def quarantine(self) -> None:
        """Keep these cores unavailable because their shadow may still run."""
        if self._released or self._quarantined:
            return
        self._allocator.quarantine(self._lock_files)
        self._quarantined = True

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Release this lease."""
        await self.release()


class HostCpuAllocator:
    """Allocate FIFO, non-overlapping, same-NUMA logical CPU sets."""

    def __init__(
        self,
        cores: tuple[CpuCore, ...],
        *,
        lock_dir: Path | None = None,
    ) -> None:
        """Initialize a per-run pool of complete physical-core sibling groups."""
        if not cores:
            raise ValueError("host CPU allocator found no physical cores")
        sibling_counts = {len(core.logical_cpus) for core in cores}
        if 0 in sibling_counts or len(sibling_counts) != 1:
            raise ValueError("host CPU allocator requires uniform non-empty sibling groups")
        self._cores = cores
        self._logical_cpus_per_core = sibling_counts.pop()
        self._core_by_key = {core.key: core for core in cores}
        if len(self._core_by_key) != len(cores):
            raise ValueError("host CPU allocator found duplicate physical cores")
        self._lock_dir = _prepare_lock_dir(lock_dir) if lock_dir is not None else None
        self._available = set(self._core_by_key)
        self._condition = asyncio.Condition()
        self._waiters: deque[object] = deque()
        self._quarantined_lock_files: list[BinaryIO] = []
        self._max_node_cpus = max(
            sum(len(core.logical_cpus) for core in cores if core.numa_node == node)
            for node in {core.numa_node for core in cores}
        )
        if self._lock_dir is not None:
            self._validate_host_locks()

    def _select(self, core_count: int) -> tuple[CpuCore, ...] | None:
        """Choose a best-fit same-NUMA sibling-packed set."""
        by_node: dict[int, list[CpuCore]] = defaultdict(list)
        for core in self._cores:
            if core.key in self._available:
                by_node[core.numa_node].append(core)
        candidates = [
            (
                len(cores),
                node,
                sorted(cores, key=lambda core: core.logical_cpus[0]),
            )
            for node, cores in by_node.items()
            if len(cores) >= core_count
        ]
        if not candidates:
            return None
        _, _, cores = min(candidates, key=lambda item: (item[0], item[1]))
        return tuple(cores[:core_count])

    def _core_lock_path(self, core: CpuCore) -> Path:
        """Return the shared lock file for one physical core."""
        assert self._lock_dir is not None
        return self._lock_dir / f"socket-{core.socket_id}-core-{core.core_id}.lock"

    def _validate_host_locks(self) -> None:
        """Create and verify every shared lock file during allocator setup."""
        assert self._lock_dir is not None
        paths = [
            self._lock_dir / "allocator.lock",
            *(self._core_lock_path(core) for core in self._cores),
        ]
        for path in paths:
            lock_file = _open_lock_file(path)
            try:
                try:
                    fcntl.flock(lock_file, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            finally:
                lock_file.close()

    def _try_acquire_host(
        self,
        core_count: int,
    ) -> tuple[tuple[CpuCore, ...], tuple[BinaryIO, ...]] | None:
        """Try one atomic same-NUMA allocation against shared host locks."""
        assert self._lock_dir is not None
        allocator_lock = _open_lock_file(self._lock_dir / "allocator.lock")
        fcntl.flock(allocator_lock, fcntl.LOCK_EX)
        try:
            by_node: dict[int, list[CpuCore]] = defaultdict(list)
            for core in self._cores:
                if core.key in self._available:
                    by_node[core.numa_node].append(core)
            candidates = sorted(
                (
                    len(cores),
                    node,
                    sorted(cores, key=lambda core: core.logical_cpus[0]),
                )
                for node, cores in by_node.items()
                if len(cores) >= core_count
            )
            for _, _, cores in candidates:
                selected: list[CpuCore] = []
                lock_files: list[BinaryIO] = []
                try:
                    for core in cores:
                        lock_file = _open_lock_file(self._core_lock_path(core))
                        try:
                            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            lock_file.close()
                            continue
                        selected.append(core)
                        lock_files.append(lock_file)
                        if len(selected) == core_count:
                            return tuple(selected), tuple(lock_files)
                except BaseException:
                    for lock_file in lock_files:
                        lock_file.close()
                    raise
                for lock_file in lock_files:
                    lock_file.close()
            return None
        finally:
            allocator_lock.close()

    def _try_acquire(
        self,
        core_count: int,
    ) -> tuple[tuple[CpuCore, ...], tuple[BinaryIO, ...]] | None:
        """Try a process-local or shared-host allocation."""
        if self._lock_dir is None:
            selected = self._select(core_count)
            return (selected, ()) if selected is not None else None
        return self._try_acquire_host(core_count)

    @classmethod
    def discover(cls, *, lock_dir: Path | None = None) -> "HostCpuAllocator":
        """Discover the current Linux host's physical CPU topology."""
        if not host_cpu_allocation_supported():
            raise RuntimeError("Linux CPU affinity and sysfs topology are unavailable")
        try:
            allowed = os.sched_getaffinity(0)
            logical_cpus_by_core: dict[tuple[int, int], list[int]] = defaultdict(list)
            numa_by_core: dict[tuple[int, int], int] = {}
            cpu_paths = sorted(
                (
                    path
                    for path in SYS_CPU_ROOT.glob("cpu[0-9]*")
                    if path.name.removeprefix("cpu").isdigit()
                ),
                key=lambda path: int(path.name.removeprefix("cpu")),
            )
            for cpu_path in cpu_paths:
                logical_cpu = int(cpu_path.name.removeprefix("cpu"))
                online_path = cpu_path / "online"
                if online_path.exists() and online_path.read_text().strip() != "1":
                    continue
                topology = cpu_path / "topology"
                socket_id = int((topology / "physical_package_id").read_text())
                core_id = int((topology / "core_id").read_text())
                key = (socket_id, core_id)
                logical_cpus_by_core[key].append(logical_cpu)
                numa_by_core.setdefault(key, _cpu_numa_node(cpu_path))
            cores = tuple(
                CpuCore(
                    logical_cpus=tuple(sorted(logical_cpus)),
                    core_id=core_id,
                    socket_id=socket_id,
                    numa_node=numa_by_core[(socket_id, core_id)],
                )
                for (socket_id, core_id), logical_cpus in logical_cpus_by_core.items()
                if set(logical_cpus).issubset(allowed)
            )
            return cls(cores, lock_dir=lock_dir)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"failed to discover Linux CPU topology: {exc}") from exc

    async def acquire(self, count: int) -> CpuLease:
        """Wait for and return a sibling-packed lease of ``count`` logical CPUs."""
        if count < 2 or count % 2 != 0:
            raise ValueError("CPU lease size must be a positive even number")
        if count % self._logical_cpus_per_core != 0:
            raise ValueError("CPU lease size must allocate complete physical cores")
        if count > self._max_node_cpus:
            raise ValueError(
                f"CPU lease requests {count} logical CPUs, but the largest "
                f"NUMA node has {self._max_node_cpus}"
            )
        core_count = count // self._logical_cpus_per_core
        token = object()
        started = time.monotonic()
        async with self._condition:
            self._waiters.append(token)
            try:
                while True:
                    allocation = (
                        self._try_acquire(core_count) if self._waiters[0] is token else None
                    )
                    if allocation is not None:
                        selected, lock_files = allocation
                        self._waiters.popleft()
                        cpus = tuple(
                            logical_cpu for core in selected for logical_cpu in core.logical_cpus
                        )
                        self._available.difference_update(core.key for core in selected)
                        self._condition.notify_all()
                        return CpuLease(
                            cpus=cpus,
                            physical_cores=tuple(
                                (core.socket_id, core.core_id) for core in selected
                            ),
                            numa_node=selected[0].numa_node,
                            wait_seconds=time.monotonic() - started,
                            _allocator=self,
                            _lock_files=lock_files,
                        )
                    if self._lock_dir is None:
                        await self._condition.wait()
                    else:
                        try:
                            await asyncio.wait_for(
                                self._condition.wait(),
                                timeout=HOST_LOCK_POLL_SECONDS,
                            )
                        except TimeoutError:
                            pass
            except BaseException:
                if token in self._waiters:
                    self._waiters.remove(token)
                    self._condition.notify_all()
                raise

    async def release(
        self,
        physical_cores: tuple[tuple[int, int], ...],
        lock_files: tuple[BinaryIO, ...] = (),
    ) -> None:
        """Return physical cores and wake queued requests."""
        async with self._condition:
            cores = set(physical_cores)
            unknown = cores - self._core_by_key.keys()
            if unknown:
                raise ValueError(f"CPU lease contains unknown physical cores: {sorted(unknown)}")
            duplicate = cores & self._available
            if duplicate:
                raise ValueError(f"CPU lease was already released: {sorted(duplicate)}")
            for lock_file in lock_files:
                lock_file.close()
            self._available.update(cores)
            self._condition.notify_all()

    def quarantine(self, lock_files: tuple[BinaryIO, ...]) -> None:
        """Retain host locks for cores whose shadow may still be running."""
        self._quarantined_lock_files.extend(lock_files)


_allocator_var: contextvars.ContextVar[HostCpuAllocator | None] = contextvars.ContextVar(
    "perfrace_host_cpu_allocator",
    default=None,
)
_trial_cpu_leases_enabled_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "perfrace_trial_cpu_leases_enabled",
    default=False,
)
_environment_leases: dict[int, tuple[object, CpuLease]] = {}


def configure_host_cpu_allocator(enabled: bool, *, lock_dir: Path) -> bool:
    """Create the run allocator and return whether CPU leases are available."""
    if not enabled:
        _allocator_var.set(None)
        return False
    if not host_cpu_allocation_supported():
        logger.warning(
            "Host CPU allocation is unavailable on this platform; "
            "measurement shadows will run without CPU affinity"
        )
        _allocator_var.set(None)
        return False
    try:
        allocator = HostCpuAllocator.discover(lock_dir=lock_dir)
    except RuntimeError as exc:
        logger.warning(
            "Host CPU allocator setup failed; measurement shadows will run "
            "without CPU affinity: %s",
            exc,
        )
        _allocator_var.set(None)
        return False
    _allocator_var.set(allocator)
    return True


def configure_trial_cpu_leases(enabled: bool) -> None:
    """Enable or disable trial-owned CPU leases in the current run context."""
    _trial_cpu_leases_enabled_var.set(enabled)


def trial_cpu_leases_enabled() -> bool:
    """Return whether checkpoint trials should own their CPU leases."""
    return _trial_cpu_leases_enabled_var.get()


def bind_environment_cpu_lease(environment: object, lease: CpuLease) -> None:
    """Associate a running trial environment with its owned CPU lease."""
    key = id(environment)
    if key in _environment_leases:
        raise RuntimeError("environment already has a trial CPU lease")
    _environment_leases[key] = (environment, lease)


def get_environment_cpu_lease(environment: object) -> CpuLease | None:
    """Return the CPU lease owned by a trial environment, if any."""
    entry = _environment_leases.get(id(environment))
    if entry is None or entry[0] is not environment:
        return None
    return entry[1]


def unbind_environment_cpu_lease(environment: object) -> CpuLease | None:
    """Remove and return a trial environment's owned CPU lease."""
    entry = _environment_leases.pop(id(environment), None)
    if entry is None or entry[0] is not environment:
        return None
    return entry[1]


def write_cpu_compose_override(path: Path, lease: CpuLease) -> Path:
    """Write a Compose override pinning the main service to one CPU lease."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "services": {
                    "main": {
                        "cpuset": ",".join(str(cpu) for cpu in lease.cpus),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def get_host_cpu_allocator() -> HostCpuAllocator | None:
    """Return the allocator configured for the current PerfRace run."""
    return _allocator_var.get()
