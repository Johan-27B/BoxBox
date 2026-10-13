import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from perfrace.evolution.config import (
    HarnessEvolutionConfig,
    LoadedHarnessEvolutionConfig,
    load_harness_evolution_config,
)
from perfrace.evolution.orchestrator import (
    PreparedEvolution,
    prepare_experiment,
    run_baseline_stage,
    run_evolution,
    run_train_generation,
    run_validation_and_select,
    validate_iteration_target,
)
from perfrace.evolution.paths import HarnessEvolutionPaths
from perfrace.evolution.runtime_repository import RuntimeRepository
from perfrace.evolution.state import read_model
from perfrace.evolution.types import (
    AggregateScore,
    EvolutionStage,
    EvolutionState,
    GenerationRecord,
    ResolvedEvolutionPlan,
    SplitManifest,
    TrainBatch,
)
from perfrace.run.types import RunSummary


def test_prepare_experiment_initializes_and_resumes_durable_state(
    tmp_path: Path, monkeypatch
) -> None:
    instance_ids = [f"instance-{index:02d}" for index in range(100)]
    catalog = tmp_path / "releases.json"
    catalog.write_text(
        json.dumps(
            {
                "instances": {
                    instance_id: {
                        "instance": instance_id,
                        "image": f"ghcr.io/example/{instance_id}@sha256:{index:064x}",
                        "task_artifact": (
                            f"ghcr.io/example/{instance_id}@sha256:{index + 1000:064x}"
                        ),
                    }
                    for index, instance_id in enumerate(instance_ids)
                }
            }
        ),
        encoding="utf-8",
    )
    early = tmp_path / "early.txt"
    early.write_text("\n".join(instance_ids[:32]) + "\n", encoding="utf-8")
    instance_root = tmp_path / "instances"
    for instance_id in instance_ids:
        task_dir = instance_root / instance_id
        task_dir.mkdir(parents=True)
        task_dir.joinpath("task.toml").write_text(
            f"""
[task]
name = "perfrace/{instance_id}"

[perfrace.measurement]
measurement = "wall-clock"
direction = "minimize"
unit = "seconds"
""".strip()
            + "\n",
            encoding="utf-8",
        )
    harness_source = tmp_path / "runtime-source"
    (harness_source / "kernel").mkdir(parents=True)
    (harness_source / "__init__.py").write_text(
        "class TerminusBoxBox:\n    setup = set_task_instruction = ensure_agent_session = configure_target_phase = run_until_trap = export_state = import_state = release_session = attach_session = restart_session = prepare_continuation = reconcile_review_trajectory = mark_harness_context_accepted = review = lambda *a, **k: None\n",
        encoding="utf-8",
    )
    (harness_source / "kernel" / "contract.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    run_config = tmp_path / "run.yaml"
    run_config.write_text(
        yaml.safe_dump(
            {
                "job": {
                    "job_name": "template",
                    "agents": [
                        {
                            "import_path": "example:Agent",
                            "model_name": "gpt-test",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "evolution.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "experiment_name": "demo",
                "model_name": "test-model",
                "artifact_root": str(tmp_path / "artifacts"),
                "release_catalog": str(catalog),
                "early_test_manifest": str(early),
                "instance_root": str(instance_root),
                "base_run_config": str(run_config),
                "harness_source": str(harness_source),
                "protocol": {"trust_evolved_code": True},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_harness_evolution_config(config_path)

    prepared = prepare_experiment(loaded, resume=False)
    resumed = prepare_experiment(loaded, resume=True)

    assert prepared.state.stage == EvolutionStage.BASELINING
    assert prepared.state.active_generation == 0
    assert prepared.paths.state.is_file()
    assert prepared.paths.generation(0).joinpath("runtime/__init__.py").is_file()
    assert len(prepared.paths.splits.joinpath("test.txt").read_text().splitlines()) == 50
    batch_paths = sorted((prepared.paths.splits / "train-batches").glob("*.txt"))
    assert len(batch_paths) == 5
    assert all(len(path.read_text().splitlines()) == 40 for path in batch_paths)
    assert resumed.state == prepared.state
    assert resumed.runtime_repository.path == prepared.runtime_repository.path

    baseline = MagicMock(return_value=tmp_path / "baseline-run.json")
    monkeypatch.setattr("perfrace.evolution.orchestrator.execute_baseline", baseline)
    advanced = run_baseline_stage(prepared, verifier_kwargs={})

    assert advanced.state.stage == EvolutionStage.TRAINING
    assert len(baseline.call_args.kwargs["task_ids"]) == 40
    assert baseline.call_args.kwargs["n_concurrent_trials"] == 24

    prepared.paths.train_batch(1).write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Train batch changed"):
        prepare_experiment(loaded, resume=True)


def test_run_train_generation_persists_score_evidence_and_next_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="demo",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=tmp_path / "instances",
        base_run_config=tmp_path / "run.yaml",
        harness_source=tmp_path / "runtime-source",
    )
    loaded = LoadedHarnessEvolutionConfig(
        source_path=tmp_path / "evolution.yaml",
        source_sha256="a" * 64,
        config=config,
    )
    split = SplitManifest(
        catalog_sha256="b" * 64,
        python_version="3.13",
        train_seed=42,
        validation_seed=43,
        early_test=(),
        train=("task-a", "task-d"),
        validation=("task-b",),
        test=("task-c",),
    )
    plan = ResolvedEvolutionPlan(
        experiment_name="demo",
        harness_source_sha256="c" * 64,
        base_run_config_sha256="d" * 64,
        controller_source_sha256="e" * 64,
        task_checksums={
            "task-a": "f" * 64,
            "task-b": "0" * 64,
            "task-d": "2" * 64,
        },
        split=split,
        generations=2,
        train_batch_size=1,
        train_batch_seed=44,
        train_batches=(
            TrainBatch(generation=1, epoch=1, batch_index=1, task_ids=("task-a",)),
            TrainBatch(generation=2, epoch=1, batch_index=2, task_ids=("task-d",)),
        ),
        train_schedule_sha256="1" * 64,
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
        test_candidate_attempts=3,
        validation_trial_hours=24,
        test_trial_hours=12,
        validation_candidate_attempts=6,
        configured_trial_hours=26,
    )
    paths = HarnessEvolutionPaths(tmp_path / "artifacts", "demo")
    (paths.generation(0) / "runtime").mkdir(parents=True)
    generated = MagicMock()
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.generate_frozen_test_artifacts",
        generated,
    )
    state = EvolutionState(
        experiment_name="demo",
        config_sha256="a" * 64,
        stage=EvolutionStage.TRAINING,
        active_generation=0,
        generations=(
            GenerationRecord(
                generation=0,
                commit="d" * 40,
                source_sha256="e" * 64,
            ),
        ),
        split_manifest_path=paths.splits / "manifest.json",
    )
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    run_dir = tmp_path / "job" / "perfrace"
    selected = run_dir / "trials" / "candidate.measurement.json"
    selected.parent.mkdir(parents=True)
    selected.write_text("{}\n", encoding="utf-8")
    summary = RunSummary.model_validate(
        {
            "job_name": "train-i1-h0",
            "enable_cache": True,
            "used_api_gateway": True,
            "trial_count": 2,
            "tasks": [
                {
                    "task_name": "task-a",
                    "baseline": None,
                    "candidates": [
                        {
                            "trial_name": "candidate",
                            "agent": "offline-harness",
                            "trial_uri": trial_dir.resolve().as_uri(),
                            "artifact": "trials/candidate.measurement.json",
                            "reward": 2.0,
                        }
                    ],
                }
            ],
        }
    )
    run_summary_path = run_dir / "run.json"
    run_summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    execute_stage = MagicMock(return_value=run_summary_path)
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.execute_stage",
        execute_stage,
    )
    prepared = PreparedEvolution(
        loaded=loaded,
        plan=plan,
        paths=paths,
        state=state,
        runtime_repository=MagicMock(),
    )

    updated = run_train_generation(prepared)

    assert updated.state.stage == EvolutionStage.ANALYZING
    assert paths.generation(0).joinpath("train/score.json").is_file()
    assert paths.generation(0).joinpath("train/evidence.json").is_file()
    assert paths.state.is_file()
    assert execute_stage.call_args.kwargs["task_ids"] == ("task-a",)
    assert execute_stage.call_args.kwargs["n_concurrent_trials"] == 20
    assert execute_stage.call_args.kwargs["iteration"] == 1
    assert execute_stage.call_args.kwargs["generation"] == 0

    h7_paths = HarnessEvolutionPaths(tmp_path / "h7-artifacts", "demo")
    (h7_paths.generation(7) / "runtime").mkdir(parents=True)
    h7_plan = plan.model_copy(
        update={
            "generations": 8,
            "train_batches": tuple(
                TrainBatch(
                    generation=iteration,
                    epoch=1,
                    batch_index=iteration,
                    task_ids=("task-a",),
                )
                for iteration in range(1, 9)
            ),
        }
    )
    h7_state = state.model_copy(
        update={
            "active_generation": 7,
            "generations": (
                GenerationRecord(
                    generation=7,
                    commit="d" * 40,
                    source_sha256="e" * 64,
                ),
            ),
        }
    )
    execute_stage.reset_mock()

    run_train_generation(
        PreparedEvolution(
            loaded=loaded,
            plan=h7_plan,
            paths=h7_paths,
            state=h7_state,
            runtime_repository=MagicMock(),
        )
    )

    assert execute_stage.call_args.kwargs["iteration"] == 8
    assert execute_stage.call_args.kwargs["generation"] == 7


def test_run_evolution_stops_at_cumulative_iteration_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    prepared = PreparedEvolution(
        loaded=MagicMock(),
        plan=SimpleNamespace(generations=24),
        paths=HarnessEvolutionPaths(tmp_path, "demo"),
        state=EvolutionState(
            experiment_name="demo",
            config_sha256="a" * 64,
            stage=EvolutionStage.BASELINING,
            active_generation=0,
            split_manifest_path=tmp_path / "split.json",
        ),
        runtime_repository=MagicMock(),
    )
    calls = {"baseline": 0, "train": 0, "analysis": 0, "evolve": 0, "validation": 0}

    def advance(current: PreparedEvolution, stage: EvolutionStage) -> PreparedEvolution:
        return replace(current, state=current.state.model_copy(update={"stage": stage}))

    def baseline(current: PreparedEvolution, **kwargs) -> PreparedEvolution:
        calls["baseline"] += 1
        return advance(current, EvolutionStage.TRAINING)

    def train(current: PreparedEvolution, **kwargs) -> PreparedEvolution:
        calls["train"] += 1
        return advance(current, EvolutionStage.ANALYZING)

    def analysis(current: PreparedEvolution, **kwargs) -> PreparedEvolution:
        calls["analysis"] += 1
        return advance(current, EvolutionStage.EVOLVING)

    def evolve(current: PreparedEvolution, **kwargs) -> PreparedEvolution:
        calls["evolve"] += 1
        return replace(
            current,
            state=current.state.model_copy(
                update={
                    "stage": EvolutionStage.TRAINING,
                    "active_generation": current.state.active_generation + 1,
                }
            ),
        )

    def validation(current: PreparedEvolution, **kwargs) -> PreparedEvolution:
        calls["validation"] += 1
        return advance(current, EvolutionStage.TEST_READY)

    monkeypatch.setattr("perfrace.evolution.orchestrator.run_baseline_stage", baseline)
    monkeypatch.setattr("perfrace.evolution.orchestrator.run_train_generation", train)
    monkeypatch.setattr("perfrace.evolution.orchestrator.run_analysis_stage", analysis)
    monkeypatch.setattr("perfrace.evolution.orchestrator.run_evolution_stage", evolve)
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.run_validation_and_select",
        validation,
    )

    stopped = run_evolution(
        prepared,
        iterations=8,
        endpoint=MagicMock(),
        verifier_kwargs={},
    )
    repeated = run_evolution(
        stopped,
        iterations=8,
        endpoint=MagicMock(),
        verifier_kwargs={},
    )

    assert stopped.state.stage == EvolutionStage.TRAINING
    assert stopped.state.active_generation == 8
    assert repeated == stopped
    assert calls == {
        "baseline": 1,
        "train": 8,
        "analysis": 8,
        "evolve": 8,
        "validation": 0,
    }


def test_run_evolution_can_stop_at_h24_before_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    prepared = PreparedEvolution(
        loaded=MagicMock(),
        plan=SimpleNamespace(generations=24),
        paths=HarnessEvolutionPaths(tmp_path, "demo"),
        state=EvolutionState(
            experiment_name="demo",
            config_sha256="a" * 64,
            stage=EvolutionStage.TRAINING,
            active_generation=23,
            split_manifest_path=tmp_path / "split.json",
        ),
        runtime_repository=MagicMock(),
    )
    calls = {"train": 0, "analysis": 0, "evolve": 0, "validation": 0}

    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.run_train_generation",
        lambda current, **kwargs: (
            calls.__setitem__("train", calls["train"] + 1)
            or replace(
                current,
                state=current.state.model_copy(update={"stage": EvolutionStage.ANALYZING}),
            )
        ),
    )
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.run_analysis_stage",
        lambda current, **kwargs: (
            calls.__setitem__("analysis", calls["analysis"] + 1)
            or replace(
                current,
                state=current.state.model_copy(update={"stage": EvolutionStage.EVOLVING}),
            )
        ),
    )
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.run_evolution_stage",
        lambda current, **kwargs: (
            calls.__setitem__("evolve", calls["evolve"] + 1)
            or replace(
                current,
                state=current.state.model_copy(
                    update={
                        "stage": EvolutionStage.TRAINING,
                        "active_generation": 24,
                    }
                ),
            )
        ),
    )
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.run_validation_and_select",
        lambda current, **kwargs: (
            calls.__setitem__("validation", calls["validation"] + 1)
            or replace(
                current,
                state=current.state.model_copy(update={"stage": EvolutionStage.TEST_READY}),
            )
        ),
    )

    trained = run_evolution(
        prepared,
        iterations=24,
        endpoint=MagicMock(),
        verifier_kwargs={},
        stop_after_training=True,
    )

    assert trained.state.stage == EvolutionStage.TRAINING
    assert trained.state.active_generation == 24
    assert calls == {"train": 1, "analysis": 1, "evolve": 1, "validation": 0}

    completed = run_evolution(
        trained,
        iterations=24,
        endpoint=MagicMock(),
        verifier_kwargs={},
    )

    assert completed.state.stage == EvolutionStage.TEST_READY
    assert calls == {"train": 1, "analysis": 1, "evolve": 1, "validation": 1}


def test_validate_iteration_target_rejects_backward_and_out_of_range(
    tmp_path: Path,
) -> None:
    prepared = PreparedEvolution(
        loaded=MagicMock(),
        plan=SimpleNamespace(generations=24),
        paths=HarnessEvolutionPaths(tmp_path, "demo"),
        state=EvolutionState(
            experiment_name="demo",
            config_sha256="a" * 64,
            stage=EvolutionStage.TRAINING,
            active_generation=8,
            split_manifest_path=tmp_path / "split.json",
        ),
        runtime_repository=MagicMock(),
    )

    validate_iteration_target(prepared, 8)
    with pytest.raises(ValueError, match="behind durable progress"):
        validate_iteration_target(prepared, 7)
    with pytest.raises(ValueError, match="between 1 and 24"):
        validate_iteration_target(prepared, 25)


def test_run_validation_selects_best_generation_and_freezes_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    (source / "kernel").mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    runtime_file = source / "runtime.py"
    runtime_file.write_text("GENERATION = 0\n", encoding="utf-8")
    (source / "kernel" / "contract.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    repository = RuntimeRepository.initialize(source, tmp_path / "repository")
    h0 = repository.validate_head()
    repository_runtime = repository.path / "runtime.py"
    repository_runtime.write_text("GENERATION = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository.path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repository.path), "commit", "-q", "-m", "generation two"],
        check=True,
    )
    h1 = repository.validate_head()
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="demo",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=tmp_path / "instances",
        base_run_config=tmp_path / "run.yaml",
        harness_source=source,
    )
    loaded = LoadedHarnessEvolutionConfig(
        source_path=tmp_path / "evolution.yaml",
        source_sha256="a" * 64,
        config=config,
    )
    split = SplitManifest(
        catalog_sha256="b" * 64,
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
        harness_source_sha256="c" * 64,
        base_run_config_sha256="d" * 64,
        controller_source_sha256="e" * 64,
        task_checksums={"task-a": "f" * 64, "task-b": "0" * 64},
        split=split,
        generations=2,
        train_batch_size=1,
        train_batch_seed=44,
        train_batches=(
            TrainBatch(generation=1, epoch=1, batch_index=1, task_ids=("task-a",)),
            TrainBatch(generation=2, epoch=2, batch_index=1, task_ids=("task-a",)),
        ),
        train_schedule_sha256="1" * 64,
        validation_generations=(0,),
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
        test_candidate_attempts=3,
        validation_trial_hours=12,
        test_trial_hours=12,
        validation_candidate_attempts=3,
        configured_trial_hours=14,
    )
    paths = HarnessEvolutionPaths(tmp_path / "artifacts", "demo")
    repository.materialize(h0.commit, paths.generation(0) / "runtime")
    repository.materialize(h1.commit, paths.generation(1) / "runtime")
    repository.materialize(h1.commit, paths.generation(2) / "runtime")
    score_h0 = AggregateScore(
        official_score=1.5,
        raw_zero_sensitive_score=1.5,
        task_scores={"task-b": 1.5},
        raw_task_scores={"task-b": 1.5},
        attempt_rewards={"task-b": (1.5, 1.5, 1.5)},
    )
    run_summary_path = tmp_path / "validation-global.json"
    run_summary_path.write_text(
        RunSummary.model_validate(
            {
                "job_name": "validation-global",
                "enable_cache": True,
                "used_api_gateway": True,
                "trial_count": 4,
                "stats": {"n_errored_trials": 0},
                "tasks": [
                    {
                        "task_name": "task-b",
                        "baseline": None,
                        "candidates": [
                            {
                                "trial_name": f"candidate-{attempt}",
                                "agent": "offline-harness-h0",
                                "trial_uri": "file:///tmp/candidate",
                                "artifact": "candidate.json",
                                "reward": score_h0.official_score,
                            }
                            for attempt in range(3)
                        ],
                    }
                ],
            }
        ).model_dump_json(),
        encoding="utf-8",
    )
    execute_validation = MagicMock(return_value=run_summary_path)
    validation_baseline = MagicMock(return_value=tmp_path / "validation-baseline.json")
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.execute_baseline",
        validation_baseline,
    )
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.execute_validation_campaign",
        execute_validation,
    )
    generated = MagicMock()
    monkeypatch.setattr(
        "perfrace.evolution.orchestrator.generate_frozen_test_artifacts",
        generated,
    )
    state = EvolutionState(
        experiment_name="demo",
        config_sha256="a" * 64,
        stage=EvolutionStage.VALIDATING,
        active_generation=2,
        generations=(
            GenerationRecord(
                generation=0,
                commit=h0.commit,
                source_sha256=h0.source_sha256,
            ),
            GenerationRecord(
                generation=1,
                commit=h1.commit,
                source_sha256=h1.source_sha256,
            ),
            GenerationRecord(
                generation=2,
                commit=h1.commit,
                source_sha256=h1.source_sha256,
            ),
        ),
        split_manifest_path=paths.splits / "manifest.json",
    )
    prepared = PreparedEvolution(loaded, plan, paths, state, repository)

    completed = run_validation_and_select(prepared)

    assert completed.state.stage == EvolutionStage.TEST_READY
    assert completed.state.active_generation == 2
    generated.assert_called_once()
    assert execute_validation.call_count == 1
    assert validation_baseline.call_count == 1
    assert validation_baseline.call_args.kwargs["task_ids"] == ("task-b",)
    assert execute_validation.call_args.kwargs["n_concurrent_trials"] == 24
    [candidate] = execute_validation.call_args.kwargs["candidates"]
    assert candidate.generation == 0
    assert candidate.agent_name == "offline-harness-h0"
    assert not paths.validation_generation(1).exists()
    assert not paths.validation_generation(2).exists()
    assert read_model(paths.validation_generation(0) / "score.json", AggregateScore) == score_h0
    assert paths.frozen_runtime.joinpath("runtime.py").read_text() == (
        "GENERATION = 0\n"
    )
