"""Build generation-specific PerfRace jobs from one reusable run template."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from harbor.models.trial.config import AgentConfig, TaskConfig

from perfrace.evolution.config import HarnessEvolutionConfig
from perfrace.evolution.types import ValidationCandidateSpec
from perfrace.run.config import LoadedRun, load_run


OFFLINE_AGENT_IMPORT_PATH = "perfrace.installed.evolved:EvolvedHarnessAgent"


def validation_agent_name(generation: int) -> str:
    """Return the stable report identity for one Validation generation."""
    if generation < 0:
        raise ValueError("Validation generation cannot be negative")
    return f"offline-harness-h{generation}"


def _offline_agent_config(
    config: HarnessEvolutionConfig,
    *,
    template: AgentConfig,
    name: str | None,
    harness_source: Path,
    harness_identity: str,
    timeout_sec: int,
) -> AgentConfig:
    """Materialize one frozen-runtime agent from the reusable template."""
    agent_payload = template.model_dump(mode="python")
    agent_payload.update(
        {
            "name": name,
            "import_path": OFFLINE_AGENT_IMPORT_PATH,
            "model_name": config.model_name,
            "task_budget_sec": timeout_sec,
            "override_timeout_sec": timeout_sec,
            "cacheable": False,
            "scale_with_attempts": True,
            "kwargs": {
                **template.kwargs,
                "harness_source": str(harness_source),
                "harness_identity": harness_identity,
                "reasoning_effort": config.protocol.reasoning_effort,
            },
        }
    )
    return AgentConfig.model_validate(agent_payload)


def _canonical_json_value(value: Any) -> Any:
    """Convert resolved config values to deterministic JSON-compatible values."""
    if isinstance(value, dict):
        return {
            str(key): _canonical_json_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_json_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported resolved run config value: {type(value).__name__}")


def resolved_run_config_sha256(path: Path) -> str:
    """Hash the canonical fully resolved reusable run template."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    job = raw.get("job") if isinstance(raw, dict) else None
    if not isinstance(job, dict) or not isinstance(job.get("job_name"), str):
        raise ValueError("Harness evolution base run config must define job.job_name")
    loaded = load_run(path)
    payload = json.dumps(
        _canonical_json_value(
            {
                "job": loaded.job.model_dump(mode="python"),
                "api_gateway": (
                    loaded.api_gateway.model_dump(mode="python")
                    if loaded.api_gateway is not None
                    else None
                ),
                "submission_path": loaded.submission_path,
                "enable_cache": loaded.enable_cache,
                "host_resources": loaded.host_resources.model_dump(mode="python"),
                "note": loaded.note,
                "agent_tag": loaded.agent_tag,
            }
        ),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def build_baseline_run(
    config: HarnessEvolutionConfig,
    *,
    task_ids: tuple[str, ...],
    n_concurrent_trials: int,
    jobs_dir: Path,
    job_name: str,
) -> LoadedRun:
    """Build the mandatory fresh nop-only baseline campaign."""
    base = load_run(config.base_run_config)
    if not base.enable_cache:
        raise ValueError("Harness evolution baseline requires enable_cache: true")
    task_configs: list[TaskConfig] = []
    for task_id in task_ids:
        task_path = config.instance_root / task_id
        if not task_path.is_dir():
            raise ValueError(f"Installed PerfRace instance is missing: {task_path}")
        task_configs.append(TaskConfig(path=task_path))
    job = base.job.model_copy(
        update={
            "job_name": job_name,
            "jobs_dir": jobs_dir,
            "n_attempts": 1,
            "n_concurrent_trials": n_concurrent_trials,
            "tasks": task_configs,
            "datasets": [],
            "agents": [],
        }
    )
    gateway = (
        base.api_gateway.model_copy(update={"log_dir": jobs_dir / job_name})
        if base.api_gateway is not None
        else None
    )
    return replace(
        base,
        job=job,
        api_gateway=gateway,
        note=f"Offline harness evolution baseline {job_name}.",
        agent_tag="nop-baseline",
    )


def build_stage_run(
    config: HarnessEvolutionConfig,
    *,
    task_ids: tuple[str, ...],
    harness_source: Path,
    harness_identity: str,
    attempts: int,
    timeout_sec: int,
    n_concurrent_trials: int,
    jobs_dir: Path,
    job_name: str,
) -> LoadedRun:
    """Build one train, validation, or frozen test run for a committed runtime snapshot."""
    base = load_run(config.base_run_config)
    if len(base.job.agents) != 1:
        raise ValueError("Harness evolution base run config must define one agent template")
    template = base.job.agents[0]
    agent = _offline_agent_config(
        config,
        template=template,
        name=None,
        harness_source=harness_source,
        harness_identity=harness_identity,
        timeout_sec=timeout_sec,
    )
    task_configs: list[TaskConfig] = []
    for task_id in task_ids:
        task_path = config.instance_root / task_id
        if not task_path.is_dir():
            raise ValueError(f"Installed PerfRace instance is missing: {task_path}")
        task_configs.append(TaskConfig(path=task_path))
    job = base.job.model_copy(
        update={
            "job_name": job_name,
            "jobs_dir": jobs_dir,
            "n_attempts": attempts,
            "n_concurrent_trials": n_concurrent_trials,
            "tasks": task_configs,
            "datasets": [],
            "agents": [agent],
        }
    )
    gateway = (
        base.api_gateway.model_copy(update={"log_dir": jobs_dir / job_name})
        if base.api_gateway is not None
        else None
    )
    return replace(
        base,
        job=job,
        api_gateway=gateway,
        note=f"Offline harness evolution stage {job_name}.",
        agent_tag=f"offline-harness-{harness_identity[:12]}",
    )


def build_validation_run(
    config: HarnessEvolutionConfig,
    *,
    task_ids: tuple[str, ...],
    candidates: tuple[ValidationCandidateSpec, ...],
    attempts: int,
    timeout_sec: int,
    n_concurrent_trials: int,
    jobs_dir: Path,
    job_name: str,
) -> LoadedRun:
    """Build one globally capped Validation job containing every frozen runtime."""
    base = load_run(config.base_run_config)
    if len(base.job.agents) != 1:
        raise ValueError("Harness evolution base run config must define one agent template")
    template = base.job.agents[0]
    agents = [
        _offline_agent_config(
            config,
            template=template,
            name=candidate.agent_name,
            harness_source=candidate.harness_source,
            harness_identity=candidate.harness_identity,
            timeout_sec=timeout_sec,
        )
        for candidate in candidates
    ]
    task_configs: list[TaskConfig] = []
    for task_id in task_ids:
        task_path = config.instance_root / task_id
        if not task_path.is_dir():
            raise ValueError(f"Installed PerfRace instance is missing: {task_path}")
        task_configs.append(TaskConfig(path=task_path))
    job = base.job.model_copy(
        update={
            "job_name": job_name,
            "jobs_dir": jobs_dir,
            "n_attempts": attempts,
            "n_concurrent_trials": n_concurrent_trials,
            "tasks": task_configs,
            "datasets": [],
            "agents": agents,
        }
    )
    gateway = (
        base.api_gateway.model_copy(update={"log_dir": jobs_dir / job_name})
        if base.api_gateway is not None
        else None
    )
    return replace(
        base,
        job=job,
        api_gateway=gateway,
        note=f"Offline harness evolution global Validation {job_name}.",
        agent_tag="offline-harness-validation-global",
    )
