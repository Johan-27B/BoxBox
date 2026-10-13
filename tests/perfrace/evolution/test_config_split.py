import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from perfrace.evolution.config import (
    ConcurrencyConfig,
    EvolutionProtocolConfig,
    HarnessEvolutionConfig,
    LoadedHarnessEvolutionConfig,
    SplitConfig,
    load_harness_evolution_config,
)
from perfrace.evolution.planning import resolve_evolution_plan
from perfrace.evolution.split import build_split_manifest, build_train_schedule
from perfrace.evolution.types import SplitManifest
from perfrace.run.config import REPO_ROOT, load_run


def test_load_config_and_build_deterministic_100_instance_split(tmp_path: Path) -> None:
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
    harness_source = tmp_path / "runtime"
    (harness_source).mkdir(parents=True)
    (harness_source / "__init__.py").write_text(
        "class TerminusBoxBox:\n    setup = set_task_instruction = ensure_agent_session = configure_target_phase = run_until_trap = export_state = import_state = release_session = attach_session = restart_session = prepare_continuation = reconcile_review_trajectory = mark_harness_context_accepted = review = lambda *a, **k: None\n",
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
                "concurrency": {
                    "qualified_max": 40,
                    "debugger_max_workers": 40,
                    "train": 40,
                    "baseline": 40,
                    "validation": 40,
                    "test": 40,
                },
                "protocol": {
                    "generations": 24,
                    "train_batch_size": 5,
                    "train_batch_seed": 44,
                    "validation_generations": [0, 8, 16, 24],
                    "trust_evolved_code": True,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_harness_evolution_config(config_path)
    first = build_split_manifest(loaded.config)
    second = build_split_manifest(loaded.config)
    plan = resolve_evolution_plan(loaded)

    assert first == second
    assert len(first.early_test) == 32
    assert len(first.train) == 40
    assert len(first.validation) == 10
    assert len(first.test) == 50
    assert set(first.train).isdisjoint(first.validation)
    assert set(first.train).isdisjoint(first.test)
    assert set(first.validation).isdisjoint(first.test)
    assert set(first.early_test) <= set(first.test)
    assert len(plan.train_batches) == 24
    assert all(len(batch.task_ids) == 5 for batch in plan.train_batches)
    assert all(len(set(batch.task_ids)) == 5 for batch in plan.train_batches)
    assert Counter(
        task_id for batch in plan.train_batches for task_id in batch.task_ids
    ) == Counter({task_id: 3 for task_id in first.train})
    assert plan.validation_generations == (0, 8, 16, 24)
    assert plan.train_candidate_attempts == 120
    assert plan.validation_candidate_attempts == 120
    assert plan.test_candidate_attempts == 150
    assert plan.validation_trial_hours == 480
    assert plan.test_trial_hours == 600
    assert plan.configured_trial_hours == 570

    changed_protocol = loaded.config.protocol.model_copy(update={"train_batch_seed": 45})
    changed_seed = LoadedHarnessEvolutionConfig(
        source_path=loaded.source_path,
        source_sha256=loaded.source_sha256,
        config=loaded.config.model_copy(update={"protocol": changed_protocol}),
    )
    assert resolve_evolution_plan(changed_seed).train_schedule_sha256 != (
        plan.train_schedule_sha256
    )

    catalog.write_text(catalog.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed_manifest = resolve_evolution_plan(loaded)
    assert changed_manifest != plan
    assert changed_manifest.split.catalog_sha256 != plan.split.catalog_sha256


def test_build_split_manifest_loads_catalog_bound_frozen_partition(tmp_path: Path) -> None:
    instance_ids = ("train-a", "train-b", "validation", "test", "unused")
    catalog = tmp_path / "releases.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instances": {
                    instance_id: {
                        "instance": instance_id,
                        "image": f"ghcr.io/example/{instance_id}@sha256:{index:064x}",
                        "task_artifact": (
                            f"ghcr.io/example/{instance_id}@sha256:{index + 100:064x}"
                        ),
                    }
                    for index, instance_id in enumerate(instance_ids)
                },
            }
        ),
        encoding="utf-8",
    )
    split_path = tmp_path / "split.json"
    split_payload = {
        "schema_version": 1,
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "train": ["train-b", "train-a"],
        "validation": ["validation"],
        "test": ["test"],
    }
    split_path.write_text(json.dumps(split_payload), encoding="utf-8")
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="frozen",
        release_catalog=catalog,
        split_manifest=split_path,
        instance_root=tmp_path / "instances",
        base_run_config=tmp_path / "run.yaml",
        split=SplitConfig(
            expected_total=5,
            early_test_count=0,
            train_count=2,
            validation_count=1,
            test_count=1,
        ),
    )

    split = build_split_manifest(config)

    assert split.train == ("train-b", "train-a")
    assert split.validation == ("validation",)
    assert split.test == ("test",)
    assert split.early_test == ()
    assert split.source_manifest_sha256 == hashlib.sha256(split_path.read_bytes()).hexdigest()

    split_payload["catalog_sha256"] = "0" * 64
    split_path.write_text(json.dumps(split_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="catalog hash"):
        build_split_manifest(config)


def test_protocol_rejects_budget_without_final_delivery_headroom() -> None:
    with pytest.raises(ValidationError):
        EvolutionProtocolConfig(train_timeout_sec=300)


def test_protocol_rejects_invalid_validation_generation_schedule() -> None:
    with pytest.raises(ValidationError, match="unique, ordered"):
        EvolutionProtocolConfig(
            generations=8,
            validation_generations=(1, 8, 8),
        )
    with pytest.raises(ValidationError, match="within"):
        EvolutionProtocolConfig(
            generations=8,
            validation_generations=(1, 9),
        )


def test_build_train_schedule_supports_two_task_smoke(tmp_path: Path) -> None:
    config = HarnessEvolutionConfig(
        model_name="test-model",
        experiment_name="smoke",
        early_test_manifest=tmp_path / "early.txt",
        instance_root=tmp_path / "instances",
        base_run_config=tmp_path / "run.yaml",
        protocol=EvolutionProtocolConfig(
            generations=2,
            train_batch_size=1,
            train_batch_seed=44,
            validation_generations=(1, 2),
        ),
    )
    split = SplitManifest(
        catalog_sha256="a" * 64,
        python_version="3.13",
        train_seed=1,
        validation_seed=0,
        early_test=(),
        train=("eucalypt", "n8n"),
        validation=("jsonnet",),
        test=(),
    )

    batches, schedule_sha256 = build_train_schedule(config, split)

    assert [batch.generation for batch in batches] == [1, 2]
    assert [batch.epoch for batch in batches] == [1, 1]
    assert {batch.task_ids for batch in batches} == {("eucalypt",), ("n8n",)}
    assert len(schedule_sha256) == 64


def test_train_schedule_requires_complete_equal_exposure_epochs(tmp_path: Path) -> None:
    split = SplitManifest(
        catalog_sha256="a" * 64,
        python_version="3.13",
        train_seed=1,
        validation_seed=0,
        early_test=(),
        train=("a", "b", "c", "d"),
        validation=("validation",),
        test=(),
    )
    base = {
        "experiment_name": "invalid",
        "early_test_manifest": tmp_path / "early.txt",
        "instance_root": tmp_path / "instances",
        "base_run_config": tmp_path / "run.yaml",
    }
    uneven_batch = HarnessEvolutionConfig(
        model_name="test-model",
        **base,
        protocol=EvolutionProtocolConfig(generations=2, train_batch_size=3),
    )
    incomplete_epoch = HarnessEvolutionConfig(
        model_name="test-model",
        **base,
        protocol=EvolutionProtocolConfig(generations=3, train_batch_size=2),
    )

    with pytest.raises(ValueError, match="divisible"):
        build_train_schedule(uneven_batch, split)
    with pytest.raises(ValueError, match="complete Train epochs"):
        build_train_schedule(incomplete_epoch, split)


def test_split_allows_explicit_empty_test_for_two_task_canary() -> None:
    canary = SplitConfig(
        expected_total=2,
        early_test_count=0,
        train_count=1,
        validation_count=1,
        allow_empty_test=True,
    )

    assert canary.allow_empty_test is True


def test_split_rejects_implicit_empty_test() -> None:
    with pytest.raises(ValidationError, match="leave at least one"):
        SplitConfig(
            expected_total=2,
            early_test_count=0,
            train_count=1,
            validation_count=1,
        )


def test_concurrency_cannot_exceed_qualification() -> None:
    with pytest.raises(ValidationError, match="qualified_max"):
        ConcurrencyConfig(
            qualified_max=10,
            debugger_max_workers=10,
            train=11,
            baseline=10,
            validation=10,
            test=10,
        )
