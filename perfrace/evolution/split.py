"""Deterministic task splitting for offline harness evolution."""

from __future__ import annotations

import hashlib
import json
import platform
import random
from pathlib import Path

from perfrace.evolution.config import HarnessEvolutionConfig
from perfrace.evolution.types import SplitManifest, TrainBatch


def build_split_manifest(config: HarnessEvolutionConfig) -> SplitManifest:
    """Validate the release universe and derive the configured split."""
    split = config.split
    catalog_ids = _load_catalog_ids(
        config.release_catalog,
        expected_total=split.expected_total,
    )
    if config.split_manifest is not None:
        return _load_frozen_split(
            config.split_manifest,
            catalog_path=config.release_catalog,
            catalog_ids=catalog_ids,
            train_count=split.train_count,
            validation_count=split.validation_count,
            test_count=split.test_count,
            allow_empty_test=split.allow_empty_test,
            train_seed=split.train_seed,
            validation_seed=split.validation_seed,
        )
    assert config.early_test_manifest is not None
    early_test = _load_early_test_ids(
        config.early_test_manifest,
        expected_count=split.early_test_count,
    )
    unknown_early = sorted(set(early_test) - set(catalog_ids))
    if unknown_early:
        raise ValueError(
            "Early test manifest contains IDs absent from the release catalog: "
            + ", ".join(unknown_early)
        )
    later = sorted(set(catalog_ids) - set(early_test))
    if split.train_count + split.validation_count > len(later) or (
        split.train_count + split.validation_count == len(later) and not split.allow_empty_test
    ):
        raise ValueError("Train and validation counts must leave later test instances")

    train = set(random.Random(split.train_seed).sample(later, split.train_count))
    validation_pool = sorted(set(later) - train)
    validation = set(
        random.Random(split.validation_seed).sample(
            validation_pool,
            split.validation_count,
        )
    )
    later_test = sorted(set(validation_pool) - validation)
    final_test = (*early_test, *later_test)

    return SplitManifest(
        catalog_sha256=hashlib.sha256(config.release_catalog.read_bytes()).hexdigest(),
        python_version=platform.python_version(),
        train_seed=split.train_seed,
        validation_seed=split.validation_seed,
        early_test=early_test,
        train=tuple(sorted(train)),
        validation=tuple(sorted(validation)),
        test=final_test,
    )


def _load_frozen_split(
    path: Path,
    *,
    catalog_path: Path,
    catalog_ids: tuple[str, ...],
    train_count: int,
    validation_count: int,
    test_count: int | None,
    allow_empty_test: bool,
    train_seed: int,
    validation_seed: int,
) -> SplitManifest:
    """Load one explicit split whose identity is bound to the release catalog."""
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read frozen split manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "catalog_sha256",
        "train",
        "validation",
        "test",
    }:
        raise ValueError(
            "Frozen split manifest must contain only schema_version, catalog_sha256, "
            "train, validation, and test"
        )
    if payload["schema_version"] != 1:
        raise ValueError(f"Unsupported frozen split schema: {payload['schema_version']}")
    catalog_sha256 = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    if payload["catalog_sha256"] != catalog_sha256:
        raise ValueError("Frozen split manifest catalog hash does not match release catalog")

    groups: dict[str, tuple[str, ...]] = {}
    for name in ("train", "validation", "test"):
        values = payload[name]
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            raise ValueError(f"Frozen split {name} must contain unique instance IDs")
        groups[name] = tuple(values)
    if len(groups["train"]) != train_count:
        raise ValueError(
            f"Frozen split Train count must be {train_count}; found {len(groups['train'])}"
        )
    if len(groups["validation"]) != validation_count:
        raise ValueError(
            "Frozen split Validation count must be "
            f"{validation_count}; found {len(groups['validation'])}"
        )
    if test_count is not None and len(groups["test"]) != test_count:
        raise ValueError(
            f"Frozen split Test count must be {test_count}; found {len(groups['test'])}"
        )
    if not groups["test"] and not allow_empty_test:
        raise ValueError("Frozen split must contain Test instances")
    train_set = set(groups["train"])
    validation_set = set(groups["validation"])
    test_set = set(groups["test"])
    if train_set & validation_set or train_set & test_set or validation_set & test_set:
        raise ValueError("Frozen split Train, Validation, and Test sets must be disjoint")
    selected = train_set | validation_set | test_set
    unknown = sorted(selected - set(catalog_ids))
    if unknown:
        raise ValueError(
            "Frozen split contains IDs absent from the release catalog: " + ", ".join(unknown)
        )
    return SplitManifest(
        catalog_sha256=catalog_sha256,
        source_manifest_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        python_version=platform.python_version(),
        train_seed=train_seed,
        validation_seed=validation_seed,
        early_test=(),
        train=groups["train"],
        validation=groups["validation"],
        test=groups["test"],
    )


def build_train_schedule(
    config: HarnessEvolutionConfig,
    split: SplitManifest,
) -> tuple[tuple[TrainBatch, ...], str]:
    """Build and hash complete deterministic Train epochs."""
    protocol = config.protocol
    batch_size = protocol.train_batch_size or len(split.train)
    full_batch = protocol.train_batch_size is None
    if len(split.train) % batch_size:
        raise ValueError("Train task count must be divisible by protocol.train_batch_size")
    batches_per_epoch = len(split.train) // batch_size
    if protocol.generations % batches_per_epoch:
        raise ValueError(
            "protocol.generations must contain an integer number of complete Train epochs"
        )
    epoch_count = protocol.generations // batches_per_epoch
    batches: list[TrainBatch] = []
    for epoch_index in range(epoch_count):
        ordered_tasks = list(split.train)
        if not full_batch:
            random.Random(protocol.train_batch_seed + epoch_index).shuffle(ordered_tasks)
        for batch_index in range(batches_per_epoch):
            start = batch_index * batch_size
            task_ids = tuple(ordered_tasks[start : start + batch_size])
            if len(set(task_ids)) != batch_size:
                raise ValueError("Train batches must contain distinct task IDs")
            batches.append(
                TrainBatch(
                    generation=len(batches) + 1,
                    epoch=epoch_index + 1,
                    batch_index=batch_index + 1,
                    task_ids=task_ids,
                )
            )
    exposures = {
        task_id: sum(task_id in batch.task_ids for batch in batches) for task_id in split.train
    }
    if len(set(exposures.values())) != 1:
        raise ValueError("Every Train task must have equal schedule exposure")
    payload = json.dumps(
        [batch.model_dump(mode="json") for batch in batches],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return tuple(batches), hashlib.sha256(payload).hexdigest()


def _load_catalog_ids(path: Path, *, expected_total: int) -> tuple[str, ...]:
    """Load immutable published instance identities from the release catalog."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read release catalog {path}: {exc}") from exc
    instances = payload.get("instances") if isinstance(payload, dict) else None
    if not isinstance(instances, dict):
        raise ValueError("Release catalog must contain an instances mapping")
    if len(instances) != expected_total:
        raise ValueError(
            f"Release catalog must contain exactly {expected_total} instances; "
            f"found {len(instances)}"
        )
    for instance_id, record in instances.items():
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("Release catalog contains an invalid instance ID")
        if not isinstance(record, dict):
            raise ValueError(f"Release record for {instance_id} must be a mapping")
        if record.get("instance") != instance_id:
            raise ValueError(f"Release record identity mismatch for {instance_id}")
        for field in ("image", "task_artifact"):
            value = record.get(field)
            if not isinstance(value, str) or "@sha256:" not in value:
                raise ValueError(
                    f"Release record {instance_id}.{field} must use an immutable digest"
                )
    return tuple(sorted(instances))


def _load_early_test_ids(path: Path, *, expected_count: int) -> tuple[str, ...]:
    """Load the fixed early-instance test manifest."""
    try:
        instance_ids = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Failed to read early test manifest {path}: {exc}") from exc
    if len(instance_ids) != expected_count:
        raise ValueError(
            f"Early test manifest must contain exactly {expected_count} IDs; "
            f"found {len(instance_ids)}"
        )
    if len(set(instance_ids)) != len(instance_ids):
        raise ValueError("Early test manifest contains duplicate instance IDs")
    return instance_ids
