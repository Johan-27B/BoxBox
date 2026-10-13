from __future__ import annotations

import asyncio
import json
from pathlib import Path

from harbor.models.environment_type import EnvironmentType
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import AgentConfig

from perfrace.run.config import (
    HostResourcesConfig,
    LoadedRun,
    PerformanceProfileConfig,
)
from perfrace.run.report import NOP_AGENT_NAME
from perfrace.run.runner import (
    PATCH_AGENT_IMPORT_PATH,
    _create_and_run_job,
    _prepare_job,
)


def _loaded_run(
    *,
    jobs_dir: Path,
    agents: list[AgentConfig] | None = None,
    submission_path: Path | None = None,
    enable_cache: bool = False,
    note: str | None = None,
    agent_tag: str | None = None,
    host_resources: HostResourcesConfig | None = None,
    performance_profile: PerformanceProfileConfig | None = None,
) -> LoadedRun:
    job = JobConfig.model_validate(
        {
            "jobs_dir": jobs_dir,
            "job_name": "demo-job",
            "tasks": [{"path": "instances/harness-v0/demo"}],
            "agents": agents or [],
        }
    )
    return LoadedRun(
        job=job,
        api_gateway=None,
        submission_path=submission_path,
        enable_cache=enable_cache,
        performance_profile=performance_profile,
        host_resources=host_resources or HostResourcesConfig(),
        note=note,
        agent_tag=agent_tag,
    )


def test_prepare_job_prepends_nop_agent_with_scale_with_attempts_false(tmp_path: Path) -> None:
    candidate = AgentConfig(name="copilot", model_name="gpt-5.5")
    job = _prepare_job(_loaded_run(jobs_dir=tmp_path / "jobs", agents=[candidate]))

    assert job.agents[0].name == NOP_AGENT_NAME
    assert job.agents[0].scale_with_attempts is False
    assert job.agents[0].cacheable is True
    assert job.agents[1] == candidate


def test_prepare_job_injects_nop_even_with_no_candidate_agents(tmp_path: Path) -> None:
    job = _prepare_job(_loaded_run(jobs_dir=tmp_path / "jobs"))

    assert [agent.name for agent in job.agents] == [NOP_AGENT_NAME]


def test_prepare_job_injects_performance_seccomp_for_docker(tmp_path: Path) -> None:
    loaded = _loaded_run(
        jobs_dir=tmp_path / "jobs",
        performance_profile=PerformanceProfileConfig(),
    )
    existing = tmp_path / "existing-compose.yaml"
    existing.write_text("services: {}\n", encoding="utf-8")
    loaded.job.environment.extra_docker_compose.append(existing)

    job = _prepare_job(loaded)

    assert job.environment.extra_docker_compose[0] == existing
    assert len(job.environment.extra_docker_compose) == 2
    compose_path = job.environment.extra_docker_compose[1]
    compose = json.loads(compose_path.read_text())
    service = compose["services"]["main"]
    assert service["cap_add"] == ["PERFMON"]
    assert service["security_opt"] == [
        f"seccomp={compose_path.parent / 'perfrace-performance.json'}"
    ]


def test_prepare_job_skips_performance_seccomp_for_non_docker(tmp_path: Path) -> None:
    loaded = _loaded_run(
        jobs_dir=tmp_path / "jobs",
        performance_profile=PerformanceProfileConfig(),
    )
    loaded.job.environment.type = EnvironmentType.DAYTONA

    job = _prepare_job(loaded)

    assert job.environment.extra_docker_compose == []
    assert not (job.jobs_dir / job.job_name).exists()


def test_prepare_job_skips_performance_seccomp_without_config(tmp_path: Path) -> None:
    job = _prepare_job(_loaded_run(jobs_dir=tmp_path / "jobs"))

    assert job.environment.extra_docker_compose == []
    assert not (job.jobs_dir / job.job_name).exists()


def test_prepare_job_injects_patch_agent_when_submission_path_set(tmp_path: Path) -> None:
    submission = tmp_path / "submission"
    submission.mkdir()
    (submission / "predictions.jsonl").write_text(
        json.dumps({"instance_id": "task-a", "model_patch": "diff --git a/a b/a\n"}) + "\n"
    )

    job = _prepare_job(_loaded_run(jobs_dir=tmp_path / "jobs", submission_path=submission))

    assert [agent.name or agent.import_path for agent in job.agents] == [
        NOP_AGENT_NAME,
        PATCH_AGENT_IMPORT_PATH,
    ]
    patch_agent = job.agents[1]
    assert patch_agent.scale_with_attempts is False
    assert patch_agent.cacheable is True
    patches_by_instance = patch_agent.kwargs["patches_by_instance"]
    assert Path(patches_by_instance["task-a"]).read_text() == "diff --git a/a b/a\n"
    assert "workspace_dir" not in patch_agent.kwargs


def test_create_job_receives_trial_process_isolation_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeJob:
        @classmethod
        async def create(cls, config, **kwargs):
            captured.update(kwargs)
            return cls()

        async def run(self):
            return "result"

    monkeypatch.setattr("perfrace.run.runner.PerfRaceJob", FakeJob)
    loaded = _loaded_run(
        jobs_dir=tmp_path / "jobs",
        host_resources=HostResourcesConfig(
            trial_process_isolation=True,
            trial_controller_memory_mb=8192,
        ),
    )

    result = asyncio.run(_create_and_run_job(loaded, loaded.job))

    assert result == "result"
    assert captured["trial_process_isolation"] is True
    assert captured["trial_controller_memory_mb"] == 8192
