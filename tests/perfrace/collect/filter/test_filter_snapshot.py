from __future__ import annotations

from perfrace.collect.filter._constants import MAX_SNAPSHOT_BYTES
from perfrace.collect.filter.snapshot import build_snapshot


def test_snapshot_is_bounded_and_deterministic() -> None:
    candidate = {
        "repo_url": "https://github.com/owner/project",
        "observed_revision": "a" * 40,
    }
    evidence = {
        "repository": "owner/project",
        "revision": "a" * 40,
        "tree": {
            "entry_count": 1000,
            "tracked_bytes": 1234,
            "paths": [f"src/path-{index}.ts" for index in range(1000)],
        },
        "licenses": [
            {
                "path": "LICENSE",
                "spdx": "MIT",
                "text": "license\n" * 10_000,
                "source_url": "https://github.com/owner/project/blob/rev/LICENSE",
            }
        ],
        "files": [
            {
                "path": "README.md",
                "text": "readme\n" * 10_000,
                "source_url": "https://github.com/owner/project/blob/rev/README.md",
            },
            {
                "path": "package.json",
                "text": '{"scripts":{"build":"tsc"}}',
                "source_url": "https://github.com/owner/project/blob/rev/package.json",
            },
        ],
        "file_errors": [],
    }

    first = build_snapshot(candidate, evidence)
    second = build_snapshot(candidate, evidence)

    assert first == second
    assert first["snapshot_bytes"] <= MAX_SNAPSHOT_BYTES
    assert first["tree"]["paths_truncated"] is True
    assert first["licenses"][0]["text_truncated"] is True
