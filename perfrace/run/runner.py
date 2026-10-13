"""Execute PerfRace runs through Harbor.

Prepares baseline and optional patch agents, manages run-scoped services, and
runs PerfRaceJob with the official verifier. The report module pairs baseline
and candidate measurements and writes the resulting run artifacts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from harbor.models.job.config import JobConfig
from harbor.models.trial.config import AgentConfig

from perfrace.run.cache import baseline_cache_root
from perfrace.run.config import LoadedRun, RunConfigError
from perfrace.run.job import PerfRaceJob
from perfrace.run.profiling import add_job_performance_profile
from perfrace.run.report import NOP_AGENT_NAME, write_run_artifacts
from perfrace.run.services.gateway import run_gateway
from perfrace.run.submission import load_submission_patches

if TYPE_CHECKING:
    from harbor.models.job.result import JobResult

logger = logging.getLogger(__name__)

PERFRACE_VERIFIER_IMPORT_PATH = "perfrace.run.verifier:PerfRaceVerifier"
PATCH_AGENT_IMPORT_PATH = "perfrace.installed.patch:PatchAgent"


def run(loaded: LoadedRun) -> int:
    """Execute a loaded PerfRace run through Harbor and return a process exit code."""
    with run_gateway(loaded.api_gateway) as verifier_kwargs:
        return execute(loaded, verifier_kwargs=verifier_kwargs)


def execute(loaded: LoadedRun, *, verifier_kwargs: dict | None = None) -> int:
    """Run with caller-owned services, allowing multi-stage experiments to share them."""
    verifier_kwargs = verifier_kwargs or {}
    job_config = _prepare_job(loaded)
    logger.info(
        "Starting job: job_name=%s tasks=%d agents=%d (%s)",
        job_config.job_name,
        len(job_config.tasks) + len(job_config.datasets),
        len(job_config.agents),
        ", ".join(agent.name or agent.import_path or "?" for agent in job_config.agents),
    )

    # Wire PerfRaceVerifier in via Harbor's native VerifierConfig.import_path/.kwargs.
    # Merge (gateway-injected keys win on conflict), not overwrite: a
    # run's own config.yaml may already declare its own kwargs (e.g.
    # [verifier].kwargs.max_concurrent_shadows) that must survive
    # alongside whatever run_gateway() injects.
    wired_job_config = job_config.model_copy(
        update={
            "verifier": job_config.verifier.model_copy(
                update={
                    "import_path": PERFRACE_VERIFIER_IMPORT_PATH,
                    "kwargs": {**job_config.verifier.kwargs, **verifier_kwargs},
                }
            )
        }
    )
    result = asyncio.run(_create_and_run_job(loaded, wired_job_config))
    logger.info(
        "Job finished: job_name=%s trials=%d errored=%d",
        job_config.job_name,
        len(result.trial_results),
        result.stats.n_errored_trials,
    )
    write_run_artifacts(loaded, job_config, result)
    return 1 if result.stats.n_errored_trials else 0


async def _create_and_run_job(loaded: LoadedRun, wired_job_config: JobConfig) -> "JobResult":
    job = await PerfRaceJob.create(
        wired_job_config,
        enable_cache=loaded.enable_cache,
        baseline_cache_root=baseline_cache_root(wired_job_config.jobs_dir),
        host_resources_enabled=loaded.host_resources.enabled,
        host_resource_lock_dir=loaded.host_resources.lock_dir,
        trial_cpu_leases=loaded.host_resources.trial_cpu_leases,
        trial_process_isolation=loaded.host_resources.trial_process_isolation,
        trial_controller_memory_mb=loaded.host_resources.trial_controller_memory_mb,
    )
    return await job.run()


def _prepare_job(loaded: LoadedRun) -> JobConfig:
    """Prepend the unconditional nop baseline agent (and PatchAgent, if configured).

    Every run measures the pristine workspace via ``nop`` regardless of which
    candidate agent(s) the user configured (zero, one, or more): Harbor's own
    ``Job._init_trial_configs()`` already produces one nop (baseline) trial
    plus one trial per candidate agent per task, with no additional
    PerfRace-side orchestration needed for the cross product.
    ``scale_with_attempts=False`` keeps ``n_attempts > 1`` (requested to
    measure a candidate agent's variance) from also multiplying redundant nop
    baseline trials. When ``submission_path`` is set (``--patch``),
    ``PatchAgent`` is injected the same way -- a distinct per-trial agent
    identity is what lets the same task's nop and patched trials coexist in
    one job without the verifier having to tell them apart. Both are also
    ``cacheable=True``: their output is deterministic given the task (and,
    for ``PatchAgent``, the patch content), unlike a real candidate agent
    whose measurement is the thing being evaluated and must always be fresh.
    """
    agents = [AgentConfig(name=NOP_AGENT_NAME, scale_with_attempts=False, cacheable=True)]
    if loaded.submission_path is not None:
        agents.append(_patch_agent_config(loaded))
    agents.extend(loaded.job.agents)
    job = loaded.job.model_copy(update={"agents": agents})
    if loaded.performance_profile is None:
        return job
    try:
        return add_job_performance_profile(job)
    except OSError as exc:
        raise RunConfigError(str(exc)) from exc


def _patch_agent_config(loaded: LoadedRun) -> AgentConfig:
    """Build the patch agent configuration from the loaded submission."""
    assert loaded.submission_path is not None
    patches = load_submission_patches(
        loaded.submission_path,
        job_dir=loaded.job.jobs_dir / loaded.job.job_name,
    )
    return AgentConfig(
        import_path=PATCH_AGENT_IMPORT_PATH,
        scale_with_attempts=False,
        cacheable=True,
        kwargs={
            "patches_by_instance": {
                instance_id: str(path) for instance_id, path in patches.items()
            }
        },
    )
