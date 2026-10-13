"""Run verification in disposable containers created from a task snapshot.

Harbor's DockerEnvironment supplies snapshot, startup, execution, and cleanup
operations. Verification modifies the shadow rather than the agent's container.
Callers stop shadows in ``finally`` blocks; cleanup has a separate timeout.

``ShadowPool`` bounds concurrent repetitions. It returns coroutines for the
caller to schedule; each repetition has its own environment and usage identity.
"""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeVar

from harbor.constants import MAIN_SERVICE_NAME
from harbor.environments.docker.docker import DockerEnvironment
from harbor.environments.factory import EnvironmentFactory
from harbor.models.environment_type import EnvironmentType
from harbor.models.trial.config import ServiceVolumeConfig
from harbor.models.trial.paths import TrialPaths

from perfrace.run.services.resources import (
    CpuLease,
    get_environment_cpu_lease,
    get_host_cpu_allocator,
    write_cpu_compose_override,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def sanitize_image_tag(name: str) -> str:
    """Coerce an arbitrary identifier into a valid Docker image tag.

    A small, local copy of ``docker.py``'s own (private)
    ``_sanitize_docker_compose_project_name`` logic (lowercase, prepend
    ``0`` if the leading character isn't alphanumeric, replace any other
    disallowed character with ``-``).
    """
    name = name.lower()
    if not re.match(r"^[a-z0-9]", name):
        name = "0" + name
    return re.sub(r"[^a-z0-9_-]", "-", name)


@dataclasses.dataclass(frozen=True)
class ShadowRunResult:
    """Outcome of running one command to completion in a disposable shadow.

    ``stdout`` is the command's combined stdout+stderr, captured in memory.
    ``timed_out`` is set only by a fanned-out repetition's own inner
    timeout (see ``run_measurement()``); a single, non-fanned-out
    ``run_in_shadow()`` call has no inner timeout and never sets it.
    """

    exit_code: int
    oom_killed: bool
    stdout: str = ""
    timed_out: bool = False
    host_resources: dict[str, object] | None = None


async def commit_snapshot(source: DockerEnvironment, tag: str) -> None:
    """Snapshot ``source``'s current container state via ``docker compose
    commit`` (paused, consistent) so a shadow can be built from it.
    """
    await source.commit_service(tag)


async def remove_snapshot(tag: str, *, timeout_sec: float = 60.0) -> None:
    """Remove one checkpoint snapshot after all shadows using it have stopped."""
    process = await asyncio.create_subprocess_exec(
        "docker",
        "image",
        "rm",
        tag,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError as exc:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            await asyncio.shield(process.wait())
        raise RuntimeError(f"timed out removing snapshot image {tag}") from exc
    error = stderr.decode(errors="replace").strip()
    if process.returncode != 0 and "no such image" not in error.lower():
        raise RuntimeError(f"failed to remove snapshot image {tag}: {error}")


async def _set_container_paused(container_id: str, *, paused: bool) -> None:
    """Run one cancellation-safe Docker pause state transition."""
    action = "pause" if paused else "unpause"
    process = await asyncio.create_subprocess_exec(
        "docker",
        action,
        container_id,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await process.communicate()
    except asyncio.CancelledError:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            await asyncio.shield(process.wait())
        raise
    error = stderr.decode(errors="replace").strip()
    if process.returncode != 0 and not (not paused and "is not paused" in error.lower()):
        raise RuntimeError(f"docker {action} failed for {container_id}: {error}")


async def _complete_cleanup(cleanup: Coroutine[object, object, T]) -> T:
    """Finish cleanup before propagating cancellation."""
    task = asyncio.create_task(cleanup)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def _complete_cleanup_capturing_cancellation(
    cleanup: Coroutine[object, object, T],
) -> tuple[T, asyncio.CancelledError | None]:
    """Finish cleanup and return cancellation for propagation afterward."""
    task = asyncio.create_task(cleanup)
    try:
        return await asyncio.shield(task), None
    except asyncio.CancelledError as exc:
        return await task, exc


@asynccontextmanager
async def paused_main_container(environment: DockerEnvironment) -> AsyncIterator[None]:
    """Pause the source container and always complete an unpause attempt."""
    container_id = await environment.resolve_service_container_id()
    if container_id is None:
        raise RuntimeError("could not resolve the main container for CPU isolation")
    try:
        await _set_container_paused(container_id, paused=True)
        yield
    finally:
        await _complete_cleanup(_set_container_paused(container_id, paused=False))


async def spawn_shadow(
    source: DockerEnvironment,
    tag: str,
    *,
    environment_name: str,
    session_id: str,
    trial_paths: TrialPaths,
    mounts: list[ServiceVolumeConfig] | None = None,
    cpu_lease: CpuLease | None = None,
) -> DockerEnvironment:
    """Construct and start a sibling ``DockerEnvironment`` pinned to the
    snapshot image ``tag``, inheriting ``source``'s ``task_env_config``
    (with ``docker_image`` overridden), ``network_policy``, and
    ``extra_docker_compose_paths`` unchanged. The caller owns the returned
    environment's lifecycle and must call ``teardown_shadow`` on it when
    done.
    """
    task_env_config = source.task_env_config.model_copy(update={"docker_image": tag})
    extra_compose = list(source.extra_docker_compose_paths)
    if cpu_lease is not None:
        extra_compose.append(cpu_compose_path(trial_paths, session_id, cpu_lease))
    shadow = EnvironmentFactory.create_environment(
        type=EnvironmentType.DOCKER,
        environment_dir=source.environment_dir,
        environment_name=environment_name,
        session_id=session_id,
        trial_paths=trial_paths,
        task_env_config=task_env_config,
        mounts=mounts,
        network_policy=source.network_policy,
        extra_docker_compose=extra_compose,
    )
    assert isinstance(shadow, DockerEnvironment)
    try:
        await shadow.start(force_build=False)
    except BaseException:
        stopped = await _complete_cleanup(teardown_shadow(shadow))
        if not stopped and cpu_lease is not None:
            cpu_lease.quarantine()
        raise
    return shadow


async def _inspect_container_state(container_id: str) -> dict[str, Any] | None:
    """Read Docker state for one already-resolved container ID."""
    process = await asyncio.create_subprocess_exec(
        "docker",
        "inspect",
        container_id,
        "--format",
        "{{json .State}}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return None
    try:
        state = json.loads(stdout.decode())
    except (ValueError, UnicodeDecodeError):
        return None
    return state if isinstance(state, dict) else None


async def get_container_state(
    environment: DockerEnvironment, *, service: str = MAIN_SERVICE_NAME
) -> dict[str, Any] | None:
    """Read a service's own container ``State`` (Docker's raw per-container
    metadata: ``Status``/``Running``/``OOMKilled``/``ExitCode``/...) via
    ``docker inspect``, resolving the actual container ID from
    ``environment``'s own compose project first. Returns ``None`` if the
    container can't be resolved or inspected (e.g. already removed) --
    callers should treat that the same as "state unknown", not raise.
    """
    container_id = await environment.resolve_service_container_id(service)
    if container_id is None:
        return None
    return await _inspect_container_state(container_id)


async def run_in_shadow(
    shadow: DockerEnvironment, command: str, *, env: dict[str, str] | None = None
) -> ShadowRunResult:
    """Execute a command in an already-started shadow and return its outcome.

    The caller must call ``teardown_shadow`` in a ``finally`` block, including
    when execution is cancelled by an outer timeout.
    """
    result = await shadow.exec(command, env=env)
    state = await get_container_state(shadow)
    oom_killed = bool(state.get("OOMKilled")) if state is not None else False
    return ShadowRunResult(
        exit_code=result.return_code, oom_killed=oom_killed, stdout=result.stdout or ""
    )


async def teardown_shadow(shadow: DockerEnvironment, *, timeout_sec: float = 60.0) -> bool:
    """Best-effort ``docker compose down --rmi local --volumes
    --remove-orphans`` (via ``DockerEnvironment.stop(delete=True)``) for
    this one shadow's own compose project, bounded by a fixed timeout
    independent of any task.toml/trial value.

    Never raises for ordinary teardown failures. Returns whether the main
    shadow container is confirmed absent or stopped, so callers only release
    pinned CPUs once they are no longer in use.
    """
    try:
        await asyncio.wait_for(shadow.stop(delete=True), timeout=timeout_sec)
    except Exception as exc:
        logger.warning(
            "Shadow teardown failed or timed out (best-effort only, may leak "
            "the shadow container/image): %s",
            exc,
        )
    try:
        container_id = await shadow.resolve_service_container_id()
    except Exception as exc:
        logger.warning("Could not confirm shadow shutdown: %s", exc)
        return False
    if container_id is None:
        return True
    try:
        state = await _inspect_container_state(container_id)
    except Exception as exc:
        logger.warning("Could not inspect shadow container %s: %s", container_id, exc)
        return False
    if state is None:
        logger.warning("Could not inspect shadow container %s after teardown", container_id)
        return False
    stopped = not bool(state.get("Running"))
    if not stopped:
        logger.warning("Shadow container %s is still running after teardown", container_id)
    return stopped


class ShadowPool:
    """Bounds how many shadow-container repetitions run concurrently.

    Mirrors ``harbor.trial.queue.TrialQueue``'s own shape: an
    ``asyncio.Semaphore`` sized once at construction (``max_parallel``);
    ``submit()``/``submit_batch()`` return coroutines only, never schedule
    them -- the caller decides how (typically ``asyncio.TaskGroup``, as
    ``run_measurement()`` does below), the same contract
    ``TrialQueue.submit()`` documents for itself.
    """

    def __init__(self, max_parallel: int) -> None:
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def _run(self, factory: Callable[[], Awaitable[T]]) -> T:
        async with self._semaphore:
            return await factory()

    def submit(self, factory: Callable[[], Awaitable[T]]) -> Coroutine[Any, Any, T]:
        """Return a coroutine that calls ``factory()`` once this pool's
        concurrency semaphore is acquired. The caller decides how to
        schedule it (await, gather, TaskGroup).
        """
        return self._run(factory)

    def submit_batch(
        self,
        factories: list[Callable[[], Awaitable[T]]],
    ) -> list[Coroutine[Any, Any, T]]:
        """Return one coroutine per factory, ordered to match ``factories``."""
        return [self.submit(factory) for factory in factories]


_shadow_pool_var: contextvars.ContextVar[ShadowPool] = contextvars.ContextVar(
    "perfrace_shadow_pool"
)
_unpinned_shadow_pool_var: contextvars.ContextVar[ShadowPool] = contextvars.ContextVar(
    "perfrace_unpinned_shadow_pool"
)


def configure_shared_shadow_pool(max_concurrent_shadows: int) -> None:
    """Construct the ``ShadowPool`` every fanned-out verify() call in this
    job shares, mirroring ``harbor.job.Job`` constructing one
    ``TrialQueue`` for the whole job rather than one per trial. Called
    once, by ``PerfRaceJob.__init__``, before any trial's own async work
    starts -- every task spawned afterward within that same call tree
    inherits this binding automatically (``contextvars`` semantics), so
    ``get_shared_shadow_pool()`` reaches it without needing Harbor's own
    ``Trial``/``VerifierFactory`` machinery to pass it through explicitly.
    """
    _shadow_pool_var.set(ShadowPool(max_concurrent_shadows))
    _unpinned_shadow_pool_var.set(ShadowPool(1))


def get_shared_shadow_pool() -> ShadowPool:
    """The ``ShadowPool`` ``configure_shared_shadow_pool`` constructed.
    Raises if that hasn't happened in an ancestor context -- every real run
    goes through ``PerfRaceJob``, which always calls it first.
    """
    try:
        return _shadow_pool_var.get()
    except LookupError as exc:
        raise RuntimeError(
            "Shared shadow pool not configured -- PerfRaceJob.__init__ must call "
            "configure_shared_shadow_pool() before any trial runs."
        ) from exc


def get_unpinned_shadow_pool() -> ShadowPool:
    """Return the serial pool for tasks that cannot request a CPU lease."""
    try:
        return _unpinned_shadow_pool_var.get()
    except LookupError as exc:
        raise RuntimeError(
            "Unpinned shadow pool not configured -- PerfRaceJob.__init__ must call "
            "configure_shared_shadow_pool() before any trial runs."
        ) from exc


def repetition_session_id(base_session_id: str, index: int) -> str:
    """The distinct, addressable session id one fanned-out repetition's own
    shadow gets, derived from ``base_session_id`` (the parent verify()
    call's own) plus its 1-based ``index``.
    """
    return f"{base_session_id}__rep{index:02d}"


def repetition_stdout_path(trial_paths: TrialPaths, index: int) -> Path:
    """Where one repetition's own combined stdout+stderr is persisted, so
    it stays inspectable after the fact -- N concurrent repetitions can't
    all redirect to one shared file, so each gets its own, named by its
    1-based ``index``.
    """
    return trial_paths.verifier_dir / f"repetition-{index:02d}-stdout.txt"


def cpu_compose_path(
    trial_paths: TrialPaths,
    session_id: str,
    lease: CpuLease,
) -> Path:
    """Write the Docker Compose override that pins one shadow to its lease."""
    path = trial_paths.verifier_dir / f"{session_id}-host-resources.json"
    return write_cpu_compose_override(path, lease)


async def acquire_cpu_lease(source: DockerEnvironment) -> CpuLease | None:
    """Acquire the run-scoped CPU lease requested by this shadow."""
    allocator = get_host_cpu_allocator()
    if allocator is None:
        return None
    count = source.effective_cpus
    if count is None:
        logger.warning(
            "Task has no effective CPU count; measurement shadow will run without CPU affinity"
        )
        return None
    return await allocator.acquire(count)


async def run_measurement(
    source: DockerEnvironment,
    tag: str,
    command: str,
    *,
    n: int,
    timeout_sec: float,
    trial_paths: TrialPaths,
    environment_name: str,
    base_session_id: str,
    mounts: list[ServiceVolumeConfig] | None = None,
    env_factory: Callable[[str], dict[str, str] | None] | None = None,
) -> list[ShadowRunResult]:
    """Run ``command`` ``n`` times concurrently (bounded by the shared
    ``ShadowPool`` -- see ``get_shared_shadow_pool``), each in its own
    disposable shadow spawned from the same, already-committed snapshot
    ``tag``, via ``asyncio.TaskGroup`` for scheduling.

    Each repetition gets its own ``session_id`` (see
    ``repetition_session_id``), its own ``PERFRACE_REPETITION_INDEX`` env
    var (its 1-based index, since every repetition's shadow shares one
    bind-mounted ``verifier_dir`` -- see ``verifier.py``'s
    ``_shadow_mounts``), and, if ``env_factory`` is given, whatever extra
    ``env`` it returns for that ``session_id`` -- e.g. so independent LLM
    calls across repetitions are tracked under independent token-proxy
    identities. Its combined stdout+stderr is persisted via
    ``repetition_stdout_path`` before this call returns.

    A repetition whose own shadow fails to even spawn (an infra failure,
    not the command itself failing) is reported back as
    ``ShadowRunResult(exit_code=-1)`` rather than aborting its siblings --
    this call fans out ``n`` independent measurements, and one's
    infrastructure trouble is not evidence the others are unusable. A
    repetition that doesn't finish within ``timeout_sec`` is reported back
    as ``ShadowRunResult(timed_out=True)`` for the same reason.
    """
    pool = (
        get_unpinned_shadow_pool()
        if get_host_cpu_allocator() is not None and source.effective_cpus is None
        else get_shared_shadow_pool()
    )

    async def run_one(index: int) -> ShadowRunResult:
        session_id = repetition_session_id(base_session_id, index)
        inherited_lease = get_environment_cpu_lease(source)
        lease = inherited_lease or await acquire_cpu_lease(source)
        owns_lease = inherited_lease is None
        shadow: DockerEnvironment | None = None
        try:
            try:
                shadow = await spawn_shadow(
                    source,
                    tag,
                    environment_name=environment_name,
                    session_id=session_id,
                    trial_paths=trial_paths,
                    mounts=mounts,
                    cpu_lease=lease if owns_lease else None,
                )
            except Exception as exc:
                logger.warning(f"Repetition {index}: failed to spawn its shadow: {exc}")
                return ShadowRunResult(
                    exit_code=-1,
                    oom_killed=False,
                    host_resources=lease.to_details() if lease is not None else None,
                )
            env = {"PERFRACE_REPETITION_INDEX": str(index)}
            if env_factory is not None:
                env.update(env_factory(session_id) or {})
            try:
                result = await asyncio.wait_for(
                    run_in_shadow(shadow, command, env=env), timeout=timeout_sec
                )
            except asyncio.TimeoutError:
                result = ShadowRunResult(exit_code=-1, oom_killed=False, timed_out=True)
            return dataclasses.replace(
                result,
                host_resources=lease.to_details() if lease is not None else None,
            )
        finally:
            stopped = shadow is None
            cancellation: asyncio.CancelledError | None = None
            if shadow is not None:
                stopped, cancellation = await _complete_cleanup_capturing_cancellation(
                    teardown_shadow(shadow)
                )
            if lease is not None and owns_lease:
                if stopped:
                    await _complete_cleanup(lease.release())
                else:
                    lease.quarantine()
            if cancellation is not None:
                raise cancellation

    try:
        async with asyncio.TaskGroup() as task_group:
            tasks = [
                task_group.create_task(pool.submit(lambda i=i: run_one(i)))
                for i in range(1, n + 1)
            ]
        results = [task.result() for task in tasks]
        for index, result in enumerate(results, start=1):
            repetition_stdout_path(trial_paths, index).write_text(result.stdout, encoding="utf-8")
        return results
    finally:
        await _complete_cleanup(remove_snapshot(tag))
