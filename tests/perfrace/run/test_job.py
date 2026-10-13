from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.job.lock import TaskLock, TrialLock
from harbor.models.trial.config import AgentConfig, TrialConfig
from harbor.models.trial.result import AgentInfo, TrialResult
from harbor.trial.hooks import TrialEvent, TrialHookEvent
from harbor.trial.queue import TrialQueue

from perfrace.run.cache import baseline_cache_key, read_baseline_trial, write_baseline_trial
from perfrace.run.job import PerfRaceJob, _agent_cache_fields
from perfrace.run.isolation import ProcessIsolatedTrialQueue
from perfrace.run.types import PerfRaceConfig, Measurement


def _task_dir(
    tmp_path: Path,
    name: str = "task-a",
    *,
    direction: str = "minimize",
    repetition_scope: str = "internal",
) -> Path:
    task_dir = tmp_path / name
    (task_dir / "environment").mkdir(parents=True)
    (task_dir / "tests").mkdir()
    (task_dir / "instruction.md").write_text("Optimize.\n")
    (task_dir / "task.toml").write_text(
        f"""
[task]
name = "perfrace/{name}"

[perfrace.measurement]
measurement = "wall-clock"
unit = "seconds"
direction = "{direction}"
repetition_scope = "{repetition_scope}"
"""
    )
    (task_dir / "tests" / "test.sh").write_text("#!/usr/bin/env bash\n")
    return task_dir


def _build_job(
    tmp_path: Path,
    task_dir: Path,
    *,
    enable_cache: bool,
    baseline_cache_root: Path,
    agents: list[dict[str, object]] | None = None,
    host_resources_enabled: bool = True,
    trial_cpu_leases: bool = False,
    trial_process_isolation: bool = False,
    trial_controller_memory_mb: int = 16 * 1024,
    verifier_kwargs: dict[str, object] | None = None,
    profiled_instances: frozenset[str] | None = frozenset(),
) -> PerfRaceJob:
    payload = {
        "jobs_dir": tmp_path / "jobs",
        "job_name": "demo-job",
        "tasks": [{"path": task_dir}],
        "agents": agents or [{"name": "nop", "cacheable": True}],
    }
    if verifier_kwargs is not None:
        payload["verifier"] = {"kwargs": verifier_kwargs}
    if profiled_instances:
        payload["environment"] = {"type": "docker"}
    config = JobConfig.model_validate(payload)
    task_configs = asyncio.run(Job._resolve_task_configs(config))
    return PerfRaceJob(
        config,
        _task_configs=task_configs,
        _metrics={},
        _task_download_results={},
        enable_cache=enable_cache,
        baseline_cache_root=baseline_cache_root,
        host_resources_enabled=host_resources_enabled,
        trial_cpu_leases=trial_cpu_leases,
        trial_process_isolation=trial_process_isolation,
        trial_controller_memory_mb=trial_controller_memory_mb,
    )


def test_cache_miss_leaves_trial_in_remaining_configs(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    job = _build_job(tmp_path, task_dir, enable_cache=True, baseline_cache_root=tmp_path / "cache")

    assert len(job._remaining_trial_configs) == 1
    assert job._existing_trial_configs == []


def test_host_allocator_uses_job_concurrency_for_shadow_pool(tmp_path: Path, monkeypatch) -> None:
    import perfrace.run.job as job_module

    configured: list[int] = []
    monkeypatch.setattr(
        job_module,
        "configure_shared_shadow_pool",
        configured.append,
    )
    allocator_configs: list[tuple[bool, Path]] = []
    monkeypatch.setattr(
        job_module,
        "configure_host_cpu_allocator",
        lambda enabled, *, lock_dir: allocator_configs.append((enabled, lock_dir)) or True,
    )
    task_dir = _task_dir(tmp_path)

    _build_job(
        tmp_path,
        task_dir,
        enable_cache=False,
        baseline_cache_root=tmp_path / "cache",
    )

    assert configured == [4]
    assert allocator_configs == [(True, Path("/tmp/perfrace-host-resources"))]


def test_disabled_host_allocator_keeps_serial_shadow_default(tmp_path: Path, monkeypatch) -> None:
    import perfrace.run.job as job_module

    configured: list[int] = []
    enabled_values: list[bool] = []
    monkeypatch.setattr(job_module, "configure_shared_shadow_pool", configured.append)
    monkeypatch.setattr(
        job_module,
        "configure_host_cpu_allocator",
        lambda enabled, *, lock_dir: enabled_values.append(enabled),
    )

    _build_job(
        tmp_path,
        _task_dir(tmp_path),
        enable_cache=False,
        baseline_cache_root=tmp_path / "cache",
        host_resources_enabled=False,
    )

    assert configured == [1]
    assert enabled_values == [False]


def test_unavailable_host_allocator_keeps_serial_shadow_default(
    tmp_path: Path, monkeypatch
) -> None:
    import perfrace.run.job as job_module

    configured: list[int] = []
    monkeypatch.setattr(job_module, "configure_shared_shadow_pool", configured.append)
    monkeypatch.setattr(
        job_module,
        "configure_host_cpu_allocator",
        lambda _enabled, *, lock_dir: False,
    )

    _build_job(
        tmp_path,
        _task_dir(tmp_path),
        enable_cache=False,
        baseline_cache_root=tmp_path / "cache",
    )

    assert configured == [1]


def test_trial_process_isolation_replaces_queue_and_preserves_job_hooks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "perfrace.run.isolation.validate_process_isolation_support",
        lambda: None,
    )
    task_dir = _task_dir(tmp_path)
    default = _build_job(
        tmp_path,
        task_dir,
        enable_cache=False,
        baseline_cache_root=tmp_path / "cache",
    )
    isolated = _build_job(
        tmp_path / "isolated",
        _task_dir(tmp_path / "isolated"),
        enable_cache=False,
        baseline_cache_root=tmp_path / "cache",
        trial_cpu_leases=True,
        trial_process_isolation=True,
        trial_controller_memory_mb=8192,
    )

    assert type(default._trial_queue) is TrialQueue
    assert isinstance(isolated._trial_queue, ProcessIsolatedTrialQueue)
    assert isolated._trial_queue._controller_memory_mb == 8192
    assert isolated._trial_queue._host_resources_enabled is True
    assert isolated._trial_queue._host_resource_lock_dir == Path("/tmp/perfrace-host-resources")
    assert isolated._trial_queue._trial_cpu_leases is True
    assert len(isolated._trial_queue._hooks[TrialEvent.START]) == 1
    assert len(isolated._trial_queue._hooks[TrialEvent.CANCEL]) == 1
    assert len(isolated._trial_queue._hooks[TrialEvent.END]) == 1


def test_trial_process_isolation_fails_before_launch_when_unsupported(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def unsupported() -> None:
        raise RuntimeError("cgroup unavailable")

    monkeypatch.setattr(
        "perfrace.run.isolation.validate_process_isolation_support",
        unsupported,
    )

    with pytest.raises(RuntimeError, match="cgroup unavailable"):
        _build_job(
            tmp_path,
            _task_dir(tmp_path),
            enable_cache=False,
            baseline_cache_root=tmp_path / "cache",
            trial_cpu_leases=True,
            trial_process_isolation=True,
        )


def test_trial_process_isolation_requires_trial_cpu_leases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "perfrace.run.isolation.validate_process_isolation_support",
        lambda: None,
    )

    with pytest.raises(ValueError, match="requires trial_cpu_leases"):
        _build_job(
            tmp_path,
            _task_dir(tmp_path),
            enable_cache=False,
            baseline_cache_root=tmp_path / "cache",
            trial_process_isolation=True,
        )


def test_trial_process_isolation_rejects_non_checkpoint_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "perfrace.run.isolation.validate_process_isolation_support",
        lambda: None,
    )

    with pytest.raises(ValueError, match="requires checkpoint candidate agents"):
        _build_job(
            tmp_path,
            _task_dir(tmp_path),
            enable_cache=False,
            baseline_cache_root=tmp_path / "cache",
            agents=[{"name": "nop", "cacheable": False}],
            trial_cpu_leases=True,
            trial_process_isolation=True,
        )


def test_trial_process_isolation_rejects_external_repetitions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "perfrace.run.isolation.validate_process_isolation_support",
        lambda: None,
    )

    with pytest.raises(ValueError, match="requires internal measurement repetitions"):
        _build_job(
            tmp_path,
            _task_dir(tmp_path, repetition_scope="external"),
            enable_cache=False,
            baseline_cache_root=tmp_path / "cache",
            trial_cpu_leases=True,
            trial_process_isolation=True,
        )


def test_trial_process_isolation_rejects_explicit_shadow_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "perfrace.run.isolation.validate_process_isolation_support",
        lambda: None,
    )

    with pytest.raises(ValueError, match="does not support max_concurrent_shadows"):
        _build_job(
            tmp_path,
            _task_dir(tmp_path),
            enable_cache=False,
            baseline_cache_root=tmp_path / "cache",
            trial_cpu_leases=True,
            trial_process_isolation=True,
            verifier_kwargs={"max_concurrent_shadows": 1},
        )


def test_cache_disabled_never_skips_even_with_a_matching_entry(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    cache_root = tmp_path / "cache"
    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    write_baseline_trial(
        cache_root,
        config.instance_id,
        baseline_cache_key(config.cache_fields),
        Measurement(
            verdict="ACCEPTED", metric="wall-clock", unit="seconds", value=10.0, details={}
        ),
    )

    job = _build_job(tmp_path, task_dir, enable_cache=False, baseline_cache_root=cache_root)

    assert len(job._remaining_trial_configs) == 1


def test_cache_hit_skips_the_trial_and_synthesizes_its_result(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    cache_root = tmp_path / "cache"
    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    cached = Measurement(
        verdict="ACCEPTED", metric="wall-clock", unit="seconds", value=10.0, details={}
    )
    write_baseline_trial(
        cache_root, config.instance_id, baseline_cache_key(config.cache_fields), cached
    )

    job = _build_job(tmp_path, task_dir, enable_cache=True, baseline_cache_root=cache_root)

    assert job._remaining_trial_configs == []
    [existing_config] = job._existing_trial_configs
    [existing_result] = job._existing_trial_results
    assert existing_config.trial_name == existing_result.trial_name
    assert existing_result.agent_info.name == "nop"

    trial_dir = Path(existing_result.trial_uri.removeprefix("file://"))
    report = Measurement.model_validate_json(
        (trial_dir / "verifier" / "measurement.json").read_text()
    )
    assert report == cached


def _hook_event(trial_config: TrialConfig, trial_result: TrialResult) -> TrialHookEvent:
    dummy_digest = "sha256:" + "0" * 64
    lock = TrialLock(
        task=TaskLock(name=trial_result.task_name, type="local", digest=dummy_digest),
        agent=trial_config.agent,
        environment=trial_config.environment,
        verifier=trial_config.verifier,
    )
    return TrialHookEvent(
        event=TrialEvent.END,
        task_name=trial_result.task_name,
        config=trial_config,
        result=trial_result,
        lock=lock,
    )


def test_write_baseline_cache_persists_a_completed_cacheable_trial(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    cache_root = tmp_path / "cache"
    job = _build_job(tmp_path, task_dir, enable_cache=True, baseline_cache_root=cache_root)

    [trial_config] = job._remaining_trial_configs
    trial_dir = job.job_dir / trial_config.trial_name
    (trial_dir / "verifier").mkdir(parents=True)
    measured = Measurement(
        verdict="ACCEPTED", metric="wall-clock", unit="seconds", value=12.5, details={}
    )
    (trial_dir / "verifier" / "measurement.json").write_text(measured.model_dump_json())

    trial_result = TrialResult(
        task_name="perfrace/task-a",
        trial_name=trial_config.trial_name,
        trial_uri=trial_dir.resolve().as_uri(),
        task_id=trial_config.task.get_task_id(),
        task_checksum="unused",
        config=trial_config,
        agent_info=AgentInfo(name="nop", version="1.0.0"),
    )

    asyncio.run(job._write_baseline_cache_if_cacheable(_hook_event(trial_config, trial_result)))

    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    cache_key = baseline_cache_key(config.cache_fields)
    assert read_baseline_trial(cache_root, config.instance_id, cache_key) == measured


def test_write_baseline_cache_skips_a_trial_with_no_valid_report(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    cache_root = tmp_path / "cache"
    job = _build_job(tmp_path, task_dir, enable_cache=True, baseline_cache_root=cache_root)

    [trial_config] = job._remaining_trial_configs
    trial_dir = job.job_dir / trial_config.trial_name
    trial_result = TrialResult(
        task_name="perfrace/task-a",
        trial_name=trial_config.trial_name,
        trial_uri=trial_dir.resolve().as_uri(),
        task_id=trial_config.task.get_task_id(),
        task_checksum="unused",
        config=trial_config,
        agent_info=AgentInfo(name="nop", version="1.0.0"),
    )

    asyncio.run(job._write_baseline_cache_if_cacheable(_hook_event(trial_config, trial_result)))

    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    cache_key = baseline_cache_key(config.cache_fields)
    assert read_baseline_trial(cache_root, config.instance_id, cache_key) is None


def test_write_baseline_cache_skips_a_non_accepted_verdict(tmp_path: Path) -> None:
    """A verifier cancelled by the outer timeout (or any other non-ACCEPTED
    outcome) still leaves a syntactically valid measurement.json (see
    PerfRaceVerifier.verify()'s TIMEOUT/VERIFIER_ERROR placeholder) --
    caching it as a baseline would make every later trial fail to score
    against a baseline that was never actually measured."""
    task_dir = _task_dir(tmp_path)
    cache_root = tmp_path / "cache"
    job = _build_job(tmp_path, task_dir, enable_cache=True, baseline_cache_root=cache_root)

    [trial_config] = job._remaining_trial_configs
    trial_dir = job.job_dir / trial_config.trial_name
    (trial_dir / "verifier").mkdir(parents=True)
    stub = Measurement(verdict="TIMEOUT", metric="wall-clock", unit="seconds", value=None)
    (trial_dir / "verifier" / "measurement.json").write_text(stub.model_dump_json())

    trial_result = TrialResult(
        task_name="perfrace/task-a",
        trial_name=trial_config.trial_name,
        trial_uri=trial_dir.resolve().as_uri(),
        task_id=trial_config.task.get_task_id(),
        task_checksum="unused",
        config=trial_config,
        agent_info=AgentInfo(name="nop", version="1.0.0"),
    )

    asyncio.run(job._write_baseline_cache_if_cacheable(_hook_event(trial_config, trial_result)))

    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    cache_key = baseline_cache_key(config.cache_fields)
    assert read_baseline_trial(cache_root, config.instance_id, cache_key) is None


def test_agent_cache_fields_folds_in_patch_content_digest(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None

    patch = tmp_path / "task-a.patch"
    patch.write_text("diff --git a/a b/a\n")
    trial_config = TrialConfig(
        task={"path": task_dir},
        agent=AgentConfig(
            import_path="perfrace.installed.patch:PatchAgent",
            cacheable=True,
            kwargs={"patches_by_instance": {config.instance_id: str(patch)}},
        ),
    )

    fields = _agent_cache_fields(trial_config, config)

    assert "patch_digest" in fields


def test_agent_cache_fields_empty_for_nop(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    trial_config = TrialConfig(
        task={"path": task_dir},
        agent=AgentConfig(name="nop", cacheable=True),
    )

    assert _agent_cache_fields(trial_config, config) == {}


def test_agent_cache_fields_include_performance_profile(tmp_path: Path) -> None:
    task_dir = _task_dir(tmp_path)
    config = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert config is not None
    compose = tmp_path / "docker-compose-performance.json"
    compose.write_text("{}\n")
    trial_config = TrialConfig(
        task={"path": task_dir},
        agent=AgentConfig(name="nop", cacheable=True),
        environment={"type": "docker", "extra_docker_compose": [compose]},
    )

    assert _agent_cache_fields(trial_config, config) == {"performance_profile": True}
