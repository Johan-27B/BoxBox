"""Reuse baseline and fixed-patch measurements for cacheable trials.

PerfRaceJob checks the cache before starting a trial and represents a cache hit
as a completed TrialResult with a measurement.json file. Fresh measurements from
cacheable trials are persisted on completion. AgentConfig.cacheable controls
eligibility; model-backed candidate trials require fresh measurements.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

from harbor.environments.factory import EnvironmentFactory
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.result import AgentInfo, TrialResult
from harbor.trial.hooks import TrialHookEvent

from perfrace.run.cache import baseline_cache_key, read_baseline_trial, write_baseline_trial
from perfrace.run.config.resources import (
    DEFAULT_HOST_RESOURCE_LOCK_DIR,
    DEFAULT_TRIAL_CONTROLLER_MEMORY_MB,
)
from perfrace.run.services.resources import (
    configure_host_cpu_allocator,
    configure_trial_cpu_leases,
)
from perfrace.run.types import PerfRaceConfig, Measurement
from perfrace.run.verifier import MEASUREMENT_FILENAME
from perfrace.run.verifier.shadow import configure_shared_shadow_pool
from perfrace.run.isolation import configure_process_isolated_trial_queue
from perfrace.run.profiling import (
    has_performance_profile,
)

logger = logging.getLogger(__name__)

CACHED_AGENT_VERSION = "cached"
# Shadow concurrency is a run-level verifier setting; default to serial.
DEFAULT_MAX_CONCURRENT_SHADOWS = 1


class PerfRaceJob(Job):
    """A Harbor ``Job`` whose ``cacheable`` agents' trials can be served from cache."""

    def __init__(
        self,
        config: JobConfig,
        *,
        enable_cache: bool = False,
        baseline_cache_root: Path | None = None,
        host_resources_enabled: bool = True,
        host_resource_lock_dir: Path = DEFAULT_HOST_RESOURCE_LOCK_DIR,
        trial_cpu_leases: bool = False,
        trial_process_isolation: bool = False,
        trial_controller_memory_mb: int = DEFAULT_TRIAL_CONTROLLER_MEMORY_MB,
        **kwargs: Any,
    ) -> None:
        task_configs = kwargs.get("_task_configs")
        task_download_results = kwargs.get("_task_download_results")
        if task_configs is None or task_download_results is None:
            raise ValueError("PerfRaceJob requires resolved task configuration")
        self._enable_cache = enable_cache and baseline_cache_root is not None
        self._baseline_cache_root = baseline_cache_root
        allocator_configured = configure_host_cpu_allocator(
            host_resources_enabled,
            lock_dir=host_resource_lock_dir,
        )
        if trial_cpu_leases and not allocator_configured:
            configure_trial_cpu_leases(False)
            raise RuntimeError("trial CPU leases require a configured host CPU allocator")
        configure_trial_cpu_leases(trial_cpu_leases)
        default_shadow_concurrency = (
            config.n_concurrent_trials if allocator_configured else DEFAULT_MAX_CONCURRENT_SHADOWS
        )
        configure_shared_shadow_pool(
            config.verifier.kwargs.get(
                "max_concurrent_shadows",
                default_shadow_concurrency,
            )
        )
        super().__init__(config, **kwargs)
        if trial_process_isolation:
            configure_process_isolated_trial_queue(
                self,
                memory_mb=trial_controller_memory_mb,
                host_resources_enabled=host_resources_enabled,
                host_allocator_configured=allocator_configured,
                host_resource_lock_dir=host_resource_lock_dir,
                trial_cpu_leases=trial_cpu_leases,
            )
        if self._enable_cache:
            self.on_trial_ended(self._write_baseline_cache_if_cacheable)

    @classmethod
    async def create(  # type: ignore[override]
        cls,
        config: JobConfig,
        *,
        enable_cache: bool = False,
        baseline_cache_root: Path | None = None,
        host_resources_enabled: bool = True,
        host_resource_lock_dir: Path = DEFAULT_HOST_RESOURCE_LOCK_DIR,
        trial_cpu_leases: bool = False,
        trial_process_isolation: bool = False,
        trial_controller_memory_mb: int = DEFAULT_TRIAL_CONTROLLER_MEMORY_MB,
    ) -> "PerfRaceJob":
        cls._resolve_agent_skills(config)
        task_configs = await cls._resolve_task_configs(config)
        EnvironmentFactory.validate_resource_policies(config.environment)
        metrics = await cls._resolve_metrics(config, task_configs)
        task_download_results = await cls._cache_tasks(task_configs)

        return cls(
            config,
            _task_configs=task_configs,
            _metrics=metrics,
            _task_download_results=task_download_results,
            enable_cache=enable_cache,
            baseline_cache_root=baseline_cache_root,
            host_resources_enabled=host_resources_enabled,
            host_resource_lock_dir=host_resource_lock_dir,
            trial_cpu_leases=trial_cpu_leases,
            trial_process_isolation=trial_process_isolation,
            trial_controller_memory_mb=trial_controller_memory_mb,
        )

    def _maybe_init_existing_job(self) -> None:
        """Override Harbor's own trial-skip logic to seed it with synthetic results
        for cacheable trials.
        """
        super()._maybe_init_existing_job()
        if not self._enable_cache:
            return

        for trial_config in self._trial_configs:
            if not trial_config.agent.cacheable:
                continue
            if trial_config.trial_name in self._previous_trial_results:
                continue  # already resumed from this same job_dir

            cached_result = self._read_cached_trial(trial_config)
            if cached_result is None:
                logger.info("Baseline cache miss: trial=%s", trial_config.trial_name)
                continue

            logger.info(
                "Baseline cache hit: trial=%s (skipping re-measurement)",
                trial_config.trial_name,
            )
            self._existing_trial_configs.append(trial_config)
            self._existing_trial_results.append(cached_result)
            self._previous_trial_results[trial_config.trial_name] = cached_result

    def _read_cached_trial(self, trial_config: TrialConfig) -> TrialResult | None:
        """If this trial is cacheable and the baseline cache has a matching entry,
        return a synthetic ``TrialResult`` pointing at a directory holding the
        cached ``measurement.json``; otherwise return ``None``.
        """
        assert self._baseline_cache_root is not None
        task_dir = trial_config.task.get_local_path()
        config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
        if config is None or config.cache_fields is None:
            return None

        cache_fields = {**config.cache_fields, **_agent_cache_fields(trial_config, config)}
        cache_key = baseline_cache_key(cache_fields)
        cached_trial = read_baseline_trial(
            self._baseline_cache_root, config.instance_id, cache_key
        )
        if cached_trial is None:
            return None

        trial_dir = self.job_dir / trial_config.trial_name
        verifier_dir = trial_dir / "verifier"
        verifier_dir.mkdir(parents=True, exist_ok=True)
        (verifier_dir / MEASUREMENT_FILENAME).write_text(
            cached_trial.model_dump_json(indent=2), encoding="utf-8"
        )

        return TrialResult(
            task_name=config.task_name,
            trial_name=trial_config.trial_name,
            trial_uri=trial_dir.resolve().as_uri(),
            task_id=trial_config.task.get_task_id(),
            task_checksum=config.task_checksum or "",
            config=trial_config,
            agent_info=AgentInfo(
                name=trial_config.agent.name or trial_config.agent.import_path or "cached",
                version=CACHED_AGENT_VERSION,
            ),
        )

    async def _write_baseline_cache_if_cacheable(self, event: TrialHookEvent) -> None:
        """Hook for Harbor's own ``on_trial_ended()`` API: write a cacheable trial's
        freshly-measured ``Measurement`` to the baseline cache so a later run can hit it.

        Runs on a worker thread via ``asyncio.to_thread``: computing
        ``PerfRaceConfig.cache_fields`` hashes the whole task directory and
        can take real wall-clock time, and this hook fires while other
        trials in the same job may still be running concurrently -- blocking
        the event loop here would stall their progress.
        """
        if not self._enable_cache or not event.config.agent.cacheable:
            return
        assert self._baseline_cache_root is not None
        await asyncio.to_thread(
            _write_baseline_cache,
            self._baseline_cache_root,
            self.job_dir,
            event.config,
            event.result,
        )


def _write_baseline_cache(
    baseline_cache_root: Path,
    job_dir: Path,
    trial_config: TrialConfig,
    trial_result: TrialResult,
) -> None:
    """Write a cacheable measurement from a worker thread."""
    task_dir = trial_result.task_id.get_local_path()
    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    if config is None or config.cache_fields is None:
        return

    report_path = job_dir / trial_result.trial_name / "verifier" / MEASUREMENT_FILENAME
    try:
        trial = Measurement.model_validate_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return  # no valid measurement to cache (e.g. the trial failed)
    if trial.verdict != "ACCEPTED":
        return  # e.g. TIMEOUT/VERIFIER_ERROR placeholder -- nothing worth caching

    cache_fields = {**config.cache_fields, **_agent_cache_fields(trial_config, config)}
    cache_key = baseline_cache_key(cache_fields)
    write_baseline_trial(baseline_cache_root, config.instance_id, cache_key, trial)
    logger.info(
        "Wrote baseline cache: instance=%s trial=%s key=%s",
        config.instance_id,
        trial_result.trial_name,
        cache_key[:12],
    )


def _agent_cache_fields(trial_config: TrialConfig, config: PerfRaceConfig) -> dict[str, Any]:
    """Extra cache-key fields a cacheable agent contributes beyond the task itself.

    ``nop`` needs none: its output only depends on the task. ``PatchAgent``'s
    output additionally depends on which patch got applied, so its own patch
    file's content digest is folded in -- otherwise two different
    submissions' patches for the same task would collide on one cache entry.
    """
    fields: dict[str, Any] = {}
    if has_performance_profile(trial_config.environment):
        fields["performance_profile"] = True

    patches_by_instance = trial_config.agent.kwargs.get("patches_by_instance")
    if not isinstance(patches_by_instance, dict):
        return fields

    patch_path = patches_by_instance.get(config.instance_id)
    if patch_path is None:
        return fields
    digest = hashlib.sha256(Path(patch_path).read_bytes()).hexdigest()
    fields["patch_digest"] = digest
    return fields
