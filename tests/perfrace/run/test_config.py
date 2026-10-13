from __future__ import annotations

import tempfile
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from perfrace.run.config import (
    DEFAULT_JOBS_DIR,
    REPO_ROOT,
    LoadedRun,
    RunConfigError,
    load_run,
)


def _load_run(
    config: dict[str, Any],
    *,
    cli_agent: str | None = None,
    cli_model: str | None = None,
    cli_n_attempts: int | None = None,
    cli_job_name: str | None = None,
    cli_jobs_dir: Path | None = None,
    cli_enable_cache: bool | None = None,
    cli_patch: Path | None = None,
    cli_note: str | None = None,
    cli_agent_tag: str | None = None,
) -> LoadedRun:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "run.yaml"
        path.write_text(yaml.safe_dump(config))
        return load_run(
            path,
            agent=cli_agent,
            model=cli_model,
            n_attempts=cli_n_attempts,
            job_name=cli_job_name,
            jobs_dir=cli_jobs_dir,
            enable_cache=cli_enable_cache,
            patch=cli_patch,
            note=cli_note,
            agent_tag=cli_agent_tag,
        )


def test_loads_harbor_job_config_and_cli_overrides(tmp_path: Path) -> None:
    loaded = _load_run(
        {
            "job": {
                "jobs_dir": "data/jobs",
                "datasets": [
                    {
                        "path": "instances/harness-v0",
                        "task_names": ["terminus-kira--fix-ocaml-gc"],
                    }
                ],
                "n_concurrent_trials": 2,
            },
        },
        cli_job_name="override-job",
        cli_jobs_dir=tmp_path / "jobs",
    )

    assert loaded.job.job_name == "override-job"
    assert loaded.job.jobs_dir == tmp_path / "jobs"
    assert loaded.job.n_concurrent_trials == 2
    assert loaded.job.datasets[0].task_names == ["terminus-kira--fix-ocaml-gc"]


def test_host_resources_default_enabled_and_can_be_disabled() -> None:
    default = _load_run({"job": {}})
    disabled = _load_run(
        {
            "host_resources": {
                "enabled": False,
                "lock_dir": "/tmp/custom-perfrace-locks",
            },
            "job": {},
        }
    )

    assert default.host_resources.enabled is True
    assert default.host_resources.trial_cpu_leases is False
    assert default.host_resources.trial_process_isolation is False
    assert default.host_resources.trial_controller_memory_mb == 16 * 1024
    assert disabled.host_resources.enabled is False
    assert disabled.host_resources.trial_cpu_leases is False
    assert disabled.host_resources.trial_process_isolation is False
    assert disabled.host_resources.trial_controller_memory_mb == 16 * 1024
    assert disabled.host_resources.lock_dir == Path("/tmp/custom-perfrace-locks")
    assert disabled.to_json_dict()["host_resources"] == {
        "enabled": False,
        "trial_cpu_leases": False,
        "trial_process_isolation": False,
        "trial_controller_memory_mb": 16 * 1024,
        "lock_dir": "/tmp/custom-perfrace-locks",
    }


def test_performance_profile_is_enabled_by_section_presence() -> None:
    default = _load_run({"job": {}})
    enabled = _load_run({"performance_profile": {}, "job": {}})

    assert default.performance_profile is None
    assert default.to_json_dict()["performance_profile"] is None
    assert enabled.performance_profile is not None
    assert enabled.to_json_dict()["performance_profile"] == {}


def test_performance_profile_rejects_unknown_options() -> None:
    with pytest.raises(RunConfigError, match="unknown"):
        _load_run({"performance_profile": {"unknown": True}, "job": {}})


def test_host_resources_can_enable_trial_cpu_leases() -> None:
    loaded = _load_run(
        {
            "host_resources": {
                "trial_cpu_leases": True,
            },
            "job": {},
        }
    )

    assert loaded.host_resources.trial_cpu_leases is True


def test_host_resources_can_enable_trial_process_isolation() -> None:
    loaded = _load_run(
        {
            "host_resources": {
                "trial_cpu_leases": True,
                "trial_process_isolation": True,
                "trial_controller_memory_mb": 8192,
            },
            "job": {},
        }
    )

    assert loaded.host_resources.trial_process_isolation is True
    assert loaded.host_resources.trial_controller_memory_mb == 8192


@pytest.mark.parametrize(
    ("host_resources", "message"),
    [
        (
            {"trial_controller_memory_mb": 0},
            "trial_controller_memory_mb must be positive",
        ),
        (
            {"enabled": False, "trial_process_isolation": True},
            "trial_process_isolation requires host_resources.enabled",
        ),
    ],
)
def test_host_resources_reject_invalid_trial_process_isolation(
    host_resources: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(RunConfigError, match=message):
        _load_run({"host_resources": host_resources, "job": {}})


def test_host_resource_lock_dir_must_be_absolute() -> None:
    with pytest.raises(RunConfigError, match="lock_dir must be an absolute path"):
        _load_run({"host_resources": {"lock_dir": "relative/locks"}, "job": {}})


def test_defaults_job_output_dir_and_agents() -> None:
    loaded = _load_run({"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}})

    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert loaded.job.jobs_dir == (REPO_ROOT / DEFAULT_JOBS_DIR).resolve()
    assert loaded.job.agents == []


def test_load_run_allows_empty_harbor_job_sources() -> None:
    loaded = _load_run({})

    assert loaded.job.tasks == []
    assert loaded.job.datasets == []


def test_unrecognized_top_level_yaml_keys_are_ignored() -> None:
    """LoadedRun has no enveloping validated schema.

    Each piece (job, api_gateway, submission_path, note, agent_tag) reads
    itself out of the raw mapping independently, so keys outside that set are
    simply not consulted rather than rejected by a monolithic model.
    """
    loaded = _load_run(
        {
            "some_legacy_key": "ignored",
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
        }
    )

    assert loaded.job.tasks[0].path == Path("instances/harness-v0/demo")


def test_patch_workspace_dir_is_rejected() -> None:
    with pytest.raises(RunConfigError, match="has been removed"):
        _load_run(
            {
                "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
                "patch_workspace_dir": "/workspace",
            }
        )


def test_all_instances_declare_workdir() -> None:
    task_paths = sorted((REPO_ROOT / "instances").glob("**/task.toml"))
    missing = [
        path
        for path in task_paths
        if not tomllib.loads(path.read_text(encoding="utf-8"))
        .get("environment", {})
        .get("workdir")
    ]

    assert not missing, "Instances without [environment].workdir: " + ", ".join(
        str(path.relative_to(REPO_ROOT)) for path in missing
    )


def test_cli_agent_sets_candidate_agent_by_name() -> None:
    loaded = _load_run(
        {"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}},
        cli_agent="copilot-cli",
        cli_model="gpt-5.5",
    )

    assert len(loaded.job.agents) == 1
    assert loaded.job.agents[0].name == "copilot-cli"
    assert loaded.job.agents[0].model_name == "gpt-5.5"
    assert loaded.job.agents[0].import_path is None


def test_cli_agent_with_colon_is_treated_as_import_path() -> None:
    # An explicitly supplied path must round-trip; it is not a built-in mapping.
    custom_agent = "user_package.custom:UserAgent"
    loaded = _load_run(
        {"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}},
        cli_agent=custom_agent,
    )

    assert loaded.job.agents[0].import_path == custom_agent
    assert loaded.job.agents[0].name is None


def test_cli_n_attempts_overrides_job() -> None:
    loaded = _load_run(
        {"job": {"tasks": [{"path": "instances/harness-v0/demo"}], "n_attempts": 1}},
        cli_n_attempts=5,
    )

    assert loaded.job.n_attempts == 5


def test_agent_and_patch_are_mutually_exclusive() -> None:
    with pytest.raises(RunConfigError, match="mutually exclusive"):
        _load_run(
            {"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}},
            cli_agent="copilot",
            cli_patch=Path("data/submissions/demo"),
        )


def test_patch_resolves_submission_path() -> None:
    loaded = _load_run(
        {"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}},
        cli_patch=Path("data/submissions/demo"),
    )

    assert loaded.submission_path == (REPO_ROOT / "data/submissions/demo").resolve()


def test_submission_path_from_yaml_is_resolved() -> None:
    loaded = _load_run(
        {
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
            "submission_path": "data/submissions/demo",
        }
    )

    assert loaded.submission_path == (REPO_ROOT / "data/submissions/demo").resolve()


def test_resolves_api_gateway_api_key() -> None:
    loaded = _load_run(
        {
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
            "api_gateway": {
                "command": "gateway --port 4000",
                "base_url": "http://localhost:4000/v1",
                "api_key": "secret",
            },
        }
    )
    assert loaded.api_gateway is not None
    assert loaded.api_gateway.command == "gateway --port 4000"
    assert loaded.api_gateway.api_key == "secret"
    assert loaded.api_gateway.log_dir == loaded.job.jobs_dir / loaded.job.job_name


def test_resolves_gateway_references_in_agent_environment() -> None:
    loaded = _load_run(
        {
            "api_gateway": {
                "port": 4100,
                "command": "proxy --port ${api_gateway.port}",
                "base_url": "http://localhost:${api_gateway.port}/v1",
                "api_key": "secret",
            },
            "job": {
                "tasks": [{"path": "instances/harness-v0/demo"}],
                "agents": [
                    {
                        "name": "copilot-cli",
                        "env": {
                            "COPILOT_PROVIDER_BASE_URL": ("${api_gateway.container_base_url}"),
                            "COPILOT_PROVIDER_API_KEY": "${api_gateway.api_key}",
                        },
                    }
                ],
            },
        }
    )

    assert loaded.api_gateway is not None
    assert loaded.api_gateway.command == "proxy --port 4100"
    assert loaded.api_gateway.base_url == "http://localhost:4100/v1"
    assert loaded.api_gateway.healthcheck == "http://localhost:4100/health/liveliness"
    assert loaded.job.agents[0].env == {
        "COPILOT_PROVIDER_BASE_URL": "http://host.docker.internal:4100/v1",
        "COPILOT_PROVIDER_API_KEY": "secret",
    }


def test_note_and_agent_tag_from_yaml_and_cli() -> None:
    loaded = _load_run(
        {
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
            "note": "from yaml",
            "agent_tag": "yaml-tag",
        }
    )
    assert loaded.note == "from yaml"
    assert loaded.agent_tag == "yaml-tag"

    overridden = _load_run(
        {
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
            "note": "from yaml",
            "agent_tag": "yaml-tag",
        },
        cli_note="from cli",
        cli_agent_tag="cli-tag",
    )
    assert overridden.note == "from cli"
    assert overridden.agent_tag == "cli-tag"


def test_enable_cache_defaults_false_and_reflects_yaml_and_cli() -> None:
    # No CLI flag or YAML field: caching defaults to disabled.
    loaded = _load_run({"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}})
    assert loaded.enable_cache is False

    # Without a CLI override, the YAML field controls caching.
    yaml_enabled = _load_run(
        {
            "enable_cache": True,
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
        }
    )
    assert yaml_enabled.enable_cache is True

    # Explicit CLI flag always wins over the YAML field.
    cli_overrides_yaml = _load_run(
        {
            "enable_cache": True,
            "job": {"tasks": [{"path": "instances/harness-v0/demo"}]},
        },
        cli_enable_cache=False,
    )
    assert cli_overrides_yaml.enable_cache is False

    enabled = _load_run(
        {"job": {"tasks": [{"path": "instances/harness-v0/demo"}]}},
        cli_enable_cache=True,
    )
    assert enabled.enable_cache is True


@pytest.mark.parametrize(
    "agent_name", [
        "terminus-boxbox", "frozen", "harness-evolution", "harness-scaling",
        "bounded-boxbox", "periodic-boxbox",
    ]
)
def test_optimization_agents_require_explicit_budget_and_model(agent_name):
    with pytest.raises(RunConfigError, match="task_budget_sec"):
        _load_run({"job": {"agents": [{"name": agent_name, "model_name": "test-model"}]}})
    with pytest.raises(RunConfigError, match="model_name"):
        _load_run({"task_budget_sec": 14400, "job": {"agents": [{"name": agent_name}]}})
    loaded = _load_run(
        {
            "task_budget_sec": 14400,
            "job": {"agents": [{"name": agent_name, "model_name": "test-model"}]},
        }
    )
    assert loaded.job.agents[0].task_budget_sec == 14400
    assert loaded.job.agents[0].model_name == "test-model"


def test_disabled_profile_round_trips():
    original = _load_run({"job": {}})
    restored = _load_run(original.to_json_dict())
    assert restored.performance_profile is None
