"""Performance-profiling policy and Docker capability wiring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harbor.models.environment_type import EnvironmentType
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import EnvironmentConfig


RESOURCE_ROOT = Path(__file__).resolve().parent / "resources"
PERFORMANCE_SECCOMP_PROFILE = RESOURCE_ROOT / "perfrace-performance.json"


def add_performance_profile(environment: EnvironmentConfig, job_dir: Path) -> EnvironmentConfig:
    """Return a Docker environment with the profiling security overlay appended."""
    if environment.type != EnvironmentType.DOCKER:
        return environment

    profile = PERFORMANCE_SECCOMP_PROFILE.read_bytes()
    config_dir = job_dir / "perfrace" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_path = config_dir / PERFORMANCE_SECCOMP_PROFILE.name
    profile_path.write_bytes(profile)

    compose_path = config_dir / "docker-compose-performance.json"
    compose_path.write_text(
        json.dumps(
            {
                "x-perfrace-seccomp-sha256": hashlib.sha256(profile).hexdigest(),
                "services": {
                    "main": {
                        "cap_add": ["PERFMON"],
                        "security_opt": [f"seccomp={profile_path.resolve()}"],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if compose_path in environment.extra_docker_compose:
        return environment
    return environment.model_copy(
        update={
            "extra_docker_compose": [
                *environment.extra_docker_compose,
                compose_path,
            ]
        }
    )


def has_performance_profile(environment: EnvironmentConfig) -> bool:
    """Return whether the generated profiling overlay is active."""
    return any(
        path.name == "docker-compose-performance.json" for path in environment.extra_docker_compose
    )


def add_job_performance_profile(job: JobConfig) -> JobConfig:
    """Enable profiling for every Docker trial in a job."""
    environment = add_performance_profile(
        job.environment,
        job.jobs_dir / job.job_name,
    )
    return job.model_copy(update={"environment": environment})
