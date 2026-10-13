"""Fail-closed orchestration for native offline harness evolution."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from perfrace.evolution.config import LoadedHarnessEvolutionConfig
from perfrace.evolution.debugger import run_generation_debugger
from perfrace.evolution.evidence import build_generation_evidence
from perfrace.evolution.execution import (
    execute_baseline,
    execute_stage,
    execute_validation_campaign,
    find_complete_baseline_summary,
    find_complete_summary,
    find_complete_validation_summary,
    generate_frozen_test_artifacts,
    validate_frozen_test_artifacts,
)
from perfrace.evolution.job_builder import validation_agent_name
from perfrace.evolution.evolver import run_evolver
from perfrace.evolution.meta import MetaAgentEndpoint
from perfrace.evolution.nexau_runner import validate_nexau_output
from perfrace.evolution.paths import HarnessEvolutionPaths
from perfrace.evolution.planning import resolve_evolution_plan
from perfrace.evolution.runtime_repository import (
    RuntimeRepository,
    hash_source_tree,
)
from perfrace.evolution.scoring import aggregate_run_summary, select_agent_summary
from perfrace.evolution.state import (
    read_evolution_state,
    read_model,
    write_model_atomic,
)
from perfrace.evolution.types import (
    AggregateScore,
    BaselineSpec,
    ChangeManifest,
    EvolutionStage,
    EvolutionState,
    GenerationEvidence,
    GenerationRecord,
    ResolvedEvolutionPlan,
    SelectionRecord,
    StageSpec,
    ValidationCampaignSpec,
    ValidationCandidateSpec,
)
from perfrace.run.types import PerfRaceConfig, RunSummary


@dataclass(frozen=True)
class PreparedEvolution:
    """Resolved paths, state, and runtime repository for one experiment."""

    loaded: LoadedHarnessEvolutionConfig
    plan: ResolvedEvolutionPlan
    paths: HarnessEvolutionPaths
    state: EvolutionState
    runtime_repository: RuntimeRepository


def prepare_experiment(
    loaded: LoadedHarnessEvolutionConfig,
    *,
    resume: bool,
) -> PreparedEvolution:
    """Initialize a new experiment or validate one durable resume point."""
    config = loaded.config
    plan = resolve_evolution_plan(loaded)
    paths = HarnessEvolutionPaths(config.artifact_root, config.experiment_name)
    if resume:
        state = read_evolution_state(paths.state)
        if state.config_sha256 != loaded.source_sha256:
            raise ValueError("Evolution config changed since the experiment was initialized")
        if read_model(paths.resolved_config, ResolvedEvolutionPlan) != plan:
            raise ValueError("Resolved evolution inputs changed since initialization")
        expected_batch_paths = {
            paths.train_batch(batch.generation): "".join(
                f"{task_id}\n" for task_id in batch.task_ids
            )
            for batch in plan.train_batches
        }
        batch_dir = paths.splits / "train-batches"
        actual_batch_paths = set(batch_dir.glob("generation-*.txt"))
        if actual_batch_paths != set(expected_batch_paths):
            raise ValueError("Persisted Train batch manifests do not match the resolved schedule")
        for batch_path, expected in expected_batch_paths.items():
            if batch_path.read_text(encoding="utf-8") != expected:
                raise ValueError(f"Persisted Train batch changed on resume: {batch_path}")
        repository = RuntimeRepository(paths.runtime_repository)
        return PreparedEvolution(loaded, plan, paths, state, repository)

    if paths.root.exists():
        raise FileExistsError(
            f"Evolution artifact directory already exists; use --resume: {paths.root}"
        )
    paths.root.mkdir(parents=True)
    write_model_atomic(paths.resolved_config, plan)
    paths.splits.mkdir()
    write_model_atomic(paths.splits / "manifest.json", plan.split)
    for name, instance_ids in (
        ("train.txt", plan.split.train),
        ("validation.txt", plan.split.validation),
        ("test.txt", plan.split.test),
    ):
        (paths.splits / name).write_text("\n".join(instance_ids) + "\n", encoding="utf-8")
    (paths.splits / "train-batches").mkdir()
    for batch in plan.train_batches:
        paths.train_batch(batch.generation).write_text(
            "".join(f"{task_id}\n" for task_id in batch.task_ids),
            encoding="utf-8",
        )

    repository = RuntimeRepository.initialize(config.harness_source, paths.runtime_repository)
    initial = repository.validate_head()
    generation_dir = paths.generation(0)
    runtime_dir = generation_dir / "runtime"
    generation_dir.mkdir(parents=True)
    repository.materialize_atomic(initial.commit, runtime_dir)
    write_model_atomic(
        generation_dir / "runtime.json",
        GenerationRecord(
            generation=0,
            commit=initial.commit,
            source_sha256=initial.source_sha256,
        ),
    )
    state = EvolutionState(
        experiment_name=config.experiment_name,
        config_sha256=loaded.source_sha256,
        stage=EvolutionStage.BASELINING,
        active_generation=0,
        generations=(
            GenerationRecord(
                generation=0,
                commit=initial.commit,
                source_sha256=initial.source_sha256,
            ),
        ),
        split_manifest_path=paths.splits / "manifest.json",
    )
    write_model_atomic(paths.state, state)
    return PreparedEvolution(loaded, plan, paths, state, repository)


def _all_task_ids(plan: ResolvedEvolutionPlan) -> tuple[str, ...]:
    return (*plan.split.train, *plan.split.validation, *plan.split.test)


def _validation_candidates(
    prepared: PreparedEvolution,
    records: dict[int, GenerationRecord],
) -> tuple[ValidationCandidateSpec, ...]:
    """Resolve and verify every predeclared frozen Validation runtime."""
    if not set(prepared.plan.validation_generations) <= set(records):
        raise ValueError("Validation schedule references an unavailable generation")
    candidates: list[ValidationCandidateSpec] = []
    for generation in prepared.plan.validation_generations:
        record = records[generation]
        runtime_dir = prepared.paths.generation(generation) / "runtime"
        prepared.runtime_repository.verify_materialized(record.commit, runtime_dir)
        candidates.append(
            ValidationCandidateSpec(
                generation=generation,
                agent_name=validation_agent_name(generation),
                harness_identity=record.commit,
                harness_source=runtime_dir.resolve(),
                harness_source_sha256=hash_source_tree(runtime_dir),
            )
        )
    return tuple(candidates)


def run_baseline_stage(
    prepared: PreparedEvolution,
    *,
    verifier_kwargs: dict[str, object] | None = None,
) -> PreparedEvolution:
    """Measure and cache accepted nop baselines for the Train split."""
    if prepared.state.stage != EvolutionStage.BASELINING:
        raise ValueError(f"Cannot run baseline from state {prepared.state.stage}")
    execute_baseline(
        prepared.loaded.config,
        task_ids=prepared.plan.split.train,
        n_concurrent_trials=prepared.plan.baseline_concurrency,
        stage_dir=prepared.paths.baseline,
        job_name=f"{prepared.loaded.config.experiment_name}-baseline",
        jobs_dir=prepared.paths.jobs,
        verifier_kwargs=verifier_kwargs,
    )
    updated_state = prepared.state.model_copy(update={"stage": EvolutionStage.TRAINING})
    write_model_atomic(prepared.paths.state, updated_state)
    return replace(prepared, state=updated_state)


def run_train_generation(
    prepared: PreparedEvolution,
    *,
    verifier_kwargs: dict[str, object] | None = None,
) -> PreparedEvolution:
    """Execute and persist the active generation's complete train stage."""
    state = prepared.state
    if state.stage != EvolutionStage.TRAINING:
        raise ValueError(f"Cannot run train stage from state {state.stage}")
    generation = state.active_generation
    record = next(
        (item for item in state.generations if item.generation == generation),
        None,
    )
    if record is None:
        raise ValueError(f"State has no record for active generation {generation}")
    iteration = generation + 1
    batch = next(
        (item for item in prepared.plan.train_batches if item.generation == iteration),
        None,
    )
    if batch is None:
        raise ValueError(f"Resolved plan has no Train batch for iteration {iteration}")
    generation_dir = prepared.paths.generation(generation)
    runtime_dir = generation_dir / "runtime"
    prepared.runtime_repository.verify_materialized(record.commit, runtime_dir)
    run_summary_path = execute_stage(
        prepared.loaded.config,
        stage="train",
        iteration=iteration,
        generation=generation,
        train_batch=batch,
        train_schedule_sha256=prepared.plan.train_schedule_sha256,
        task_ids=batch.task_ids,
        harness_source=runtime_dir,
        harness_identity=record.commit,
        attempts=prepared.plan.train_attempts,
        timeout_sec=prepared.plan.train_timeout_sec,
        n_concurrent_trials=prepared.plan.train_concurrency,
        stage_dir=generation_dir / "train",
        job_name=f"train-i{iteration}-h{generation}",
        jobs_dir=prepared.paths.jobs,
        verifier_kwargs=verifier_kwargs,
    )
    run_summary = RunSummary.model_validate_json(run_summary_path.read_text(encoding="utf-8"))
    score_path = generation_dir / "train" / "score.json"
    evidence_path = generation_dir / "train" / "evidence.json"
    write_model_atomic(
        score_path,
        aggregate_run_summary(
            run_summary,
            expected_attempts=prepared.plan.train_attempts,
        ),
    )
    write_model_atomic(
        evidence_path,
        build_generation_evidence(
            run_summary_path,
            batch=batch,
            harness_generation=generation,
            train_schedule_sha256=prepared.plan.train_schedule_sha256,
            expected_attempts=prepared.plan.train_attempts,
        ),
    )
    updated_record = record.model_copy(
        update={
            "train_run_dir": run_summary_path.parent,
            "train_score_path": score_path,
            "analysis_dir": generation_dir / "analysis",
        }
    )
    updated_generations = tuple(
        updated_record if item.generation == generation else item for item in state.generations
    )
    updated_state = state.model_copy(
        update={
            "stage": EvolutionStage.ANALYZING,
            "generations": updated_generations,
        }
    )
    write_model_atomic(prepared.paths.state, updated_state)
    return replace(prepared, state=updated_state)


def run_analysis_stage(
    prepared: PreparedEvolution,
    *,
    endpoint: MetaAgentEndpoint,
) -> PreparedEvolution:
    """Run debugger reports and advance to the iteration's evolution step."""
    state = prepared.state
    if state.stage != EvolutionStage.ANALYZING:
        raise ValueError(f"Cannot run analysis from state {state.stage}")
    generation = state.active_generation
    generation_dir = prepared.paths.generation(generation)
    previous_overview = (
        prepared.paths.generation(generation - 1) / "analysis" / "overview.md"
        if generation > 0
        else None
    )
    run_generation_debugger(
        evidence_path=generation_dir / "train" / "evidence.json",
        score_path=generation_dir / "train" / "score.json",
        experiment_root=prepared.paths.root,
        output_dir=generation_dir / "analysis",
        endpoint=endpoint,
        previous_overview_path=previous_overview,
        max_workers=prepared.plan.debugger_max_workers,
    )
    updated_state = state.model_copy(update={"stage": EvolutionStage.EVOLVING})
    write_model_atomic(prepared.paths.state, updated_state)
    return replace(prepared, state=updated_state)


def run_evolution_stage(
    prepared: PreparedEvolution,
    *,
    endpoint: MetaAgentEndpoint,
) -> PreparedEvolution:
    """Run one lineage revision and materialize the next generation."""
    state = prepared.state
    if state.stage != EvolutionStage.EVOLVING:
        raise ValueError(f"Cannot run evolution from state {state.stage}")
    generation = state.active_generation
    if generation >= prepared.plan.generations:
        raise ValueError("Final generation cannot produce a successor")
    iteration = generation + 1
    record = next(item for item in state.generations if item.generation == generation)
    if record.train_run_dir is None:
        raise ValueError(f"Generation h{generation} has no completed Train run directory")
    generation_dir = prepared.paths.generation(generation)
    outcome = run_evolver(
        repository=prepared.runtime_repository,
        experiment_root=prepared.paths.root,
        generation_dir=generation_dir,
        iteration=iteration,
        parent_generation=generation,
        parent_commit=record.commit,
        overview_path=generation_dir / "analysis" / "overview.md",
        detail_dir=generation_dir / "analysis" / "detail",
        endpoint=endpoint,
        # Match Harness Scaling: expose the completed job artifact directory,
        # including all trial trajectories, terminal captures, measurements,
        # and logs, without exposing the ephemeral target workspace.
        extra_read_roots=(record.train_run_dir.parent,),
    )
    updated_record = record.model_copy(
        update={
            "evolve_dir": generation_dir / "evolve",
            "successor_commit": outcome.snapshot.commit,
        }
    )
    next_generation = generation + 1
    next_generation_dir = prepared.paths.generation(next_generation)
    next_record = GenerationRecord(
        generation=next_generation,
        commit=outcome.snapshot.commit,
        source_sha256=outcome.snapshot.source_sha256,
    )
    runtime_dir = next_generation_dir / "runtime"
    runtime_marker = next_generation_dir / "runtime.json"
    next_generation_dir.mkdir(parents=True, exist_ok=True)
    prepared.runtime_repository.materialize_atomic(
        outcome.snapshot.commit,
        runtime_dir,
    )
    if runtime_marker.is_file():
        if read_model(runtime_marker, GenerationRecord) != next_record:
            raise ValueError(
                f"Materialized generation does not match evolve outcome: {next_generation_dir}"
            )
    else:
        write_model_atomic(runtime_marker, next_record)
    generations = tuple(
        updated_record if item.generation == generation else item for item in state.generations
    ) + (next_record,)
    updated_state = state.model_copy(
        update={
            "stage": EvolutionStage.TRAINING,
            "active_generation": next_generation,
            "generations": generations,
        }
    )
    write_model_atomic(prepared.paths.state, updated_state)
    return replace(prepared, state=updated_state)


def run_validation_and_select(
    prepared: PreparedEvolution,
    *,
    verifier_kwargs: dict[str, object] | None = None,
) -> PreparedEvolution:
    """Evaluate fixed validation generations and freeze the best runtime."""
    if prepared.state.stage != EvolutionStage.VALIDATING:
        raise ValueError(f"Cannot run validation from state {prepared.state.stage}")
    records = {record.generation: record for record in prepared.state.generations}
    candidates = _validation_candidates(prepared, records)
    execute_baseline(
        prepared.loaded.config,
        task_ids=prepared.plan.split.validation,
        n_concurrent_trials=prepared.plan.baseline_concurrency,
        stage_dir=prepared.paths.validation / "baseline",
        job_name=f"{prepared.loaded.config.experiment_name}-validation-baseline",
        jobs_dir=prepared.paths.jobs,
        verifier_kwargs=verifier_kwargs,
    )
    run_summary_path = execute_validation_campaign(
        prepared.loaded.config,
        candidates=candidates,
        task_ids=prepared.plan.split.validation,
        attempts=prepared.plan.validation_attempts,
        timeout_sec=prepared.plan.validation_timeout_sec,
        n_concurrent_trials=prepared.plan.validation_concurrency,
        stage_dir=prepared.paths.validation,
        job_name="validation-global",
        jobs_dir=prepared.paths.jobs,
        verifier_kwargs=verifier_kwargs,
    )
    run_summary = RunSummary.model_validate_json(run_summary_path.read_text(encoding="utf-8"))
    scores: dict[int, AggregateScore] = {}
    for candidate in candidates:
        generation = candidate.generation
        validation_dir = prepared.paths.validation_generation(generation)
        score_path = validation_dir / "score.json"
        score = aggregate_run_summary(
            select_agent_summary(run_summary, candidate.agent_name),
            expected_attempts=prepared.plan.validation_attempts,
        )
        write_model_atomic(score_path, score)
        scores[generation] = score
    selected_generation = min(
        scores,
        key=lambda generation: (
            -scores[generation].official_score,
            generation,
        ),
    )
    selected_record = next(
        item for item in prepared.state.generations if item.generation == selected_generation
    )
    selection = SelectionRecord(
        selected_generation=selected_generation,
        selected_commit=selected_record.commit,
        validation_scores=scores,
    )
    write_model_atomic(prepared.paths.selection, selection)
    frozen_marker = GenerationRecord(
        generation=selected_generation,
        commit=selected_record.commit,
        source_sha256=selected_record.source_sha256,
    )
    prepared.runtime_repository.materialize_atomic(
        selected_record.commit,
        prepared.paths.frozen_runtime,
    )
    if prepared.paths.frozen_runtime_marker.is_file():
        if read_model(prepared.paths.frozen_runtime_marker, GenerationRecord) != frozen_marker:
            raise ValueError("Frozen runtime marker does not match validation selection")
    else:
        write_model_atomic(prepared.paths.frozen_runtime_marker, frozen_marker)
    generate_frozen_test_artifacts(
        config=prepared.loaded.config,
        config_source_path=prepared.loaded.source_path,
        config_source_sha256=prepared.loaded.source_sha256,
        plan=prepared.plan,
        paths=prepared.paths,
        selection=selection,
        selected_record=selected_record,
    )
    updated_state = prepared.state.model_copy(
        update={
            "stage": EvolutionStage.TEST_READY,
            "active_generation": prepared.plan.generations,
            "selection_path": prepared.paths.selection,
        }
    )
    write_model_atomic(prepared.paths.state, updated_state)
    return replace(prepared, state=updated_state)


def validate_completed_experiment(prepared: PreparedEvolution) -> SelectionRecord:
    """Validate every durable stage before reporting completion."""
    if prepared.state.stage not in {EvolutionStage.TEST_READY, EvolutionStage.COMPLETE}:
        raise ValueError("Experiment state is not complete")
    if prepared.state.selection_path != prepared.paths.selection:
        raise ValueError("Completed state selection path does not match experiment paths")
    records = {record.generation: record for record in prepared.state.generations}
    expected_generations = set(range(0, prepared.plan.generations + 1))
    if set(records) != expected_generations:
        raise ValueError("Completed state does not contain every configured generation")
    if prepared.state.active_generation != prepared.plan.generations:
        raise ValueError("Completed state does not point at the final generated harness")
    task_names: dict[str, str] = {}
    baseline_configs: dict[str, PerfRaceConfig] = {}
    for task_id in _all_task_ids(prepared.plan):
        task_config = PerfRaceConfig.from_task_dir(
            prepared.loaded.config.instance_root / task_id,
            include_checksum=True,
        )
        if (
            task_config is None
            or task_config.task_checksum != prepared.plan.task_checksums[task_id]
            or task_config.cache_fields is None
        ):
            raise ValueError(f"Cannot validate completed task identity: {task_id}")
        if task_config.task_name in baseline_configs:
            raise ValueError(f"Duplicate completed task name: {task_config.task_name}")
        task_names[task_id] = task_config.task_name
        baseline_configs[task_config.task_name] = task_config
    baseline_spec = BaselineSpec(
        task_ids=prepared.plan.split.train,
        task_checksums={
            task_id: prepared.plan.task_checksums[task_id] for task_id in prepared.plan.split.train
        },
        base_run_config_sha256=prepared.plan.base_run_config_sha256,
        controller_source_sha256=prepared.plan.controller_source_sha256,
        n_concurrent_trials=prepared.plan.baseline_concurrency,
        job_name=f"{prepared.loaded.config.experiment_name}-baseline",
    )
    if read_model(prepared.paths.baseline / "stage.json", BaselineSpec) != baseline_spec:
        raise ValueError("Baseline stage identity is inconsistent")
    if (
        find_complete_baseline_summary(
            jobs_dir=prepared.paths.jobs,
            job_name=baseline_spec.job_name,
            expected_configs={
                task_names[task_id]: baseline_configs[task_names[task_id]]
                for task_id in prepared.plan.split.train
            },
            n_concurrent_trials=baseline_spec.n_concurrent_trials,
        )
        is None
    ):
        raise ValueError("Experiment has no complete accepted baseline cache")
    validation_name_set = {task_names[task_id] for task_id in prepared.plan.split.validation}
    train_batches = {batch.generation: batch for batch in prepared.plan.train_batches}
    expected_iterations = set(range(1, prepared.plan.generations + 1))
    if set(train_batches) != expected_iterations:
        raise ValueError("Resolved Train schedule does not contain every iteration")
    validation_generations = set(prepared.plan.validation_generations)
    validation_scores: dict[int, AggregateScore] = {}
    for generation in sorted(records):
        record = records[generation]
        generation_dir = prepared.paths.generation(generation)
        runtime_dir = generation_dir / "runtime"
        runtime_marker = read_model(generation_dir / "runtime.json", GenerationRecord)
        if (
            runtime_marker.generation != record.generation
            or runtime_marker.commit != record.commit
            or runtime_marker.source_sha256 != record.source_sha256
        ):
            raise ValueError(f"Generation {generation} runtime marker is inconsistent")
        prepared.runtime_repository.verify_materialized(record.commit, runtime_dir)
    for iteration in range(1, prepared.plan.generations + 1):
        generation = iteration - 1
        record = records[generation]
        next_record = records[iteration]
        batch = train_batches[iteration]
        train_name_set = {task_names[task_id] for task_id in batch.task_ids}
        generation_dir = prepared.paths.generation(generation)
        runtime_dir = generation_dir / "runtime"
        train_spec = StageSpec(
            stage="train",
            iteration=iteration,
            generation=generation,
            epoch=batch.epoch,
            batch_index=batch.batch_index,
            train_schedule_sha256=prepared.plan.train_schedule_sha256,
            task_ids=batch.task_ids,
            task_checksums={
                task_id: prepared.plan.task_checksums[task_id] for task_id in batch.task_ids
            },
            harness_identity=record.commit,
            harness_source_sha256=hash_source_tree(runtime_dir),
            base_run_config_sha256=prepared.plan.base_run_config_sha256,
            controller_source_sha256=prepared.plan.controller_source_sha256,
            attempts=prepared.plan.train_attempts,
            timeout_sec=prepared.plan.train_timeout_sec,
            n_concurrent_trials=prepared.plan.train_concurrency,
            effective_concurrency=min(
                prepared.plan.train_concurrency,
                len(batch.task_ids) * prepared.plan.train_attempts,
            ),
            job_name=f"train-i{iteration}-h{generation}",
        )
        if read_model(generation_dir / "train" / "stage.json", StageSpec) != train_spec:
            raise ValueError(f"Generation {generation} train stage identity is inconsistent")
        train_summary_path = find_complete_summary(
            jobs_dir=prepared.paths.jobs,
            job_name=f"train-i{iteration}-h{generation}",
            expected_task_names=train_name_set,
            attempts=prepared.plan.train_attempts,
            harness_identity=record.commit,
            timeout_sec=prepared.plan.train_timeout_sec,
            n_concurrent_trials=prepared.plan.train_concurrency,
        )
        if train_summary_path is None:
            raise ValueError(f"Generation {generation} has no complete train summary")
        train_summary = RunSummary.model_validate_json(
            train_summary_path.read_text(encoding="utf-8")
        )
        train_score = aggregate_run_summary(
            train_summary,
            expected_attempts=prepared.plan.train_attempts,
        )
        if read_model(generation_dir / "train" / "score.json", AggregateScore) != train_score:
            raise ValueError(f"Generation {generation} train score is inconsistent")
        evidence = read_model(
            generation_dir / "train" / "evidence.json",
            GenerationEvidence,
        )
        if (
            evidence.iteration != iteration
            or evidence.generation != generation
            or evidence.epoch != batch.epoch
            or evidence.batch_index != batch.batch_index
            or evidence.task_ids != batch.task_ids
            or evidence.train_schedule_sha256 != prepared.plan.train_schedule_sha256
            or {task.task_name for task in evidence.tasks} != train_name_set
        ):
            raise ValueError(f"Generation {generation} evidence index is inconsistent")
        analysis_dir = generation_dir / "analysis"
        if not validate_nexau_output(analysis_dir / "overview"):
            raise ValueError(f"Generation {generation} overview output is incomplete")
        expected_overview = (
            f"{(analysis_dir / 'overview' / 'result.md').read_text(encoding='utf-8').rstrip()}\n"
        )
        if (analysis_dir / "overview.md").read_text(encoding="utf-8") != expected_overview:
            raise ValueError(f"Generation {generation} overview is inconsistent")
        for task in evidence.tasks:
            slug = "".join(
                character if character.isalnum() or character in "._-" else "_"
                for character in task.task_name
            )
            if not validate_nexau_output(analysis_dir / "detail" / slug):
                raise ValueError(
                    f"Generation {generation} debugger output is incomplete for {task.task_name}"
                )
        evolve_dir = generation_dir / "evolve"
        if not validate_nexau_output(evolve_dir):
            raise ValueError(f"Iteration {iteration} evolve output is incomplete")
        manifest = read_model(evolve_dir / "change_manifest.json", ChangeManifest)
        outcome = json.loads((evolve_dir / "outcome.json").read_text(encoding="utf-8"))
        if (
            manifest.iteration != iteration
            or manifest.parent_commit != record.commit
            or outcome.get("iteration") != iteration
            or outcome.get("parent_generation") != generation
            or outcome.get("result_generation") != iteration
            or outcome.get("parent_commit") != record.commit
            or outcome.get("result_commit") != next_record.commit
            or record.successor_commit != next_record.commit
        ):
            raise ValueError(f"Iteration {iteration} evolve lineage is inconsistent")
        validation_dir = prepared.paths.validation_generation(generation)
        if generation not in validation_generations and validation_dir.exists():
            raise ValueError(
                f"Generation {generation} has Validation artifacts outside the fixed schedule"
            )
    validation_baseline_spec = BaselineSpec(
        task_ids=prepared.plan.split.validation,
        task_checksums={
            task_id: prepared.plan.task_checksums[task_id]
            for task_id in prepared.plan.split.validation
        },
        base_run_config_sha256=prepared.plan.base_run_config_sha256,
        controller_source_sha256=prepared.plan.controller_source_sha256,
        n_concurrent_trials=prepared.plan.baseline_concurrency,
        job_name=f"{prepared.loaded.config.experiment_name}-validation-baseline",
    )
    if (
        read_model(prepared.paths.validation / "baseline" / "stage.json", BaselineSpec)
        != validation_baseline_spec
    ):
        raise ValueError("Validation baseline stage identity is inconsistent")
    if (
        find_complete_baseline_summary(
            jobs_dir=prepared.paths.jobs,
            job_name=validation_baseline_spec.job_name,
            expected_configs={
                task_names[task_id]: baseline_configs[task_names[task_id]]
                for task_id in prepared.plan.split.validation
            },
            n_concurrent_trials=validation_baseline_spec.n_concurrent_trials,
        )
        is None
    ):
        raise ValueError("Experiment has no complete accepted Validation baseline cache")
    candidates = _validation_candidates(prepared, records)
    validation_spec = ValidationCampaignSpec(
        candidates=candidates,
        task_ids=prepared.plan.split.validation,
        task_checksums={
            task_id: prepared.plan.task_checksums[task_id]
            for task_id in prepared.plan.split.validation
        },
        base_run_config_sha256=prepared.plan.base_run_config_sha256,
        controller_source_sha256=prepared.plan.controller_source_sha256,
        attempts=prepared.plan.validation_attempts,
        timeout_sec=prepared.plan.validation_timeout_sec,
        n_concurrent_trials=prepared.plan.validation_concurrency,
        effective_concurrency=min(
            prepared.plan.validation_concurrency,
            len(candidates)
            * len(prepared.plan.split.validation)
            * prepared.plan.validation_attempts,
        ),
        job_name="validation-global",
    )
    if (
        read_model(prepared.paths.validation / "stage.json", ValidationCampaignSpec)
        != validation_spec
    ):
        raise ValueError("Global Validation stage identity is inconsistent")
    validation_summary_path = find_complete_validation_summary(
        jobs_dir=prepared.paths.jobs,
        spec=validation_spec,
        expected_task_names=validation_name_set,
    )
    if validation_summary_path is None:
        raise ValueError("Global Validation has no complete run summary")
    validation_summary = RunSummary.model_validate_json(
        validation_summary_path.read_text(encoding="utf-8")
    )
    for candidate in candidates:
        validation_score = aggregate_run_summary(
            select_agent_summary(validation_summary, candidate.agent_name),
            expected_attempts=prepared.plan.validation_attempts,
        )
        validation_dir = prepared.paths.validation_generation(candidate.generation)
        if read_model(validation_dir / "score.json", AggregateScore) != validation_score:
            raise ValueError(f"Generation {candidate.generation} validation score is inconsistent")
        validation_scores[candidate.generation] = validation_score
    if set(validation_scores) != validation_generations:
        raise ValueError("Completed Validation scores do not match the fixed generation schedule")
    selection = read_model(prepared.paths.selection, SelectionRecord)
    if selection.validation_scores != validation_scores:
        raise ValueError("Selection does not contain the validated generation scores")
    expected_selection = min(
        validation_scores,
        key=lambda generation: (
            -validation_scores[generation].official_score,
            generation,
        ),
    )
    if selection.selected_generation != expected_selection:
        raise ValueError("Selection is not the deterministic validation winner")
    selected_record = next(
        (
            record
            for record in prepared.state.generations
            if record.generation == selection.selected_generation
        ),
        None,
    )
    if selected_record is None or selected_record.commit != selection.selected_commit:
        raise ValueError("Selection does not match a recorded runtime generation")
    marker = read_model(prepared.paths.frozen_runtime_marker, GenerationRecord)
    if (
        marker.generation != selected_record.generation
        or marker.commit != selected_record.commit
        or marker.source_sha256 != selected_record.source_sha256
    ):
        raise ValueError("Frozen runtime marker does not match the selected generation")
    prepared.runtime_repository.verify_materialized(
        selected_record.commit,
        prepared.paths.frozen_runtime,
    )
    validate_frozen_test_artifacts(prepared.paths.root, require_unrun=True)
    return selection


def validate_iteration_target(prepared: PreparedEvolution, iterations: int) -> None:
    """Reject cumulative iteration targets inconsistent with durable progress."""
    if iterations < 1 or iterations > prepared.plan.generations:
        raise ValueError(
            f"Iteration target must be between 1 and {prepared.plan.generations}: {iterations}"
        )
    in_flight = prepared.state.stage in {EvolutionStage.ANALYZING, EvolutionStage.EVOLVING}
    minimum_target = prepared.state.active_generation + (1 if in_flight else 0)
    if iterations < minimum_target:
        raise ValueError(
            f"Iteration target {iterations} is behind durable progress {minimum_target}"
        )
    if (
        prepared.state.stage
        in {
            EvolutionStage.VALIDATING,
            EvolutionStage.TEST_READY,
            EvolutionStage.COMPLETE,
        }
        and iterations != prepared.plan.generations
    ):
        raise ValueError("Validation state requires the configured maximum iteration target")


def run_evolution(
    prepared: PreparedEvolution,
    *,
    iterations: int,
    endpoint: MetaAgentEndpoint,
    verifier_kwargs: dict[str, object],
    stop_after_training: bool = False,
) -> PreparedEvolution:
    """Drive the durable state machine to one cumulative harness target."""
    validate_iteration_target(prepared, iterations)
    current = prepared
    while current.state.stage not in {EvolutionStage.TEST_READY, EvolutionStage.COMPLETE}:
        if current.state.stage == EvolutionStage.BASELINING:
            current = run_baseline_stage(current, verifier_kwargs=verifier_kwargs)
        elif current.state.stage == EvolutionStage.TRAINING:
            if current.state.active_generation == iterations:
                if iterations < current.plan.generations or stop_after_training:
                    return current
                updated_state = current.state.model_copy(
                    update={"stage": EvolutionStage.VALIDATING}
                )
                write_model_atomic(current.paths.state, updated_state)
                current = replace(current, state=updated_state)
                continue
            current = run_train_generation(current, verifier_kwargs=verifier_kwargs)
        elif current.state.stage == EvolutionStage.ANALYZING:
            current = run_analysis_stage(current, endpoint=endpoint)
        elif current.state.stage == EvolutionStage.EVOLVING:
            current = run_evolution_stage(current, endpoint=endpoint)
        elif current.state.stage == EvolutionStage.VALIDATING:
            current = run_validation_and_select(
                current,
                verifier_kwargs=verifier_kwargs,
            )
        else:
            raise ValueError(f"Unsupported evolution stage: {current.state.stage}")
    return current
