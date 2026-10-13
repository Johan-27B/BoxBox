"""Resolve a harness-evolution experiment without creating artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from perfrace.evolution.config import LoadedHarnessEvolutionConfig
from perfrace.evolution.job_builder import resolved_run_config_sha256
from perfrace.evolution.runtime_repository import hash_source_tree
from perfrace.evolution.split import build_split_manifest, build_train_schedule
from perfrace.evolution.types import ResolvedEvolutionPlan
from perfrace.run.config import REPO_ROOT, load_run
from perfrace.evolution.loader import validate_harness_source
from perfrace.run.types import PerfRaceConfig


def controller_source_sha256() -> str:
    """Hash controller, verifier, vendored Harbor, and dependency identities."""
    digest = hashlib.sha256()
    roots = (
        REPO_ROOT / "perfrace",
        REPO_ROOT / "vendor" / "harbor" / "src" / "harbor",
        REPO_ROOT / "boxbox",
    )
    files: list[Path] = []
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.relative_to(root).parts
            and path.suffix != ".pyc"
        )
    files.extend((REPO_ROOT / "pyproject.toml", REPO_ROOT / "uv.lock"))
    for path in sorted(files, key=lambda item: item.relative_to(REPO_ROOT).as_posix()):
        relative = path.relative_to(REPO_ROOT).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def resolve_evolution_plan(
    loaded: LoadedHarnessEvolutionConfig,
) -> ResolvedEvolutionPlan:
    """Validate all static inputs and calculate the configured offline budget."""
    config = loaded.config
    split = build_split_manifest(config)
    train_batches, train_schedule_sha256 = build_train_schedule(config, split)
    if not config.protocol.trust_evolved_code:
        raise ValueError("Full harness evolution requires protocol.trust_evolved_code: true")
    if not (config.harness_source / "__init__.py").is_file():
        raise ValueError(f"Harness source must contain __init__.py: {config.harness_source}")
    harness_source_sha256 = hash_source_tree(config.harness_source)
    validate_harness_source(
        config.harness_source, identity=f"runtime0_{harness_source_sha256[:16]}"
    )
    base_run = load_run(config.base_run_config)
    if len(base_run.job.agents) != 1:
        raise ValueError("Harness evolution base run config must define one agent template")
    for task_id in (*split.train, *split.validation, *split.test):
        task_dir = config.instance_root / task_id
        if not task_dir.is_dir():
            raise ValueError(f"Installed PerfRace instance is missing: {task_dir}")
    task_checksums: dict[str, str] = {}
    for task_id in (*split.train, *split.validation, *split.test):
        task_config = PerfRaceConfig.from_task_dir(
            config.instance_root / task_id,
            include_checksum=True,
        )
        if task_config is None or task_config.task_checksum is None:
            raise ValueError(f"Installed PerfRace instance has no usable checksum: {task_id}")
        task_checksums[task_id] = task_config.task_checksum
    protocol = config.protocol
    validation_generations = protocol.validation_generations or tuple(
        range(0, protocol.generations + 1)
    )
    train_candidate_attempts = sum(
        len(batch.task_ids) * protocol.train_attempts for batch in train_batches
    )
    test_candidate_attempts = len(split.test) * protocol.test_attempts
    validation_candidate_attempts = (
        len(validation_generations) * len(split.validation) * protocol.validation_attempts
    )
    validation_seconds = validation_candidate_attempts * protocol.validation_timeout_sec
    test_seconds = test_candidate_attempts * protocol.test_timeout_sec
    configured_seconds = train_candidate_attempts * protocol.train_timeout_sec + validation_seconds
    return ResolvedEvolutionPlan(
        experiment_name=config.experiment_name,
        harness_source_sha256=harness_source_sha256,
        base_run_config_sha256=resolved_run_config_sha256(config.base_run_config),
        controller_source_sha256=controller_source_sha256(),
        task_checksums=task_checksums,
        split=split,
        generations=protocol.generations,
        train_batch_size=protocol.train_batch_size or len(split.train),
        train_batch_seed=protocol.train_batch_seed,
        train_batches=train_batches,
        train_schedule_sha256=train_schedule_sha256,
        validation_generations=validation_generations,
        train_attempts=protocol.train_attempts,
        validation_attempts=protocol.validation_attempts,
        test_attempts=protocol.test_attempts,
        train_timeout_sec=protocol.train_timeout_sec,
        validation_timeout_sec=protocol.validation_timeout_sec,
        test_timeout_sec=protocol.test_timeout_sec,
        debugger_max_workers=config.concurrency.debugger_max_workers,
        train_concurrency=config.concurrency.train,
        baseline_concurrency=config.concurrency.baseline,
        validation_concurrency=config.concurrency.validation,
        test_concurrency=config.concurrency.test,
        train_candidate_attempts=train_candidate_attempts,
        validation_candidate_attempts=validation_candidate_attempts,
        test_candidate_attempts=test_candidate_attempts,
        validation_trial_hours=validation_seconds / 3600,
        test_trial_hours=test_seconds / 3600,
        configured_trial_hours=configured_seconds / 3600,
    )
