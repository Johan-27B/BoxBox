"""Load local patch-mode submissions for PerfRace runs.

A submission is a local directory containing a fixed-format ``predictions.jsonl``
file. Each non-empty line is a JSON object:

    {"instance_id": "eucalypt--eval-speed", "model_patch": "diff --git ..."}

The loader validates this file and materializes each inline patch into the Harbor
job directory. Patch application happens later inside ``PatchAgent``; the
executor and agent pass around patch file paths rather than large patch text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Collection

from perfrace.run.config import RunConfigError


_PATCH_FILENAME_RE = re.compile(r"^[a-z0-9._-]+$")


def load_submission_patches(
    submission_path: Path,
    *,
    job_dir: Path,
    selected_instance_ids: Collection[str] | None = None,
) -> dict[str, Path]:
    """Materialize submission patches under ``job_dir`` and return them by instance id.

    ``submission_path`` is the local directory containing ``predictions.jsonl``.
    When ``selected_instance_ids`` is provided, only those instances are written,
    and every selected instance must be present in ``predictions.jsonl``. Extra
    predictions are allowed so a large submission can be used for subset runs.
    """
    records = _read_prediction_records(submission_path / "predictions.jsonl")
    selected = set(selected_instance_ids) if selected_instance_ids is not None else None
    if selected is not None:
        missing = sorted(selected - set(records))
        if missing:
            raise RunConfigError("Submission is missing selected instances: " + ", ".join(missing))

    patch_dir = job_dir / "submission-patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patches: dict[str, Path] = {}
    for instance_id, patch_text in records.items():
        if selected is not None and instance_id not in selected:
            continue
    # Keep large inline patches out of Harbor config JSON. PatchAgent later
        # uploads this file and applies it inside the container workspace.
        patch_path = patch_dir / f"{instance_id}.patch"
        patch_path.write_text(patch_text, encoding="utf-8")
        patches[instance_id] = patch_path
    return patches


def _read_prediction_records(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RunConfigError(f"Submission predictions file not found: {path}")

    records: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as predictions:
            # JSONL has no stdlib reader; the format is one JSON object per line.
            # Streaming preserves line numbers for diagnostics without loading a
            # potentially large submission into memory.
            for line_number, line in enumerate(predictions, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RunConfigError(
                        f"Invalid JSON in {path} line {line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(record, dict):
                    raise RunConfigError(f"Submission line {line_number} must be a JSON object")

                instance_id = record.get("instance_id")
                if not isinstance(instance_id, str) or not instance_id:
                    raise RunConfigError(
                        f"Submission line {line_number} requires string instance_id"
                    )
                if instance_id != instance_id.lower():
                    raise RunConfigError(
                        f"Submission instance_id must be lowercase: {instance_id}"
                    )
                if not _PATCH_FILENAME_RE.fullmatch(instance_id) or ".." in instance_id:
                    raise RunConfigError(
                        f"Submission instance_id is not a safe file name: {instance_id}"
                    )
                if instance_id in records:
                    raise RunConfigError(f"Duplicate submission instance_id: {instance_id}")

                patch = record.get("model_patch")
                if not isinstance(patch, str) or not patch.strip():
                    raise RunConfigError(
                        f"Submission line {line_number} requires non-empty model_patch"
                    )
                records[instance_id] = patch
    except (OSError, UnicodeError) as exc:
        raise RunConfigError(f"Failed to read submission predictions {path}: {exc}") from exc

    if not records:
        raise RunConfigError(f"Submission predictions file is empty: {path}")
    return records
