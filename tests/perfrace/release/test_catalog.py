from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from perfrace.release import catalog as catalog_module
from perfrace.release.catalog import sync_release_catalog
from perfrace.release.publisher import ReleaseRecord


def _record(instance: str) -> ReleaseRecord:
    return ReleaseRecord(
        schema_version=1,
        instance=instance,
        image=f"ghcr.io/example/{instance}@sha256:" + "a" * 64,
        task_artifact=f"ghcr.io/example/{instance}@sha256:" + "b" * 64,
        task_content_hash="sha256:" + "c" * 64,
        archive_digest="sha256:" + "d" * 64,
        packaged_files=3,
        published_at="2026-09-07T00:00:00Z",
    )


def test_sync_release_catalog_writes_active_records(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    releases = root / ".releases"
    releases.mkdir(parents=True)
    record = _record("project--workload")
    (releases / "project--workload.json").write_text(
        json.dumps(asdict(record)),
        encoding="utf-8",
    )
    output = tmp_path / "catalog.json"

    instances = sync_release_catalog(root, output)

    assert instances == {"project--workload"}
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "instances": {"project--workload": asdict(record)},
    }


def test_sync_release_catalog_retries_when_records_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "instances"
    first = {"schema_version": 1, "instances": {"first--task": {}}}
    second = {
        "schema_version": 1,
        "instances": {"first--task": {}, "second--task": {}},
    }
    payloads = iter((first, second, second, second))
    monkeypatch.setattr(catalog_module, "_catalog_payload", lambda _root: next(payloads))
    output = tmp_path / "catalog.json"

    instances = sync_release_catalog(root, output)

    assert instances == {"first--task", "second--task"}
    assert json.loads(output.read_text(encoding="utf-8")) == second
