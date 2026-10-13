import os
import subprocess
import sys
from pathlib import Path

import yaml

from perfrace.evolution.config import HarnessEvolutionConfig
from perfrace.evolution.job_builder import (
    OFFLINE_AGENT_IMPORT_PATH,
    build_stage_run,
    build_validation_run,
    resolved_run_config_sha256,
    validation_agent_name,
)
from perfrace.evolution.types import ValidationCandidateSpec


def test_build_stage_run_replaces_agent_tasks_attempts_and_timeout(tmp_path: Path) -> None:
    base_config = tmp_path / "base.yaml"
    base_config.write_text(
        yaml.safe_dump(
            {
                "job": {
                    "job_name": "template",
                    "jobs_dir": str(tmp_path / "base-jobs"),
                    "agents": [
                        {
                            "import_path": "example:TemplateAgent",
                            "model_name": "old-model",
                            "kwargs": {"max_turns": 2},
                            "env": {"LLM_API_KEY": "test-key"},
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    instance_root = tmp_path / "instances"
    for task_id in ("task-a", "task-b"):
        (instance_root / task_id).mkdir(parents=True)
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="demo",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=instance_root,
        base_run_config=base_config,
    )

    loaded = build_stage_run(
        config,
        task_ids=("task-a", "task-b"),
        harness_source=tmp_path / "runtime",
        harness_identity="a" * 40,
        attempts=3,
        timeout_sec=14400,
        n_concurrent_trials=24,
        jobs_dir=tmp_path / "jobs",
        job_name="validation-h1",
    )

    [agent] = loaded.job.agents
    assert agent.import_path == OFFLINE_AGENT_IMPORT_PATH
    assert agent.model_name == "test-model"
    assert agent.task_budget_sec == agent.override_timeout_sec
    assert loaded.job.n_concurrent_trials == 24
    assert agent.override_timeout_sec == 14400
    assert agent.kwargs["harness_identity"] == "a" * 40
    assert agent.kwargs["reasoning_effort"] == "high"
    assert loaded.job.n_attempts == 3
    assert [task.path.name for task in loaded.job.tasks] == ["task-a", "task-b"]


def test_build_validation_run_uses_one_global_multi_agent_job(tmp_path: Path) -> None:
    base_config = tmp_path / "base.yaml"
    base_config.write_text(
        yaml.safe_dump(
            {
                "job": {
                    "job_name": "template",
                    "agents": [
                        {
                            "import_path": "example:TemplateAgent",
                            "model_name": "old-model",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    instance_root = tmp_path / "instances"
    for task_id in ("task-a", "task-b"):
        (instance_root / task_id).mkdir(parents=True)
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="demo",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=instance_root,
        base_run_config=base_config,
    )
    candidates = tuple(
        ValidationCandidateSpec(
            generation=generation,
            agent_name=validation_agent_name(generation),
            harness_identity=character * 40,
            harness_source=tmp_path / f"runtime-{generation}",
            harness_source_sha256=character * 64,
        )
        for generation, character in zip((0, 8, 16, 24), "abcd", strict=True)
    )

    loaded = build_validation_run(
        config,
        task_ids=("task-a", "task-b"),
        candidates=candidates,
        attempts=3,
        timeout_sec=14400,
        n_concurrent_trials=40,
        jobs_dir=tmp_path / "jobs",
        job_name="validation-global",
    )

    assert loaded.job.job_name == "validation-global"
    assert loaded.job.n_attempts == 3
    assert loaded.job.n_concurrent_trials == 40
    assert [agent.name for agent in loaded.job.agents] == [
        "offline-harness-h0",
        "offline-harness-h8",
        "offline-harness-h16",
        "offline-harness-h24",
    ]
    assert [agent.kwargs["harness_identity"] for agent in loaded.job.agents] == [
        candidate.harness_identity for candidate in candidates
    ]


def test_resolved_run_config_hash_is_stable_across_hash_seeds(tmp_path: Path) -> None:
    config = tmp_path / "run.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "job": {
                    "job_name": "stable-hash",
                    "jobs_dir": str(tmp_path / "jobs"),
                    "retry": {
                        "exclude_exceptions": [
                            "AgentTimeoutError",
                            "VerifierTimeoutError",
                            "ModelNotFoundError",
                        ]
                    },
                    "agents": [],
                }
            }
        ),
        encoding="utf-8",
    )
    expected = resolved_run_config_sha256(config)
    script = (
        "from pathlib import Path;"
        "from perfrace.evolution.job_builder import resolved_run_config_sha256;"
        f"print(resolved_run_config_sha256(Path({str(config)!r})))"
    )
    hashes = {
        subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in ("1", "2", "3")
    }
    assert hashes == {expected}
