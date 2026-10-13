"""Process-isolated Harbor trial execution for opt-in controller memory limits."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any
from uuid import uuid4

from harbor.environments.docker.docker import _sanitize_docker_compose_project_name
from harbor.models.job.lock import TaskLock, TrialLock, build_trial_lock
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.result import AgentInfo, ExceptionInfo, TrialResult
from harbor.models.trial.paths import TrialPaths
from harbor.trial.hooks import HookCallback, TrialEvent, TrialHookEvent
from harbor.trial.queue import TrialQueue


class ControllerMemoryLimitError(RuntimeError):
    """The per-trial host controller exceeded its configured memory limit."""


class ControllerWorkerError(RuntimeError):
    """The per-trial host controller worker exited without a TrialResult."""


class ControllerHookError(RuntimeError):
    """A parent-side Harbor lifecycle hook failed during an isolated trial."""


def _fallback_trial_lock(config: TrialConfig) -> TrialLock:
    task_config = config.task
    if task_config.is_package_task():
        task_type = "package"
        task_name = task_config.name or "unknown/unknown"
    elif task_config.is_git_task():
        task_type = "git"
        task_name = task_config.path.name if task_config.path is not None else "unknown"
    else:
        task_type = "local"
        task_name = task_config.path.name if task_config.path is not None else "unknown"
    return TrialLock(
        task=TaskLock(
            name=task_name,
            type=task_type,
            digest="sha256:" + "0" * 64,
            source=task_config.source,
            path=task_config.path,
            git_url=task_config.git_url,
            git_commit_id=task_config.git_commit_id,
        ),
        install_only=config.install_only,
        timeout_multiplier=config.timeout_multiplier,
        agent_timeout_multiplier=config.agent_timeout_multiplier,
        verifier_timeout_multiplier=config.verifier_timeout_multiplier,
        agent_setup_timeout_multiplier=config.agent_setup_timeout_multiplier,
        environment_build_timeout_multiplier=config.environment_build_timeout_multiplier,
        agent=config.agent,
        environment=config.environment,
        verifier=config.verifier,
    )


class ProcessIsolatedTrial:
    """A Harbor trial-compatible proxy backed by one memory-limited worker."""

    def __init__(
        self,
        config: TrialConfig,
        *,
        controller_memory_mb: int,
        host_resources_enabled: bool,
        host_resource_lock_dir: Path,
        trial_cpu_leases: bool,
        trial_lock: TrialLock | None = None,
        task_name: str | None = None,
        task_checksum: str | None = None,
    ) -> None:
        self.config = config
        self.paths = TrialPaths(config.trials_dir / config.trial_name)
        self._controller_memory_mb = controller_memory_mb
        self._host_resources_enabled = host_resources_enabled
        self._host_resource_lock_dir = host_resource_lock_dir
        self._trial_cpu_leases = trial_cpu_leases
        self._trial_lock = trial_lock or _fallback_trial_lock(config)
        self._task_name = task_name or self._trial_lock.task.name
        self._task_checksum = task_checksum or self._trial_lock.task.digest
        self._hooks: dict[TrialEvent, list[HookCallback]] = {event: [] for event in TrialEvent}
        digest = sha1(
            f"{config.job_id}:{config.trial_name}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:20]
        self._unit_name = f"perfrace-trial-{digest}"
        self._scope_unit_name = f"{self._unit_name}.scope"
        self._control_dir = self.paths.trial_dir / ".controller-worker"
        self._event_dir = self._control_dir / "events"
        self._config_path = self._control_dir / "config.json"
        self._worker_log_path = self._control_dir / "worker.log"
        self._last_event: TrialHookEvent | None = None

    def add_hook(self, event: Any, hook: Any) -> None:
        """Register a Harbor trial hook on the parent-side proxy."""
        self._hooks[event].append(hook)

    async def _emit(self, event: TrialHookEvent) -> None:
        self._last_event = event
        for hook in self._hooks[event.event]:
            await hook(event)

    async def _emit_terminal(self, event: TrialHookEvent) -> BaseException | None:
        self._last_event = event
        first_error: BaseException | None = None
        for hook in self._hooks[event.event]:
            try:
                await hook(event)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        return first_error

    def _worker_command(self) -> list[str]:
        systemd_run = shutil.which("systemd-run")
        if systemd_run is None:
            raise RuntimeError("trial process isolation requires systemd-run")
        repo_root = Path(__file__).resolve().parents[2]
        command = [
            systemd_run,
            "--user",
            "--scope",
            "--unit",
            self._unit_name,
            "--expand-environment=no",
            "--property",
            f"MemoryMax={self._controller_memory_mb}M",
            "--property",
            "MemorySwapMax=0",
            "--working-directory",
            str(repo_root),
            sys.executable,
            "-m",
            "perfrace.run.isolation",
            "worker",
            "--config",
            str(self._config_path),
            "--event-dir",
            str(self._event_dir),
            "--parent-pid",
            str(os.getpid()),
            "--host-resource-lock-dir",
            str(self._host_resource_lock_dir),
        ]
        if self._host_resources_enabled:
            command.append("--host-resources-enabled")
        if self._trial_cpu_leases:
            command.append("--trial-cpu-leases")
        return command

    async def _relay_events(self, process: Any) -> None:
        sequence = 0
        while process.returncode is None:
            matches = sorted(self._event_dir.glob(f"{sequence:04d}-*.json"))
            if not matches:
                await asyncio.sleep(0.02)
                continue
            event_path = matches[0]
            event = TrialHookEvent.model_validate_json(event_path.read_text(encoding="utf-8"))
            await self._emit(event)
            event_path.with_suffix(".ack").write_text("", encoding="utf-8")
            sequence += 1

        while True:
            matches = sorted(self._event_dir.glob(f"{sequence:04d}-*.json"))
            if not matches:
                return
            event_path = matches[0]
            event = TrialHookEvent.model_validate_json(event_path.read_text(encoding="utf-8"))
            await self._emit(event)
            event_path.with_suffix(".ack").write_text("", encoding="utf-8")
            sequence += 1

    async def _synthesize_failure(
        self,
        *,
        exception_type: str,
        message: str,
        details: str,
    ) -> TrialResult:
        if self._last_event is None:
            now = datetime.now(timezone.utc)
            result = TrialResult(
                trial_name=self.config.trial_name,
                task_name=self._task_name,
                task_id=self.config.task.get_task_id(),
                started_at=now,
                config=self.config,
                task_checksum=self._task_checksum,
                trial_uri=self.paths.trial_dir.expanduser().resolve().as_uri(),
                agent_info=AgentInfo(
                    name=self.config.agent.name or self.config.agent.import_path or "unknown",
                    version="worker-unavailable",
                ),
                source=self.config.task.source,
            )
            self.paths.trial_dir.mkdir(parents=True, exist_ok=True)
            self.paths.lock_path.write_text(
                self._trial_lock.model_dump_json(indent=4, exclude_none=True),
                encoding="utf-8",
            )
            start_event = TrialHookEvent(
                event=TrialEvent.START,
                task_name=result.task_name,
                config=self.config,
                result=result,
                lock=self._trial_lock,
            )
            start_error = await self._emit_terminal(start_event)
            if start_error is not None:
                details += "\nParent START hook also failed:\n" + "".join(
                    traceback.format_exception(start_error)
                )

        result = self._last_event.result.model_copy(deep=True)
        now = datetime.now(timezone.utc)
        result.exception_info = ExceptionInfo(
            exception_type=exception_type,
            exception_message=message,
            exception_traceback=details,
            occurred_at=now,
        )
        result.finished_at = now
        self.paths.trial_dir.mkdir(parents=True, exist_ok=True)
        self.paths.result_path.write_text(result.model_dump_json(indent=4), encoding="utf-8")
        end_error = await self._emit_terminal(
            self._last_event.model_copy(
                update={
                    "event": TrialEvent.END,
                    "result": result,
                    "timestamp": now,
                }
            )
        )
        if end_error is not None:
            result.exception_info.exception_traceback += (
                "\nParent END hook also failed:\n" + "".join(traceback.format_exception(end_error))
            )
            self.paths.result_path.write_text(
                result.model_dump_json(indent=4),
                encoding="utf-8",
            )
        return result

    async def _stop_unit(self) -> None:
        systemctl = shutil.which("systemctl")
        if systemctl is None:
            return
        process = await asyncio.create_subprocess_exec(
            systemctl,
            "--user",
            "kill",
            "--kill-whom=all",
            "--signal=TERM",
            self._scope_unit_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        await asyncio.sleep(1)
        process = await asyncio.create_subprocess_exec(
            systemctl,
            "--user",
            "kill",
            "--kill-whom=all",
            "--signal=KILL",
            self._scope_unit_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()

    async def _unit_property(self, property_name: str) -> str | None:
        systemctl = shutil.which("systemctl")
        if systemctl is None:
            return None
        process = await asyncio.create_subprocess_exec(
            systemctl,
            "--user",
            "show",
            self._scope_unit_name,
            "--property",
            property_name,
            "--value",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await process.communicate()
        if process.returncode != 0:
            return None
        return output.decode().strip() or None

    async def _unit_result(self) -> str | None:
        return await self._unit_property("Result")

    async def _wait_for_unit_settle(self) -> None:
        for attempt in range(40):
            state = await self._unit_property("ActiveState")
            if state not in {"active", "activating", "deactivating", "reloading"}:
                return
            if attempt < 39:
                await asyncio.sleep(0.05)

    async def _reset_unit(self) -> None:
        systemctl = shutil.which("systemctl")
        if systemctl is None:
            return
        for attempt in range(5):
            process = await asyncio.create_subprocess_exec(
                systemctl,
                "--user",
                "reset-failed",
                self._scope_unit_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
            state = await self._unit_property("ActiveState")
            if state not in {"active", "activating", "deactivating", "failed", "reloading"}:
                return
            if attempt < 4:
                await asyncio.sleep(0.05)

    async def _cleanup_trial_runtime(self) -> None:
        trial_prefix = _sanitize_docker_compose_project_name(self.config.trial_name)
        main_project = _sanitize_docker_compose_project_name(f"{self.config.trial_name}__env")

        def belongs_to_trial(project: str) -> bool:
            return project == main_project or (
                project.startswith(f"{trial_prefix}__") and "verify-shadow" in project
            )

        list_containers = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        container_output, _ = await list_containers.communicate()
        container_ids = []
        for container_id in container_output.decode().split():
            inspect = await asyncio.create_subprocess_exec(
                "docker",
                "inspect",
                "--format",
                '{{ index .Config.Labels "com.docker.compose.project" }}',
                container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            project_output, _ = await inspect.communicate()
            if inspect.returncode == 0 and belongs_to_trial(project_output.decode().strip()):
                container_ids.append(container_id)
        if container_ids:
            remove_containers = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                *container_ids,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await remove_containers.wait()

        list_networks = await asyncio.create_subprocess_exec(
            "docker",
            "network",
            "ls",
            "-q",
            "--filter",
            "label=com.docker.compose.project",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        network_output, _ = await list_networks.communicate()
        network_ids = []
        for network_id in network_output.decode().split():
            inspect = await asyncio.create_subprocess_exec(
                "docker",
                "network",
                "inspect",
                "--format",
                '{{ index .Labels "com.docker.compose.project" }}',
                network_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            project_output, _ = await inspect.communicate()
            if inspect.returncode == 0 and belongs_to_trial(project_output.decode().strip()):
                network_ids.append(network_id)
        if network_ids:
            remove_networks = await asyncio.create_subprocess_exec(
                "docker",
                "network",
                "rm",
                *network_ids,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await remove_networks.wait()

    def _worker_log_tail(self, max_bytes: int = 64 * 1024) -> str:
        if not self._worker_log_path.is_file():
            return ""
        with self._worker_log_path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(size - max_bytes, 0))
            return stream.read().decode(errors="replace")

    async def run(self) -> TrialResult:
        """Run the worker, relay hooks, and return or synthesize its TrialResult."""
        self._event_dir.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            self.config.model_dump_json(indent=4),
            encoding="utf-8",
        )
        self._worker_log_path.touch()
        with self._worker_log_path.open("ab") as worker_log:
            process = await asyncio.create_subprocess_exec(
                *self._worker_command(),
                stdout=worker_log,
                stderr=asyncio.subprocess.STDOUT,
            )
            relay_task = asyncio.create_task(self._relay_events(process))
            wait_task = asyncio.create_task(process.wait())
            try:
                await asyncio.gather(wait_task, relay_task)
            except asyncio.CancelledError:
                await self._stop_unit()
                await self._cleanup_trial_runtime()
                await self._wait_for_unit_settle()
                await self._reset_unit()
                relay_task.cancel()
                wait_task.cancel()
                if self._last_event is not None:
                    await self._emit_terminal(
                        self._last_event.model_copy(
                            update={
                                "event": TrialEvent.CANCEL,
                                "timestamp": datetime.now(timezone.utc),
                            }
                        )
                    )
                raise
            except Exception as exc:
                await self._stop_unit()
                await self._cleanup_trial_runtime()
                await self._wait_for_unit_settle()
                await self._reset_unit()
                relay_task.cancel()
                wait_task.cancel()
                return await self._synthesize_failure(
                    exception_type=ControllerHookError.__name__,
                    message=f"Parent trial hook failed: {exc}",
                    details="".join(traceback.format_exception(exc)),
                )
            except BaseException:
                await self._stop_unit()
                await self._cleanup_trial_runtime()
                await self._wait_for_unit_settle()
                await self._reset_unit()
                relay_task.cancel()
                wait_task.cancel()
                raise

        await self._wait_for_unit_settle()
        unit_result = await self._unit_result()
        await self._reset_unit()
        if self.paths.result_path.is_file():
            result = TrialResult.model_validate_json(
                self.paths.result_path.read_text(encoding="utf-8")
            )
            if self._last_event is None or self._last_event.event != TrialEvent.END:
                if self._last_event is None:
                    raise RuntimeError(
                        f"trial worker {self.config.trial_name} wrote a result without START"
                    )
                await self._emit(
                    self._last_event.model_copy(
                        update={
                            "event": TrialEvent.END,
                            "result": result,
                            "timestamp": datetime.now(timezone.utc),
                        }
                    )
                )
            return result

        await self._cleanup_trial_runtime()
        details = self._worker_log_tail()
        if unit_result == "oom-kill" or process.returncode in {-9, 137}:
            return await self._synthesize_failure(
                exception_type=ControllerMemoryLimitError.__name__,
                message=(
                    f"Trial controller exceeded {self._controller_memory_mb} MiB memory limit"
                ),
                details=details,
            )
        return await self._synthesize_failure(
            exception_type=ControllerWorkerError.__name__,
            message=f"Trial controller worker exited with code {process.returncode}",
            details=details,
        )


class ProcessIsolatedTrialQueue(TrialQueue):
    """Preserve Harbor scheduling while executing each trial in a cgroup worker."""

    def __init__(
        self,
        *args: Any,
        controller_memory_mb: int,
        host_resources_enabled: bool,
        host_resource_lock_dir: Path,
        trial_cpu_leases: bool,
        trial_locks: dict[str, TrialLock],
        trial_task_metadata: dict[str, tuple[str, str]],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._controller_memory_mb = controller_memory_mb
        self._host_resources_enabled = host_resources_enabled
        self._host_resource_lock_dir = host_resource_lock_dir
        self._trial_cpu_leases = trial_cpu_leases
        self._trial_locks = trial_locks
        self._trial_task_metadata = trial_task_metadata

    async def _execute_trial_with_retries(
        self,
        trial_config: TrialConfig,
    ) -> TrialResult:
        """Run Harbor's existing retry policy around a process-isolated trial."""
        for attempt in range(self._retry_config.max_retries + 1):
            trial = ProcessIsolatedTrial(
                trial_config,
                controller_memory_mb=self._controller_memory_mb,
                host_resources_enabled=self._host_resources_enabled,
                host_resource_lock_dir=self._host_resource_lock_dir,
                trial_cpu_leases=self._trial_cpu_leases,
                trial_lock=self._trial_locks[trial_config.trial_name],
                task_name=self._trial_task_metadata[trial_config.trial_name][0],
                task_checksum=self._trial_task_metadata[trial_config.trial_name][1],
            )
            self._setup_hooks(trial)
            result = await trial.run()

            if result.exception_info is None:
                return result
            if not self._should_retry_exception(result.exception_info.exception_type):
                self._logger.debug(
                    "Not retrying trial because the exception is not in "
                    "include_exceptions or the maximum number of retries has been reached"
                )
                return result
            if attempt == self._retry_config.max_retries:
                self._logger.debug(
                    "Not retrying trial because the maximum number of retries has been reached"
                )
                return result

            shutil.rmtree(trial.paths.trial_dir, ignore_errors=True)
            delay_sec = self._calculate_backoff_delay_sec(attempt)
            self._logger.debug(
                "Trial %s failed with exception %s. Retrying in %.2f seconds...",
                trial_config.trial_name,
                result.exception_info.exception_type,
                delay_sec,
            )
            await asyncio.sleep(delay_sec)

        raise RuntimeError(
            f"Trial {trial_config.trial_name} produced no result. This should never happen."
        )


def configure_process_isolated_trial_queue(
    job: Any,
    *,
    memory_mb: int,
    host_resources_enabled: bool,
    host_allocator_configured: bool,
    host_resource_lock_dir: Path,
    trial_cpu_leases: bool,
) -> None:
    """Replace a PerfRace job's queue while preserving Harbor's registered hooks."""
    if not trial_cpu_leases:
        raise ValueError("trial process isolation currently requires trial_cpu_leases")
    if not host_allocator_configured:
        raise RuntimeError("trial process isolation requires the host CPU allocator")
    if "max_concurrent_shadows" in job.config.verifier.kwargs:
        raise ValueError("trial process isolation does not support max_concurrent_shadows")
    unsupported_agents = [
        agent.name or agent.import_path or "unknown"
        for agent in job.config.agents
        if not agent.cacheable and not agent.task_budget_sec
    ]
    if unsupported_agents:
        raise ValueError(
            "trial process isolation currently requires checkpoint candidate agents: "
            + ", ".join(unsupported_agents)
        )
    from perfrace.run.types import PerfRaceConfig

    task_metadata: dict[Any, tuple[str, str]] = {}
    for task_config in job._task_configs:
        download = job._task_download_results.get(task_config.get_task_id())
        task_dir = download.path if download is not None else task_config.get_local_path()
        perfrace_config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
        if perfrace_config is None or perfrace_config.task_checksum is None:
            raise ValueError(
                f"trial process isolation requires readable PerfRace task metadata: {task_dir}"
            )
        task_metadata[task_config.get_task_id()] = (
            perfrace_config.task_name,
            perfrace_config.task_checksum,
        )
        measurement = perfrace_config.measurement if perfrace_config is not None else None
        if measurement is not None and measurement.repetition_scope != "internal":
            raise ValueError(
                "trial process isolation currently requires internal measurement "
                f"repetitions: {task_dir}"
            )
    validate_process_isolation_support()
    original = job._trial_queue
    hooks = {event: list(callbacks) for event, callbacks in original._hooks.items()}
    trial_locks: dict[str, TrialLock] = {}
    trial_task_metadata: dict[str, tuple[str, str]] = {}
    for trial_config in job._trial_configs:
        download = job._task_download_results.get(trial_config.task.get_task_id())
        trial_locks[trial_config.trial_name] = (
            build_trial_lock(
                trial_config=trial_config,
                task_download_result=download,
            )
            if download is not None
            else _fallback_trial_lock(trial_config)
        )
        trial_task_metadata[trial_config.trial_name] = task_metadata[
            trial_config.task.get_task_id()
        ]
    job._trial_queue = ProcessIsolatedTrialQueue(
        n_concurrent=original._n_concurrent,
        retry_config=original._retry_config,
        hooks=hooks,
        controller_memory_mb=memory_mb,
        host_resources_enabled=host_resources_enabled,
        host_resource_lock_dir=host_resource_lock_dir,
        trial_cpu_leases=trial_cpu_leases,
        trial_locks=trial_locks,
        trial_task_metadata=trial_task_metadata,
    )


def validate_process_isolation_support() -> None:
    """Fail before launch unless user systemd can enforce cgroup MemoryMax."""
    if sys.platform != "linux":
        raise RuntimeError("trial process isolation requires Linux cgroup v2")
    controllers_path = Path("/sys/fs/cgroup/cgroup.controllers")
    try:
        controllers = set(controllers_path.read_text(encoding="utf-8").split())
    except OSError as exc:
        raise RuntimeError("trial process isolation requires Linux cgroup v2") from exc
    if "memory" not in controllers:
        raise RuntimeError("trial process isolation requires the cgroup v2 memory controller")
    systemd_run = shutil.which("systemd-run")
    systemctl = shutil.which("systemctl")
    if systemd_run is None or systemctl is None:
        raise RuntimeError("trial process isolation requires systemd-run and systemctl")

    unit = f"perfrace-memory-check-{uuid4().hex[:12]}"
    command = [
        systemd_run,
        "--user",
        "--scope",
        "--unit",
        unit,
        "--expand-environment=no",
        "-p",
        "MemoryMax=64M",
        "-p",
        "MemorySwapMax=0",
        "/bin/true",
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("trial process isolation cgroup smoke failed") from exc
    if result.returncode != 0:
        raise RuntimeError("trial process isolation cgroup smoke failed: " + result.stdout.strip())


async def _run_trial(
    config_path: Path,
    event_dir: Path,
    parent_pid: int,
    *,
    host_resources_enabled: bool,
    host_resource_lock_dir: Path,
    trial_cpu_leases: bool,
) -> None:
    """Run one unchanged Harbor Trial and synchronously relay its lifecycle hooks."""
    from harbor.trial.trial import Trial

    from perfrace.run.services.resources import (
        configure_host_cpu_allocator,
        configure_trial_cpu_leases,
    )
    from perfrace.run.verifier.shadow import configure_shared_shadow_pool

    allocator_configured = configure_host_cpu_allocator(
        host_resources_enabled,
        lock_dir=host_resource_lock_dir,
    )
    if trial_cpu_leases and not allocator_configured:
        raise RuntimeError("trial CPU leases require a configured host CPU allocator")
    configure_trial_cpu_leases(trial_cpu_leases)
    configure_shared_shadow_pool(1)

    config = TrialConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    trial = await Trial.create(config)
    event_dir.mkdir(parents=True, exist_ok=True)
    sequence = 0

    async def relay(event: TrialHookEvent) -> None:
        nonlocal sequence
        event_path = event_dir / f"{sequence:04d}-{event.event.value}.json"
        temporary = event_path.with_suffix(".json.tmp")
        temporary.write_text(event.model_dump_json(), encoding="utf-8")
        temporary.replace(event_path)
        acknowledgement = event_path.with_suffix(".ack")
        while not acknowledgement.exists():
            try:
                os.kill(parent_pid, 0)
            except ProcessLookupError as exc:
                raise RuntimeError(
                    "trial worker parent exited before hook acknowledgement"
                ) from exc
            await asyncio.sleep(0.01)
        event_path.unlink(missing_ok=True)
        acknowledgement.unlink(missing_ok=True)
        sequence += 1

    for event in TrialEvent:
        trial.add_hook(event, relay)
    await trial.run()


def main() -> int:
    """Run the worker entry point for one serialized Harbor trial."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["worker"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--event-dir", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--host-resources-enabled", action="store_true")
    parser.add_argument("--host-resource-lock-dir", type=Path, required=True)
    parser.add_argument("--trial-cpu-leases", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        _run_trial(
            args.config,
            args.event_dir,
            args.parent_pid,
            host_resources_enabled=args.host_resources_enabled,
            host_resource_lock_dir=args.host_resource_lock_dir,
            trial_cpu_leases=args.trial_cpu_leases,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
