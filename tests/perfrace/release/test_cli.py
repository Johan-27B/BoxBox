from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from perfrace.release.cli import export_releases
from perfrace.release.publisher import ReleaseRecord


def test_export_releases_writes_deterministic_catalog(tmp_path: Path) -> None:
    root = tmp_path / "instances"
    releases = root / ".releases"
    releases.mkdir(parents=True)
    record = ReleaseRecord(
        schema_version=1,
        instance="project--workload",
        image="ghcr.io/example/project@sha256:" + "a" * 64,
        task_artifact="ghcr.io/example/project@sha256:" + "b" * 64,
        task_content_hash="sha256:" + "c" * 64,
        archive_digest="sha256:" + "d" * 64,
        packaged_files=3,
        published_at="2026-09-02T00:00:00Z",
    )
    (releases / "project--workload.json").write_text(
        json.dumps(asdict(record)),
        encoding="utf-8",
    )
    output = tmp_path / "catalog.json"

    export_releases(instance_root=root, output=output)
    first = output.read_bytes()
    export_releases(instance_root=root, output=output)

    assert output.read_bytes() == first
    assert json.loads(first) == {
        "schema_version": 1,
        "instances": {"project--workload": asdict(record)},
    }
