from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfrace.run.config import RunConfigError
from perfrace.run.submission import load_submission_patches


def _submission(tmp_path: Path, lines: list[object]) -> Path:
    root = tmp_path / "submission"
    root.mkdir()
    (root / "predictions.jsonl").write_text(
        "\n".join(json.dumps(line) if not isinstance(line, str) else line for line in lines),
        encoding="utf-8",
    )
    return root


def test_load_submission_patches_materializes_inline_patches(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        [
            {
                "instance_id": "terminus-kira--fix-ocaml-gc",
                "model_patch": "diff --git a/a b/a\n",
            }
        ],
    )

    patches = load_submission_patches(submission, job_dir=tmp_path / "job")

    patch_path = tmp_path / "job" / "submission-patches" / "terminus-kira--fix-ocaml-gc.patch"
    assert patches == {"terminus-kira--fix-ocaml-gc": patch_path}
    assert patch_path.read_text(encoding="utf-8") == "diff --git a/a b/a\n"


def test_load_submission_patches_supports_selected_subset(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        [
            {"instance_id": "task-a", "model_patch": "diff --git a/a b/a\n"},
            {"instance_id": "task-b", "model_patch": "diff --git a/b b/b\n"},
        ],
    )

    patches = load_submission_patches(
        submission,
        job_dir=tmp_path / "job",
        selected_instance_ids={"task-b"},
    )

    assert sorted(patches) == ["task-b"]
    assert not (tmp_path / "job" / "submission-patches" / "task-a.patch").exists()


def test_load_submission_patches_requires_selected_instances(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        [{"instance_id": "task-a", "model_patch": "diff --git a/a b/a\n"}],
    )

    with pytest.raises(RunConfigError, match="missing selected instances: task-b"):
        load_submission_patches(
            submission,
            job_dir=tmp_path / "job",
            selected_instance_ids={"task-a", "task-b"},
        )


def test_load_submission_patches_rejects_duplicate_instances(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        [
            {"instance_id": "task-a", "model_patch": "diff --git a/a b/a\n"},
            {"instance_id": "task-a", "model_patch": "diff --git a/b b/b\n"},
        ],
    )

    with pytest.raises(RunConfigError, match="Duplicate submission instance_id"):
        load_submission_patches(submission, job_dir=tmp_path / "job")


def test_load_submission_patches_rejects_invalid_records(tmp_path: Path) -> None:
    submission = _submission(tmp_path, [{"instance_id": "Task-A", "model_patch": "diff"}])

    with pytest.raises(RunConfigError, match="lowercase"):
        load_submission_patches(submission, job_dir=tmp_path / "job")


def test_load_submission_patches_rejects_missing_file(tmp_path: Path) -> None:
    submission = tmp_path / "missing"

    with pytest.raises(RunConfigError, match="predictions file not found"):
        load_submission_patches(submission, job_dir=tmp_path / "job")
