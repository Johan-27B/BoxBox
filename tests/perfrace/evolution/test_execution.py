import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from perfrace.evolution import execution
from perfrace.evolution.config import HarnessEvolutionConfig
from perfrace.evolution.paths import HarnessEvolutionPaths
from perfrace.evolution.runtime_repository import hash_source_tree
from perfrace.evolution.state import read_model, write_model_atomic
from perfrace.evolution.types import (
    EvolutionStage,
    EvolutionState,
    GenerationRecord,
    ResolvedEvolutionPlan,
    SelectionRecord,
    SplitManifest,
    StageSpec,
    TrainBatch,
    ValidationCampaignSpec,
    ValidationCandidateSpec,
)
from perfrace.run.cache import baseline_cache_key, baseline_cache_root, write_baseline_trial
from perfrace.run.report import RunPaths
from perfrace.run.types import PerfRaceConfig, RunSummary


def test_execute_stage_rotates_recovery_job_after_infrastructure_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stage_dir = tmp_path / "stage"
    jobs_dir = stage_dir / "jobs"
    failed_path = RunPaths(jobs_dir=jobs_dir, job_name="train-i1-h0").summary_path
    failed_path.parent.mkdir(parents=True)
    failed_path.write_text(
        RunSummary(
            job_name="train-i1-h0",
            enable_cache=True,
            used_api_gateway=True,
            trial_count=2,
            stats={"n_errored_trials": 2},
            tasks=[],
        ).model_dump_json(),
        encoding="utf-8",
    )
    built_names = []

    def fake_build_stage_run(*args, **kwargs):
        built_names.append(kwargs["job_name"])
        return SimpleNamespace(api_gateway=None, job=SimpleNamespace(job_name=kwargs["job_name"]))

    def fake_execute(loaded, *, verifier_kwargs):
        summary_path = RunPaths(
            jobs_dir=jobs_dir,
            job_name=loaded.job.job_name,
        ).summary_path
        summary_path.parent.mkdir(parents=True)
        summary_path.with_name("job.yaml").write_text(
            yaml.safe_dump(
                {
                    "n_attempts": 1,
                    "n_concurrent_trials": 20,
                    "agents": [
                        {"name": "nop"},
                        {
                            "import_path": (
                                "perfrace.installed.evolved:EvolvedHarnessAgent"
                            ),
                            "task_budget_sec": 60,
                            "override_timeout_sec": 60,
                            "kwargs": {"harness_identity": "a" * 40},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        baseline_measurement = {
            "verdict": "ACCEPTED",
            "metric": "wall-clock",
            "unit": "seconds",
            "value": 2.0,
        }
        candidate_measurement = {
            "verdict": "ACCEPTED",
            "metric": "wall-clock",
            "unit": "seconds",
            "value": 1.0,
        }
        summary_path.with_name("baseline.json").write_text(
            json.dumps(baseline_measurement),
            encoding="utf-8",
        )
        summary_path.with_name("candidate.json").write_text(
            json.dumps(candidate_measurement),
            encoding="utf-8",
        )
        summary_path.write_text(
            RunSummary.model_validate(
                {
                    "job_name": loaded.job.job_name,
                    "enable_cache": True,
                    "used_api_gateway": True,
                    "trial_count": 2,
                    "stats": {"n_errored_trials": 0},
                    "tasks": [
                        {
                            "task_name": "perfrace/task-a",
                            "baseline": {
                                "trial_name": "baseline",
                                "agent": "nop",
                                "trial_uri": "file:///tmp/baseline",
                                "artifact": "baseline.json",
                                "perf_trial": baseline_measurement,
                            },
                            "candidates": [
                                {
                                    "trial_name": "candidate",
                                    "agent": "offline-harness",
                                    "trial_uri": "file:///tmp/candidate",
                                    "artifact": "candidate.json",
                                    "perf_trial": candidate_measurement,
                                    "reward": 2.0,
                                }
                            ],
                        }
                    ],
                }
            ).model_dump_json(),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(execution, "build_stage_run", fake_build_stage_run)
    monkeypatch.setattr(execution, "execute", fake_execute)
    task_dir = tmp_path / "instances" / "task-a"
    task_dir.mkdir(parents=True)
    task_dir.joinpath("task.toml").write_text(
        """
[task]
name = "perfrace/task-a"

[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
unit = "seconds"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    harness_source = tmp_path / "runtime"
    harness_source.mkdir()
    harness_source.joinpath("runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    base_run_config = tmp_path / "run.yaml"
    base_run_config.write_text("job:\n  job_name: template\n", encoding="utf-8")
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="demo",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=tmp_path / "instances",
        base_run_config=base_run_config,
    )

    summary_path = execution.execute_stage(
        config,
        stage="train",
        iteration=1,
        generation=0,
        train_batch=TrainBatch(
            generation=1,
            epoch=1,
            batch_index=1,
            task_ids=("task-a",),
        ),
        train_schedule_sha256="b" * 64,
        task_ids=("task-a",),
        harness_source=harness_source,
        harness_identity="a" * 40,
        attempts=1,
        timeout_sec=60,
        n_concurrent_trials=20,
        stage_dir=stage_dir,
        job_name="train-i1-h0",
        verifier_kwargs={},
    )

    assert built_names == ["train-i1-h0-recovery-01"]
    assert (
        summary_path
        == RunPaths(
            jobs_dir=jobs_dir,
            job_name="train-i1-h0-recovery-01",
        ).summary_path
    )
    spec = read_model(stage_dir / "stage.json", StageSpec)
    assert spec.stage == "train"
    assert spec.iteration == 1
    assert spec.generation == 0
    assert spec.epoch == 1
    assert spec.batch_index == 1
    assert spec.train_schedule_sha256 == "b" * 64
    assert spec.effective_concurrency == 1


def test_complete_validation_summary_requires_all_agents_and_global_cap(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "perfrace"
    run_dir.mkdir()
    measurement = execution.Measurement(
        verdict="ACCEPTED",
        metric="wall-clock",
        unit="seconds",
        value=1.0,
    )
    baseline_path = run_dir / "baseline.json"
    baseline_path.write_text(measurement.model_dump_json(), encoding="utf-8")
    candidates = (
        ValidationCandidateSpec(
            generation=1,
            agent_name="offline-harness-h1",
            harness_identity="a" * 40,
            harness_source=tmp_path / "runtime-h1",
            harness_source_sha256="b" * 64,
        ),
        ValidationCandidateSpec(
            generation=8,
            agent_name="offline-harness-h8",
            harness_identity="c" * 40,
            harness_source=tmp_path / "runtime-h8",
            harness_source_sha256="d" * 64,
        ),
    )
    candidate_entries = []
    for candidate in candidates:
        for attempt in range(3):
            artifact = run_dir / f"{candidate.agent_name}-{attempt}.json"
            artifact.write_text(measurement.model_dump_json(), encoding="utf-8")
            candidate_entries.append(
                {
                    "trial_name": f"{candidate.agent_name}-{attempt}",
                    "agent": candidate.agent_name,
                    "trial_uri": "file:///tmp/candidate",
                    "artifact": artifact.name,
                    "perf_trial": measurement.model_dump(),
                    "reward": 1.0,
                }
            )
    summary_path = run_dir / "run.json"
    summary = RunSummary.model_validate(
        {
            "job_name": "validation-global",
            "enable_cache": True,
            "used_api_gateway": True,
            "trial_count": 7,
            "stats": {"n_errored_trials": 0},
            "tasks": [
                {
                    "task_name": "perfrace/task-a",
                    "baseline": {
                        "trial_name": "baseline",
                        "agent": "nop",
                        "trial_uri": "file:///tmp/baseline",
                        "artifact": baseline_path.name,
                        "perf_trial": measurement.model_dump(),
                    },
                    "candidates": candidate_entries,
                }
            ],
        }
    )
    summary_path.write_text(summary.model_dump_json(), encoding="utf-8")
    summary_path.with_name("job.yaml").write_text(
        yaml.safe_dump(
            {
                "n_attempts": 3,
                "n_concurrent_trials": 40,
                "agents": [
                    {"name": "nop"},
                    *[
                        {
                            "name": candidate.agent_name,
                            "import_path": (
                                "perfrace.installed.evolved:EvolvedHarnessAgent"
                            ),
                            "task_budget_sec": 14400,
                            "override_timeout_sec": 14400,
                            "kwargs": {
                                "harness_identity": candidate.harness_identity,
                                "harness_source": str(candidate.harness_source),
                            },
                        }
                        for candidate in candidates
                    ],
                ],
            }
        ),
        encoding="utf-8",
    )
    spec = ValidationCampaignSpec(
        candidates=candidates,
        task_ids=("task-a",),
        task_checksums={"task-a": "e" * 64},
        base_run_config_sha256="f" * 64,
        controller_source_sha256="0" * 64,
        attempts=3,
        timeout_sec=14400,
        n_concurrent_trials=40,
        effective_concurrency=6,
        job_name="validation-global",
    )

    assert execution._is_complete_validation_summary(
        summary_path,
        spec=spec,
        expected_task_names={"perfrace/task-a"},
    )
    incomplete = summary.model_copy(
        update={
            "tasks": [
                summary.tasks[0].model_copy(
                    update={"candidates": summary.tasks[0].candidates[:-1]}
                )
            ]
        }
    )
    summary_path.write_text(incomplete.model_dump_json(), encoding="utf-8")
    assert not execution._is_complete_validation_summary(
        summary_path,
        spec=spec,
        expected_task_names={"perfrace/task-a"},
    )


def test_complete_baseline_requires_accepted_measurement_and_cache(tmp_path: Path) -> None:
    task_dir = tmp_path / "instances" / "task-a"
    task_dir.mkdir(parents=True)
    task_dir.joinpath("task.toml").write_text(
        """[task]
name = "perfrace/task-a"

[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
unit = "seconds"
""",
        encoding="utf-8",
    )
    task = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert task is not None and task.cache_fields is not None
    jobs_dir = tmp_path / "jobs"
    summary_path = RunPaths(jobs_dir=jobs_dir, job_name="baseline").summary_path
    summary_path.parent.mkdir(parents=True)
    measurement = execution.Measurement(
        verdict="ACCEPTED", metric="wall-clock", unit="seconds", value=2.0
    )
    summary_path.with_name("baseline.json").write_text(
        measurement.model_dump_json(), encoding="utf-8"
    )
    summary_path.with_name("job.yaml").write_text(
        yaml.safe_dump({"n_concurrent_trials": 24, "agents": [{"name": "nop"}]}),
        encoding="utf-8",
    )
    summary_path.write_text(
        RunSummary.model_validate(
            {
                "job_name": "baseline",
                "enable_cache": True,
                "used_api_gateway": False,
                "trial_count": 1,
                "stats": {"n_errored_trials": 0},
                "tasks": [
                    {
                        "task_name": task.task_name,
                        "baseline": {
                            "trial_name": "baseline",
                            "agent": "nop",
                            "trial_uri": "file:///tmp/baseline",
                            "artifact": "baseline.json",
                            "perf_trial": measurement.model_dump(),
                        },
                        "candidates": [],
                    }
                ],
            }
        ).model_dump_json(),
        encoding="utf-8",
    )
    expected = {task.task_name: task}
    assert (
        execution.find_complete_baseline_summary(
            jobs_dir=jobs_dir,
            job_name="baseline",
            expected_configs=expected,
            n_concurrent_trials=24,
        )
        is None
    )
    write_baseline_trial(
        baseline_cache_root(jobs_dir),
        task.instance_id,
        baseline_cache_key(task.cache_fields),
        measurement,
    )
    assert (
        execution.find_complete_baseline_summary(
            jobs_dir=jobs_dir,
            job_name="baseline",
            expected_configs=expected,
            n_concurrent_trials=24,
        )
        == summary_path
    )


def test_generate_frozen_test_bundle_is_unrun_and_identity_locked(
    tmp_path: Path, monkeypatch
) -> None:
    instance_root = tmp_path / "instances"
    task_dir = instance_root / "task-c"
    task_dir.mkdir(parents=True)
    task_dir.joinpath("task.toml").write_text(
        """[task]
name = "perfrace/task-c"

[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
unit = "seconds"
""",
        encoding="utf-8",
    )
    base_config = tmp_path / "base.yaml"
    base_config.write_text(
        yaml.safe_dump(
            {
                "enable_cache": True,
                "api_gateway": {
                    "port": 45137,
                    "command": "proxy --port ${api_gateway.port}",
                    "base_url": "http://127.0.0.1:${api_gateway.port}/v1",
                    "api_key": "test-key",
                },
                "job": {
                    "job_name": "template",
                    "jobs_dir": str(tmp_path / "base-jobs"),
                    "agents": [{"import_path": "example:Agent", "model_name": "old"}],
                },
            }
        ),
        encoding="utf-8",
    )
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="demo",
        artifact_root=tmp_path / "artifacts",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=instance_root,
        base_run_config=base_config,
    )
    config_source = tmp_path / "evolution.yaml"
    config_source.write_text("frozen config\n", encoding="utf-8")
    config_source_sha256 = execution._sha256(config_source)
    source = SimpleNamespace(
        source_path=config_source,
        source_sha256=config_source_sha256,
        config=config,
    )
    monkeypatch.setattr(execution, "load_harness_evolution_config", lambda path: source)
    paths = HarnessEvolutionPaths(config.artifact_root, config.experiment_name)
    paths.frozen_runtime.mkdir(parents=True)
    paths.frozen_runtime.joinpath("runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    task = PerfRaceConfig.from_task_dir(task_dir, include_checksum=True)
    assert task is not None and task.task_checksum is not None
    split = SplitManifest(
        catalog_sha256="a" * 64,
        python_version="3.13",
        train_seed=42,
        validation_seed=43,
        early_test=(),
        train=("task-a",),
        validation=("task-b",),
        test=("task-c",),
    )
    plan = ResolvedEvolutionPlan(
        experiment_name="demo",
        harness_source_sha256="b" * 64,
        base_run_config_sha256="c" * 64,
        controller_source_sha256="d" * 64,
        task_checksums={"task-c": task.task_checksum},
        split=split,
        generations=2,
        train_batch_size=1,
        train_batch_seed=44,
        train_batches=(
            TrainBatch(generation=1, epoch=1, batch_index=1, task_ids=("task-a",)),
            TrainBatch(generation=2, epoch=2, batch_index=1, task_ids=("task-a",)),
        ),
        train_schedule_sha256="e" * 64,
        validation_generations=(1, 2),
        train_attempts=1,
        validation_attempts=3,
        test_attempts=3,
        train_timeout_sec=3600,
        validation_timeout_sec=14400,
        test_timeout_sec=14400,
        debugger_max_workers=20,
        train_concurrency=20,
        baseline_concurrency=24,
        validation_concurrency=24,
        test_concurrency=24,
        train_candidate_attempts=2,
        validation_candidate_attempts=6,
        test_candidate_attempts=3,
        validation_trial_hours=24,
        test_trial_hours=12,
        configured_trial_hours=26,
    )
    monkeypatch.setattr(execution, "resolve_evolution_plan", lambda loaded: plan)
    record = GenerationRecord(
        generation=1,
        commit="e" * 40,
        source_sha256="f" * 64,
    )
    selection = SelectionRecord(
        selected_generation=1,
        selected_commit=record.commit,
        validation_scores={},
    )
    write_model_atomic(paths.resolved_config, plan)
    write_model_atomic(paths.splits / "manifest.json", split)
    write_model_atomic(paths.selection, selection)
    write_model_atomic(paths.frozen_runtime_marker, record)
    write_model_atomic(
        paths.state,
        EvolutionState(
            experiment_name="demo",
            config_sha256=config_source_sha256,
            stage=EvolutionStage.TEST_READY,
            active_generation=1,
            generations=(record,),
            split_manifest_path=paths.splits / "manifest.json",
            selection_path=paths.selection,
        ),
    )

    spec = execution.generate_frozen_test_artifacts(
        config=config,
        config_source_path=config_source,
        config_source_sha256=config_source_sha256,
        plan=plan,
        paths=paths,
        selection=selection,
        selected_record=record,
    )

    assert spec.task_ids == ("task-c",)
    assert spec.selected_source_sha256 == record.source_sha256
    assert spec.selected_tree_sha256 == hash_source_tree(paths.frozen_runtime)
    assert spec.selected_tree_sha256 != spec.selected_source_sha256
    assert paths.test_manifest.read_text(encoding="utf-8") == "task-c\n"
    assert paths.test_run_script.stat().st_mode & 0o111
    assert paths.test_score_script.stat().st_mode & 0o111
    assert not (paths.jobs / spec.job_name).exists()
    assert "log_dir" not in yaml.safe_load(paths.test_config.read_text())["api_gateway"]
    assert execution.validate_frozen_test_artifacts(paths.root, require_unrun=True) == spec

    runtime_file = paths.frozen_runtime / "runtime.py"
    runtime_file.write_text("VALUE = 2\n", encoding="utf-8")
    try:
        execution.validate_frozen_test_artifacts(paths.root)
    except ValueError as exc:
        assert "Frozen test runtime source hash changed" in str(exc)
    else:
        raise AssertionError("expected frozen runtime identity validation failure")
    runtime_file.write_text("VALUE = 1\n", encoding="utf-8")

    paths.test_manifest.write_text("changed\n", encoding="utf-8")
    try:
        execution.validate_frozen_test_artifacts(paths.root)
    except ValueError as exc:
        assert "Test manifest changed" in str(exc)
    else:
        raise AssertionError("expected frozen test identity validation failure")


def test_task_manifest_text_has_no_phantom_empty_task() -> None:
    assert execution._task_manifest_text(()) == ""
    assert execution._task_manifest_text(("task-a", "task-b")) == "task-a\ntask-b\n"
