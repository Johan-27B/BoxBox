"""Execute train and validation stages through the native PerfRace runner."""

from __future__ import annotations
import argparse
import hashlib
import shlex
from pathlib import Path
from typing import Literal

import yaml

from perfrace.evolution.config import (
    HarnessEvolutionConfig,
    load_harness_evolution_config,
)
from perfrace.evolution.job_builder import (
    build_baseline_run,
    build_stage_run,
    build_validation_run,
    resolved_run_config_sha256,
)
from perfrace.evolution.planning import (
    controller_source_sha256,
    resolve_evolution_plan,
)
from perfrace.evolution.paths import HarnessEvolutionPaths
from perfrace.evolution.scoring import aggregate_run_summary
from perfrace.evolution.runtime_repository import hash_source_tree
from perfrace.evolution.state import (
    read_model,
    write_model_atomic,
    write_text_atomic,
)
from perfrace.evolution.types import (
    AggregateScore,
    BaselineSpec,
    EvolutionStage,
    EvolutionState,
    FrozenTestSpec,
    GenerationRecord,
    ResolvedEvolutionPlan,
    SelectionRecord,
    StageSpec,
    TrainBatch,
    ValidationCampaignSpec,
    ValidationCandidateSpec,
)
from perfrace.run.cache import baseline_cache_key, baseline_cache_root, read_baseline_trial
from perfrace.run.config import load_run
from perfrace.run.report import RunPaths
from perfrace.run.runner import execute
from perfrace.run.services.gateway import run_gateway
from perfrace.run.types import Measurement, PerfRaceConfig, RunSummary, RunTrialSummary


def _artifact_matches(run_dir: Path, trial: RunTrialSummary) -> bool:
    """Validate one referenced measurement artifact against its summary value."""
    if trial.perf_trial is None:
        return False
    artifact = (run_dir / trial.artifact).resolve()
    if not artifact.is_relative_to(run_dir.resolve()) or not artifact.is_file():
        return False
    try:
        measurement = Measurement.model_validate_json(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return measurement == trial.perf_trial


def _is_complete_summary(
    path: Path,
    *,
    job_name: str,
    expected_task_names: set[str],
    attempts: int,
    harness_identity: str,
    timeout_sec: int,
    n_concurrent_trials: int,
) -> bool:
    """Return whether one run summary exactly matches a complete stage."""
    try:
        summary = RunSummary.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    try:
        job = yaml.safe_load(path.with_name("job.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return False
    agents = job.get("agents") if isinstance(job, dict) else None
    matching_agents = (
        [
            agent
            for agent in agents
            if isinstance(agent, dict)
            and agent.get("import_path")
            == "perfrace.installed.evolved:EvolvedHarnessAgent"
            and isinstance(agent.get("kwargs"), dict)
            and agent["kwargs"].get("harness_identity") == harness_identity
        ]
        if isinstance(agents, list)
        else []
    )
    candidate = matching_agents[0] if len(matching_agents) == 1 else None
    nop_agents = (
        [agent for agent in agents if isinstance(agent, dict) and agent.get("name") == "nop"]
        if isinstance(agents, list)
        else []
    )
    return (
        summary.job_name == job_name
        and isinstance(job, dict)
        and job.get("n_attempts") == attempts
        and job.get("n_concurrent_trials") == n_concurrent_trials
        and len(nop_agents) == 1
        and len(agents) == 2
        and candidate is not None
        and candidate.get("task_budget_sec") == timeout_sec
        and candidate.get("override_timeout_sec") == timeout_sec
        and summary.stats.get("n_errored_trials", 0) == 0
        and summary.trial_count == len(expected_task_names) * (attempts + 1)
        and {task.task_name for task in summary.tasks} == expected_task_names
        and len(matching_agents) == 1
        and all(
            task.baseline is not None
            and task.baseline.perf_trial is not None
            and _artifact_matches(path.parent, task.baseline)
            and len(task.candidates) == attempts
            and all(
                candidate.agent == "offline-harness"
                and candidate.reward is not None
                and _artifact_matches(path.parent, candidate)
                for candidate in task.candidates
            )
            for task in summary.tasks
        )
    )


def find_complete_summary(
    *,
    jobs_dir: Path,
    job_name: str,
    expected_task_names: set[str],
    attempts: int,
    harness_identity: str,
    timeout_sec: int,
    n_concurrent_trials: int,
) -> Path | None:
    """Return the first exact complete base or recovery run summary."""
    names = [job_name]
    if jobs_dir.is_dir():
        names.extend(
            sorted(path.name for path in jobs_dir.glob(f"{job_name}-recovery-*") if path.is_dir())
        )
    for name in dict.fromkeys(names):
        path = RunPaths(jobs_dir=jobs_dir, job_name=name).summary_path
        if _is_complete_summary(
            path,
            job_name=name,
            expected_task_names=expected_task_names,
            attempts=attempts,
            harness_identity=harness_identity,
            timeout_sec=timeout_sec,
            n_concurrent_trials=n_concurrent_trials,
        ):
            return path
    return None


def _is_complete_validation_summary(
    path: Path,
    *,
    spec: ValidationCampaignSpec,
    expected_task_names: set[str],
) -> bool:
    """Return whether one multi-agent Validation summary exactly matches its campaign."""
    try:
        summary = RunSummary.model_validate_json(path.read_text(encoding="utf-8"))
        job = yaml.safe_load(path.with_name("job.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        return False
    agents = job.get("agents") if isinstance(job, dict) else None
    if not isinstance(agents, list):
        return False
    nop_agents = [
        agent for agent in agents if isinstance(agent, dict) and agent.get("name") == "nop"
    ]
    candidate_agents = {
        agent.get("name"): agent
        for agent in agents
        if isinstance(agent, dict)
        and agent.get("import_path") == "perfrace.installed.evolved:EvolvedHarnessAgent"
    }
    expected_agents = {candidate.agent_name: candidate for candidate in spec.candidates}
    if (
        summary.job_name != spec.job_name
        or job.get("n_attempts") != spec.attempts
        or job.get("n_concurrent_trials") != spec.n_concurrent_trials
        or len(nop_agents) != 1
        or set(candidate_agents) != set(expected_agents)
        or len(agents) != len(expected_agents) + 1
        or summary.stats.get("n_errored_trials", 0) != 0
        or summary.trial_count
        != len(expected_task_names) * (1 + len(expected_agents) * spec.attempts)
        or {task.task_name for task in summary.tasks} != expected_task_names
    ):
        return False
    for agent_name, expected in expected_agents.items():
        agent = candidate_agents[agent_name]
        kwargs = agent.get("kwargs")
        if not (
            agent.get("task_budget_sec") == spec.timeout_sec
            and agent.get("override_timeout_sec") == spec.timeout_sec
            and isinstance(kwargs, dict)
            and kwargs.get("harness_identity") == expected.harness_identity
            and Path(kwargs.get("harness_source", "")).resolve()
            == expected.harness_source.resolve()
        ):
            return False
    for task in summary.tasks:
        if (
            task.baseline is None
            or task.baseline.perf_trial is None
            or not _artifact_matches(path.parent, task.baseline)
        ):
            return False
        candidates_by_agent = {
            agent_name: [
                candidate for candidate in task.candidates if candidate.agent == agent_name
            ]
            for agent_name in expected_agents
        }
        if len(task.candidates) != len(expected_agents) * spec.attempts or any(
            len(candidates) != spec.attempts
            or any(
                candidate.reward is None or not _artifact_matches(path.parent, candidate)
                for candidate in candidates
            )
            for candidates in candidates_by_agent.values()
        ):
            return False
    return True


def find_complete_validation_summary(
    *,
    jobs_dir: Path,
    spec: ValidationCampaignSpec,
    expected_task_names: set[str],
) -> Path | None:
    """Return the first exact complete global Validation summary."""
    names = [spec.job_name]
    if jobs_dir.is_dir():
        names.extend(
            sorted(
                path.name for path in jobs_dir.glob(f"{spec.job_name}-recovery-*") if path.is_dir()
            )
        )
    for name in dict.fromkeys(names):
        path = RunPaths(jobs_dir=jobs_dir, job_name=name).summary_path
        effective_spec = spec.model_copy(update={"job_name": name})
        if _is_complete_validation_summary(
            path,
            spec=effective_spec,
            expected_task_names=expected_task_names,
        ):
            return path
    return None


def _baseline_task_configs(
    config: HarnessEvolutionConfig,
    task_ids: tuple[str, ...],
) -> dict[str, PerfRaceConfig]:
    task_configs: dict[str, PerfRaceConfig] = {}
    for task_id in task_ids:
        task = PerfRaceConfig.from_task_dir(
            config.instance_root / task_id,
            include_checksum=True,
        )
        if task is None or task.task_checksum is None or task.cache_fields is None:
            raise ValueError(f"Installed PerfRace instance cannot be baselined: {task_id}")
        if task.task_name in task_configs:
            raise ValueError(f"Duplicate PerfRace task name: {task.task_name}")
        task_configs[task.task_name] = task
    return task_configs


def _is_complete_baseline_summary(
    path: Path,
    *,
    job_name: str,
    expected_configs: dict[str, PerfRaceConfig],
    n_concurrent_trials: int,
) -> bool:
    try:
        summary = RunSummary.model_validate_json(path.read_text(encoding="utf-8"))
        job = yaml.safe_load(path.with_name("job.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        return False
    agents = job.get("agents") if isinstance(job, dict) else None
    if not (
        summary.job_name == job_name
        and summary.enable_cache
        and summary.stats.get("n_errored_trials", 0) == 0
        and summary.trial_count == len(expected_configs)
        and {task.task_name for task in summary.tasks} == set(expected_configs)
        and isinstance(job, dict)
        and job.get("n_concurrent_trials") == n_concurrent_trials
        and isinstance(agents, list)
        and len(agents) == 1
        and isinstance(agents[0], dict)
        and agents[0].get("name") == "nop"
    ):
        return False
    for task_summary in summary.tasks:
        task = expected_configs[task_summary.task_name]
        baseline = task_summary.baseline
        measurement = baseline.perf_trial if baseline is not None else None
        if (
            task.measurement is None
            or baseline is None
            or baseline.agent != "nop"
            or measurement is None
            or measurement.verdict != "ACCEPTED"
            or measurement.value is None
            or float(measurement.value) <= 0
            or measurement.metric != task.measurement.measurement
            or measurement.unit != task.measurement.unit
            or task_summary.candidates
            or not _artifact_matches(path.parent, baseline)
        ):
            return False
    return True


def _baseline_cache_is_complete(
    jobs_dir: Path,
    expected_configs: dict[str, PerfRaceConfig],
    summary_path: Path,
) -> bool:
    summary = RunSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    measurements = {
        task.task_name: task.baseline.perf_trial
        for task in summary.tasks
        if task.baseline is not None
    }
    cache_root = baseline_cache_root(jobs_dir)
    for task_name, task in expected_configs.items():
        assert task.cache_fields is not None
        cached = read_baseline_trial(
            cache_root,
            task.instance_id,
            baseline_cache_key(task.cache_fields),
        )
        if cached is None or cached != measurements.get(task_name):
            return False
    return True


def find_complete_baseline_summary(
    *,
    jobs_dir: Path,
    job_name: str,
    expected_configs: dict[str, PerfRaceConfig],
    n_concurrent_trials: int,
) -> Path | None:
    """Return a complete accepted nop-only run with a matching shared cache."""
    names = [job_name]
    if jobs_dir.is_dir():
        names.extend(
            sorted(path.name for path in jobs_dir.glob(f"{job_name}-recovery-*") if path.is_dir())
        )
    for name in dict.fromkeys(names):
        path = RunPaths(jobs_dir=jobs_dir, job_name=name).summary_path
        if _is_complete_baseline_summary(
            path,
            job_name=name,
            expected_configs=expected_configs,
            n_concurrent_trials=n_concurrent_trials,
        ) and _baseline_cache_is_complete(jobs_dir, expected_configs, path):
            return path
    return None


def execute_baseline(
    config: HarnessEvolutionConfig,
    *,
    task_ids: tuple[str, ...],
    n_concurrent_trials: int,
    stage_dir: Path,
    job_name: str,
    jobs_dir: Path,
    verifier_kwargs: dict[str, object] | None = None,
) -> Path:
    """Run and validate the mandatory fresh nop baseline campaign."""
    task_configs = _baseline_task_configs(config, task_ids)
    spec = BaselineSpec(
        task_ids=task_ids,
        task_checksums={
            task_id: PerfRaceConfig.from_task_dir(
                config.instance_root / task_id, include_checksum=True
            ).task_checksum
            for task_id in task_ids
        },
        base_run_config_sha256=resolved_run_config_sha256(config.base_run_config),
        controller_source_sha256=controller_source_sha256(),
        n_concurrent_trials=n_concurrent_trials,
        job_name=job_name,
    )
    spec_path = stage_dir / "stage.json"
    if spec_path.is_file():
        if read_model(spec_path, BaselineSpec) != spec:
            raise ValueError(f"Existing baseline inputs do not match resume request: {stage_dir}")
    else:
        write_model_atomic(spec_path, spec)
    complete_summary = find_complete_baseline_summary(
        jobs_dir=jobs_dir,
        job_name=job_name,
        expected_configs=task_configs,
        n_concurrent_trials=n_concurrent_trials,
    )
    if complete_summary is not None:
        return complete_summary
    if not (jobs_dir / job_name).exists():
        effective_job_name = job_name
    else:
        recovery_index = 1
        while (jobs_dir / f"{job_name}-recovery-{recovery_index:02d}").exists():
            recovery_index += 1
        effective_job_name = f"{job_name}-recovery-{recovery_index:02d}"
    summary_path = RunPaths(jobs_dir=jobs_dir, job_name=effective_job_name).summary_path
    loaded = build_baseline_run(
        config,
        task_ids=task_ids,
        n_concurrent_trials=n_concurrent_trials,
        jobs_dir=jobs_dir,
        job_name=effective_job_name,
    )
    if verifier_kwargs is None:
        with run_gateway(loaded.api_gateway) as local_verifier_kwargs:
            exit_code = execute(loaded, verifier_kwargs=local_verifier_kwargs)
    else:
        exit_code = execute(loaded, verifier_kwargs=verifier_kwargs)
    if exit_code != 0:
        raise RuntimeError(f"PerfRace baseline failed: {effective_job_name}")
    if not (
        _is_complete_baseline_summary(
            summary_path,
            job_name=effective_job_name,
            expected_configs=task_configs,
            n_concurrent_trials=n_concurrent_trials,
        )
        and _baseline_cache_is_complete(jobs_dir, task_configs, summary_path)
    ):
        raise RuntimeError(
            f"PerfRace baseline is incomplete, rejected, or missing cache entries: {summary_path}"
        )
    return summary_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_locked_text(path: Path, text: str) -> None:
    """Write an immutable generated artifact or verify an identical resume."""
    if path.is_file():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Frozen test artifact changed on resume: {path}")
        return
    write_text_atomic(path, text)


def _run_yaml(loaded: object) -> str:
    payload = loaded.to_json_dict()
    for key in ("api_gateway", "submission_path", "note", "agent_tag"):
        if payload.get(key) is None:
            payload.pop(key, None)
    if api_gateway := payload.get("api_gateway"):
        api_gateway.pop("log_dir", None)
    return yaml.safe_dump(payload, sort_keys=False)


def _task_manifest_text(task_ids: tuple[str, ...]) -> str:
    return "".join(f"{task_id}\n" for task_id in task_ids)


def _test_job_exists(jobs_dir: Path, job_name: str) -> bool:
    return (jobs_dir / job_name).exists() or any(
        path.is_dir() for path in jobs_dir.glob(f"{job_name}-recovery-*")
    )


def generate_frozen_test_artifacts(
    *,
    config: HarnessEvolutionConfig,
    config_source_path: Path,
    config_source_sha256: str,
    plan: ResolvedEvolutionPlan,
    paths: HarnessEvolutionPaths,
    selection: SelectionRecord,
    selected_record: GenerationRecord,
) -> FrozenTestSpec:
    """Generate an identity-locked final-test bundle without executing it."""
    paths.test.mkdir(parents=True, exist_ok=True)
    if (paths.jobs / f"{config.experiment_name}-test-hstar").exists():
        raise ValueError("Final test job already exists before the protocol gate")
    manifest_text = _task_manifest_text(plan.split.test)
    _write_locked_text(paths.test_manifest, manifest_text)
    loaded = build_stage_run(
        config,
        task_ids=plan.split.test,
        harness_source=paths.frozen_runtime,
        harness_identity=selection.selected_commit,
        attempts=plan.test_attempts,
        timeout_sec=plan.test_timeout_sec,
        n_concurrent_trials=plan.test_concurrency,
        jobs_dir=paths.jobs,
        job_name=f"{config.experiment_name}-test-hstar",
    )
    _write_locked_text(paths.test_config, _run_yaml(loaded))
    spec = FrozenTestSpec(
        experiment_name=config.experiment_name,
        config_source_path=config_source_path.resolve(),
        config_source_sha256=config_source_sha256,
        base_run_config_sha256=plan.base_run_config_sha256,
        controller_source_sha256=plan.controller_source_sha256,
        model_name=config.model_name,
        reasoning_effort=config.protocol.reasoning_effort,
        selected_generation=selection.selected_generation,
        selected_commit=selection.selected_commit,
        selected_source_sha256=selected_record.source_sha256,
        selected_tree_sha256=hash_source_tree(paths.frozen_runtime),
        harness_source=paths.frozen_runtime.resolve(),
        task_ids=plan.split.test,
        task_checksums={task_id: plan.task_checksums[task_id] for task_id in plan.split.test},
        split_manifest_sha256=_sha256(paths.splits / "manifest.json"),
        test_manifest_sha256=_sha256(paths.test_manifest),
        run_config_sha256=_sha256(paths.test_config),
        attempts=plan.test_attempts,
        timeout_sec=plan.test_timeout_sec,
        n_concurrent_trials=plan.test_concurrency,
        job_name=f"{config.experiment_name}-test-hstar",
    )
    if paths.test_spec.is_file():
        if read_model(paths.test_spec, FrozenTestSpec) != spec:
            raise ValueError("Frozen test specification changed on resume")
    else:
        write_model_atomic(paths.test_spec, spec)
    config_argument = shlex.quote(str(config_source_path.resolve()))
    run_script = (
        """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPERIMENT_ROOT=$(dirname -- "$SCRIPT_DIR")
REPO_ROOT=${PERFRACE_REPO:-$(git rev-parse --show-toplevel)}
cd "$REPO_ROOT"
"""
        + f"uv run --extra evolution perfrace evolve-harness --config {config_argument} --resume\n"
        + """uv run --extra evolution python -m perfrace.evolution.execution validate-test --require-unrun --experiment-root "$EXPERIMENT_ROOT"
exec uv run --extra evolution perfrace run --config "$SCRIPT_DIR/offline-hstar.yaml"
"""
    )
    score_script = """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPERIMENT_ROOT=$(dirname -- "$SCRIPT_DIR")
REPO_ROOT=${PERFRACE_REPO:-$(git rev-parse --show-toplevel)}
cd "$REPO_ROOT"
uv run --extra evolution python -m perfrace.evolution.execution score-test --experiment-root "$EXPERIMENT_ROOT"
"""
    _write_locked_text(paths.test_run_script, run_script)
    _write_locked_text(paths.test_score_script, score_script)
    paths.test_run_script.chmod(0o755)
    paths.test_score_script.chmod(0o755)
    return spec


def validate_frozen_test_artifacts(
    experiment_root: Path,
    *,
    require_unrun: bool = False,
) -> FrozenTestSpec:
    """Validate the selected runtime and every generated final-test identity."""
    root = experiment_root.expanduser().resolve()
    paths = HarnessEvolutionPaths(root.parent, root.name)
    plan = read_model(paths.resolved_config, ResolvedEvolutionPlan)
    state = read_model(paths.state, EvolutionState)
    selection = read_model(paths.selection, SelectionRecord)
    marker = read_model(paths.frozen_runtime_marker, GenerationRecord)
    spec = read_model(paths.test_spec, FrozenTestSpec)
    if (
        state.experiment_name != spec.experiment_name
        or state.config_sha256 != spec.config_source_sha256
        or _sha256(spec.config_source_path) != spec.config_source_sha256
    ):
        raise ValueError("Frozen test source config identity changed")
    source = load_harness_evolution_config(spec.config_source_path)
    if (
        source.source_sha256 != spec.config_source_sha256
        or source.config.experiment_name != spec.experiment_name
        or HarnessEvolutionPaths(
            source.config.artifact_root, source.config.experiment_name
        ).root.resolve()
        != root
        or resolve_evolution_plan(source) != plan
    ):
        raise ValueError("Frozen test source inputs no longer resolve to the recorded plan")
    if state.stage not in {EvolutionStage.TEST_READY, EvolutionStage.COMPLETE}:
        raise ValueError(f"Experiment has not reached the final-test gate: {state.stage}")
    if state.selection_path != paths.selection:
        raise ValueError("Experiment state does not point to the frozen selection")
    if (
        selection.selected_generation != marker.generation
        or selection.selected_commit != marker.commit
        or marker.source_sha256 != spec.selected_source_sha256
        or selection.selected_generation != spec.selected_generation
        or selection.selected_commit != spec.selected_commit
    ):
        raise ValueError("Frozen test runtime identity does not match selection")
    if (
        spec.experiment_name != plan.experiment_name
        or spec.task_ids != plan.split.test
        or spec.base_run_config_sha256 != plan.base_run_config_sha256
        or spec.controller_source_sha256 != plan.controller_source_sha256
        or spec.model_name != source.config.model_name
        or spec.reasoning_effort != source.config.protocol.reasoning_effort
        or spec.attempts != plan.test_attempts
        or spec.timeout_sec != plan.test_timeout_sec
        or spec.n_concurrent_trials != plan.test_concurrency
    ):
        raise ValueError("Frozen test specification does not match the resolved plan")
    if spec.task_checksums != {
        task_id: plan.task_checksums[task_id] for task_id in plan.split.test
    }:
        raise ValueError("Frozen test task checksums do not match the resolved plan")
    if spec.harness_source.resolve() != paths.frozen_runtime.resolve():
        raise ValueError("Frozen test runtime path is not the selected runtime")
    if hash_source_tree(paths.frozen_runtime) != spec.selected_tree_sha256:
        raise ValueError("Frozen test runtime source hash changed")
    if _sha256(paths.splits / "manifest.json") != spec.split_manifest_sha256:
        raise ValueError("Split manifest changed after test generation")
    if _sha256(paths.test_manifest) != spec.test_manifest_sha256:
        raise ValueError("Test manifest changed after test generation")
    if tuple(paths.test_manifest.read_text(encoding="utf-8").splitlines()) != spec.task_ids:
        raise ValueError("Test manifest contents do not match the frozen test specification")
    if _sha256(paths.test_config) != spec.run_config_sha256:
        raise ValueError("Frozen test run config changed")
    loaded = load_run(paths.test_config)
    base = load_run(source.config.base_run_config)
    if (
        not loaded.enable_cache
        or loaded.submission_path is not None
        or loaded.host_resources != base.host_resources
        or loaded.job.job_name != spec.job_name
        or loaded.job.jobs_dir.resolve() != paths.jobs.resolve()
        or loaded.job.datasets
    ):
        raise ValueError("Frozen test run policy does not match the experiment")
    current_checksums: dict[str, str] = {}
    for task_id, task_entry in zip(spec.task_ids, loaded.job.tasks, strict=True):
        if task_entry.path.resolve() != (source.config.instance_root / task_id).resolve():
            raise ValueError("Frozen test task path does not match its manifest")
        task = PerfRaceConfig.from_task_dir(task_entry.path, include_checksum=True)
        if task is None or task.task_checksum is None:
            raise ValueError(f"Frozen test task cannot be validated: {task_id}")
        current_checksums[task_id] = task.task_checksum
    if current_checksums != spec.task_checksums:
        raise ValueError("Frozen test task content changed")
    if len(loaded.job.agents) != 1:
        raise ValueError("Frozen test config must contain exactly one candidate agent")
    agent = loaded.job.agents[0]
    if (
        agent.import_path != "perfrace.installed.evolved:EvolvedHarnessAgent"
        or agent.model_name != spec.model_name
        or agent.kwargs.get("reasoning_effort") != spec.reasoning_effort
        or agent.kwargs.get("harness_identity") != spec.selected_commit
        or Path(agent.kwargs.get("harness_source", "")).resolve() != spec.harness_source.resolve()
        or agent.task_budget_sec != spec.timeout_sec
        or loaded.job.n_attempts != spec.attempts
        or loaded.job.n_concurrent_trials != spec.n_concurrent_trials
        or tuple(task.path.name for task in loaded.job.tasks) != spec.task_ids
    ):
        raise ValueError("Frozen test run config does not match its identity lock")
    if agent.override_timeout_sec != spec.timeout_sec:
        raise ValueError("Frozen test timeout does not match its identity lock")
    if require_unrun and _test_job_exists(loaded.job.jobs_dir, spec.job_name):
        raise ValueError("Frozen final test has already been launched")
    return spec


def score_frozen_test(experiment_root: Path) -> AggregateScore:
    """Validate and score one manually launched frozen final-test run."""
    root = experiment_root.expanduser().resolve()
    paths = HarnessEvolutionPaths(root.parent, root.name)
    spec = validate_frozen_test_artifacts(root)
    loaded = load_run(paths.test_config)
    task_names = {
        task.task_name
        for task_config in loaded.job.tasks
        if (task := PerfRaceConfig.from_task_dir(task_config.path)) is not None
    }
    if len(task_names) != len(spec.task_ids):
        raise ValueError("Could not resolve every frozen test task name")
    summary_path = find_complete_summary(
        jobs_dir=loaded.job.jobs_dir,
        job_name=spec.job_name,
        expected_task_names=task_names,
        attempts=spec.attempts,
        harness_identity=spec.selected_commit,
        timeout_sec=spec.timeout_sec,
        n_concurrent_trials=spec.n_concurrent_trials,
    )
    if summary_path is None:
        raise ValueError("Frozen final test has no complete run summary")
    summary = RunSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    score = aggregate_run_summary(summary, expected_attempts=spec.attempts)
    write_model_atomic(paths.test / "score.json", score)
    lines = [
        "# Frozen Offline Harness Test",
        "",
        f"- Selected generation: h{spec.selected_generation}",
        f"- Selected commit: `{spec.selected_commit}`",
        f"- Tasks: {len(spec.task_ids)}",
        f"- Attempts per task: {spec.attempts}",
        f"- Official score: {score.official_score:.12g}",
        f"- Raw zero-sensitive score: {score.raw_zero_sensitive_score:.12g}",
        f"- Run summary: `{summary_path}`",
        "",
    ]
    write_text_atomic(paths.test / "summary.md", "\n".join(lines))
    return score


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate or score a frozen harness test.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate-test")
    validate_parser.add_argument("--experiment-root", type=Path, required=True)
    validate_parser.add_argument("--require-unrun", action="store_true")
    score_parser = subparsers.add_parser("score-test")
    score_parser.add_argument("--experiment-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-test":
        validate_frozen_test_artifacts(args.experiment_root, require_unrun=args.require_unrun)
    else:
        score_frozen_test(args.experiment_root)
    return 0


def execute_validation_campaign(
    config: HarnessEvolutionConfig,
    *,
    candidates: tuple[ValidationCandidateSpec, ...],
    task_ids: tuple[str, ...],
    attempts: int,
    timeout_sec: int,
    n_concurrent_trials: int,
    stage_dir: Path,
    job_name: str,
    jobs_dir: Path,
    verifier_kwargs: dict[str, object] | None = None,
) -> Path:
    """Run all frozen Validation generations through one globally capped job."""
    task_checksums: dict[str, str] = {}
    expected_task_names: set[str] = set()
    for task_id in task_ids:
        task_config = PerfRaceConfig.from_task_dir(
            config.instance_root / task_id,
            include_checksum=True,
        )
        if task_config is None or task_config.task_checksum is None:
            raise ValueError(f"Installed PerfRace instance has no usable checksum: {task_id}")
        task_checksums[task_id] = task_config.task_checksum
        expected_task_names.add(task_config.task_name)
    for candidate in candidates:
        if hash_source_tree(candidate.harness_source) != candidate.harness_source_sha256:
            raise ValueError(
                f"Validation runtime source changed for generation {candidate.generation}"
            )
    spec = ValidationCampaignSpec(
        candidates=candidates,
        task_ids=task_ids,
        task_checksums=task_checksums,
        base_run_config_sha256=resolved_run_config_sha256(config.base_run_config),
        controller_source_sha256=controller_source_sha256(),
        attempts=attempts,
        timeout_sec=timeout_sec,
        n_concurrent_trials=n_concurrent_trials,
        effective_concurrency=min(
            n_concurrent_trials,
            len(candidates) * len(task_ids) * attempts,
        ),
        job_name=job_name,
    )
    spec_path = stage_dir / "stage.json"
    if spec_path.is_file():
        if read_model(spec_path, ValidationCampaignSpec) != spec:
            raise ValueError(
                f"Existing Validation inputs do not match resume request: {stage_dir}"
            )
    else:
        write_model_atomic(spec_path, spec)
    complete_summary = find_complete_validation_summary(
        jobs_dir=jobs_dir,
        spec=spec,
        expected_task_names=expected_task_names,
    )
    if complete_summary is not None:
        return complete_summary
    if not (jobs_dir / job_name).exists():
        effective_job_name = job_name
    else:
        recovery_index = 1
        while (jobs_dir / f"{job_name}-recovery-{recovery_index:02d}").exists():
            recovery_index += 1
        effective_job_name = f"{job_name}-recovery-{recovery_index:02d}"
    summary_path = RunPaths(jobs_dir=jobs_dir, job_name=effective_job_name).summary_path
    loaded = build_validation_run(
        config,
        task_ids=task_ids,
        candidates=candidates,
        attempts=attempts,
        timeout_sec=timeout_sec,
        n_concurrent_trials=n_concurrent_trials,
        jobs_dir=jobs_dir,
        job_name=effective_job_name,
    )
    if verifier_kwargs is None:
        with run_gateway(loaded.api_gateway) as local_verifier_kwargs:
            exit_code = execute(loaded, verifier_kwargs=local_verifier_kwargs)
    else:
        exit_code = execute(loaded, verifier_kwargs=verifier_kwargs)
    if exit_code != 0:
        raise RuntimeError(f"PerfRace Validation failed: {effective_job_name}")
    effective_spec = spec.model_copy(update={"job_name": effective_job_name})
    if not _is_complete_validation_summary(
        summary_path,
        spec=effective_spec,
        expected_task_names=expected_task_names,
    ):
        raise RuntimeError(f"PerfRace Validation did not write a complete summary: {summary_path}")
    return summary_path


def execute_stage(
    config: HarnessEvolutionConfig,
    *,
    stage: Literal["train", "validation"],
    iteration: int,
    generation: int,
    train_batch: TrainBatch | None,
    train_schedule_sha256: str | None,
    task_ids: tuple[str, ...],
    harness_source: Path,
    harness_identity: str,
    attempts: int,
    timeout_sec: int,
    n_concurrent_trials: int,
    stage_dir: Path,
    job_name: str,
    jobs_dir: Path | None = None,
    verifier_kwargs: dict[str, object] | None = None,
) -> Path:
    """Run one complete stage and return its standard `run.json` path."""
    task_checksums: dict[str, str] = {}
    expected_task_names: set[str] = set()
    for task_id in task_ids:
        task_config = PerfRaceConfig.from_task_dir(
            config.instance_root / task_id,
            include_checksum=True,
        )
        if task_config is None or task_config.task_checksum is None:
            raise ValueError(f"Installed PerfRace instance has no usable checksum: {task_id}")
        task_checksums[task_id] = task_config.task_checksum
        expected_task_names.add(task_config.task_name)
    spec = StageSpec(
        stage=stage,
        iteration=iteration,
        generation=generation,
        epoch=train_batch.epoch if train_batch is not None else None,
        batch_index=train_batch.batch_index if train_batch is not None else None,
        train_schedule_sha256=train_schedule_sha256,
        task_ids=task_ids,
        task_checksums=task_checksums,
        harness_identity=harness_identity,
        harness_source_sha256=hash_source_tree(harness_source),
        base_run_config_sha256=resolved_run_config_sha256(config.base_run_config),
        controller_source_sha256=controller_source_sha256(),
        attempts=attempts,
        timeout_sec=timeout_sec,
        n_concurrent_trials=n_concurrent_trials,
        effective_concurrency=min(n_concurrent_trials, len(task_ids) * attempts),
        job_name=job_name,
    )
    spec_path = stage_dir / "stage.json"
    if spec_path.is_file():
        if read_model(spec_path, StageSpec) != spec:
            raise ValueError(f"Existing stage inputs do not match resume request: {stage_dir}")
    else:
        write_model_atomic(spec_path, spec)
    jobs_dir = jobs_dir or stage_dir / "jobs"
    complete_summary = find_complete_summary(
        jobs_dir=jobs_dir,
        job_name=job_name,
        expected_task_names=expected_task_names,
        attempts=attempts,
        harness_identity=harness_identity,
        timeout_sec=timeout_sec,
        n_concurrent_trials=n_concurrent_trials,
    )
    if complete_summary is not None:
        return complete_summary
    if not (jobs_dir / job_name).exists():
        effective_job_name = job_name
    else:
        recovery_index = 1
        while (jobs_dir / f"{job_name}-recovery-{recovery_index:02d}").exists():
            recovery_index += 1
        effective_job_name = f"{job_name}-recovery-{recovery_index:02d}"
    summary_path = RunPaths(
        jobs_dir=jobs_dir,
        job_name=effective_job_name,
    ).summary_path
    loaded = build_stage_run(
        config,
        task_ids=task_ids,
        harness_source=harness_source,
        harness_identity=harness_identity,
        attempts=attempts,
        timeout_sec=timeout_sec,
        n_concurrent_trials=n_concurrent_trials,
        jobs_dir=jobs_dir,
        job_name=effective_job_name,
    )
    if verifier_kwargs is None:
        with run_gateway(loaded.api_gateway) as local_verifier_kwargs:
            exit_code = execute(loaded, verifier_kwargs=local_verifier_kwargs)
    else:
        exit_code = execute(loaded, verifier_kwargs=verifier_kwargs)
    if exit_code != 0:
        raise RuntimeError(f"PerfRace stage failed: {effective_job_name}")
    if not _is_complete_summary(
        summary_path,
        job_name=effective_job_name,
        expected_task_names=expected_task_names,
        attempts=attempts,
        harness_identity=harness_identity,
        timeout_sec=timeout_sec,
        n_concurrent_trials=n_concurrent_trials,
    ):
        raise RuntimeError(f"PerfRace stage did not write a complete summary: {summary_path}")
    return summary_path


if __name__ == "__main__":
    raise SystemExit(_main())
