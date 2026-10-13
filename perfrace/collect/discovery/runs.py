"""Run-directory and manifest lifecycle for Discovery datasets."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 3
RUN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STEP_NAMES = ("harvest", "metadata", "export")


@dataclass(frozen=True)
class DiscoveryRun:
    """Paths and immutable parameters for one Discovery dataset."""

    name: str
    root: Path
    start_at: datetime
    end_at: datetime
    authorship_start_at: datetime
    authorship_end_at: datetime
    bot_config_sha256: str
    created_at: datetime

    @property
    def manifest_path(self) -> Path:
        """Return the run manifest path."""
        return self.root / "manifest.json"

    @property
    def harvest_path(self) -> Path:
        """Return the harvested project-record path."""
        return self.root / "harvest.jsonl"

    @property
    def metadata_path(self) -> Path:
        """Return the repository metadata path."""
        return self.root / "metadata.jsonl"

    @property
    def candidates_path(self) -> Path:
        """Return the exported candidate path."""
        return self.root / "candidates.jsonl"

    def log_path(self, step: str) -> Path:
        """Return the log path for one Discovery step."""
        if step not in STEP_NAMES:
            raise ValueError(f"unknown Discovery step: {step}")
        return self.root / f"{step}.log"


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Discovery timestamps must include a UTC offset")
    normalized = value.astimezone(UTC).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _one_year_before(value: datetime) -> datetime:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"manifest {field} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"manifest {field} must include a UTC offset")
    return parsed.astimezone(UTC)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Discovery manifest: {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Discovery manifest must be a JSON object: {path}")
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported Discovery manifest schema: {payload.get('schema_version')!r}"
        )
    return payload


def _validate_run_name(run_name: str) -> str:
    if not RUN_NAME_PATTERN.fullmatch(run_name):
        raise ValueError(
            "run name must start with an alphanumeric character and contain only "
            "letters, digits, '.', '_' or '-'"
        )
    return run_name


def open_run(
    output_root: Path,
    *,
    run_name: str | None,
    start_at: datetime,
    end_at: datetime,
    bot_config_sha256: str,
) -> DiscoveryRun:
    """Create or resume one Discovery run with matching immutable parameters."""
    start_text = _iso_utc(start_at)
    end_text = _iso_utc(end_at)
    authorship_start_at = _one_year_before(end_at.astimezone(UTC))
    authorship_end_at = end_at.astimezone(UTC)
    authorship_start_text = _iso_utc(authorship_start_at)
    authorship_end_text = _iso_utc(authorship_end_at)
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    if not re.fullmatch(r"[0-9a-f]{64}", bot_config_sha256):
        raise ValueError("bot_config_sha256 must be a lowercase SHA-256 digest")

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if run_name is None:
        base_name = datetime.now(UTC).strftime("discover-%Y%m%dT%H%M%SZ")
        run_name = base_name
        suffix = 2
        while (output_root / run_name).exists():
            run_name = f"{base_name}-{suffix}"
            suffix += 1
    run_name = _validate_run_name(run_name)
    run_root = output_root / run_name
    manifest_path = run_root / "manifest.json"

    if manifest_path.is_file():
        manifest = _read_manifest(manifest_path)
        expected = {
            "run_name": run_name,
            "discovery_channel": "ai-signals",
            "start_at": start_text,
            "end_at": end_text,
            "authorship_start_at": authorship_start_text,
            "authorship_end_at": authorship_end_text,
            "bot_config_sha256": bot_config_sha256,
        }
        mismatches = [key for key, value in expected.items() if manifest.get(key) != value]
        if mismatches:
            raise ValueError(
                f"Discovery run {run_name!r} has incompatible manifest fields: "
                + ", ".join(mismatches)
            )
        created_at = _parse_utc(manifest.get("created_at"), "created_at")
        return DiscoveryRun(
            name=run_name,
            root=run_root,
            start_at=_parse_utc(manifest["start_at"], "start_at"),
            end_at=_parse_utc(manifest["end_at"], "end_at"),
            authorship_start_at=_parse_utc(manifest["authorship_start_at"], "authorship_start_at"),
            authorship_end_at=_parse_utc(manifest["authorship_end_at"], "authorship_end_at"),
            bot_config_sha256=bot_config_sha256,
            created_at=created_at,
        )

    if run_root.exists() and any(run_root.iterdir()):
        raise ValueError(f"Discovery run directory is non-empty without a manifest: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).replace(microsecond=0)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_name": run_name,
        "discovery_channel": "ai-signals",
        "created_at": _iso_utc(created_at),
        "updated_at": _iso_utc(created_at),
        "start_at": start_text,
        "end_at": end_text,
        "authorship_start_at": authorship_start_text,
        "authorship_end_at": authorship_end_text,
        "bot_config_sha256": bot_config_sha256,
        "steps": {step: {"status": "pending"} for step in STEP_NAMES},
        "counts": {
            "discovered": 0,
            "metadata_valid": 0,
            "metadata_unavailable": 0,
            "exported": 0,
            "export_excluded": 0,
        },
    }
    _write_json(manifest_path, manifest)
    return DiscoveryRun(
        name=run_name,
        root=run_root,
        start_at=start_at.astimezone(UTC),
        end_at=end_at.astimezone(UTC),
        authorship_start_at=authorship_start_at,
        authorship_end_at=authorship_end_at,
        bot_config_sha256=bot_config_sha256,
        created_at=created_at,
    )


def load_run(output_root: Path, run_name: str) -> DiscoveryRun:
    """Load one existing Discovery run."""
    run_name = _validate_run_name(run_name)
    root = output_root.expanduser().resolve() / run_name
    manifest = _read_manifest(root / "manifest.json")
    if manifest.get("run_name") != run_name:
        raise ValueError(f"manifest run name does not match directory: {root}")
    if manifest.get("discovery_channel") != "ai-signals":
        raise ValueError(f"unsupported discovery channel in {root / 'manifest.json'}")
    bot_config_sha256 = manifest.get("bot_config_sha256")
    if not isinstance(bot_config_sha256, str):
        raise ValueError("manifest bot_config_sha256 must be a string")
    return DiscoveryRun(
        name=run_name,
        root=root,
        start_at=_parse_utc(manifest.get("start_at"), "start_at"),
        end_at=_parse_utc(manifest.get("end_at"), "end_at"),
        authorship_start_at=_parse_utc(manifest.get("authorship_start_at"), "authorship_start_at"),
        authorship_end_at=_parse_utc(manifest.get("authorship_end_at"), "authorship_end_at"),
        bot_config_sha256=bot_config_sha256,
        created_at=_parse_utc(manifest.get("created_at"), "created_at"),
    )


def step_status(run: DiscoveryRun, step: str) -> str:
    """Return the persisted status for one Discovery step."""
    if step not in STEP_NAMES:
        raise ValueError(f"unknown Discovery step: {step}")
    manifest = _read_manifest(run.manifest_path)
    state = manifest.get("steps", {}).get(step, {})
    status = state.get("status")
    if status not in {"pending", "running", "complete", "failed"}:
        raise ValueError(f"manifest contains invalid {step} status: {status!r}")
    return status


def run_counts(run: DiscoveryRun) -> dict[str, int]:
    """Return the persisted run-level counters."""
    manifest = _read_manifest(run.manifest_path)
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("manifest counts must be a mapping")
    result: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str) or not isinstance(value, int) or value < 0:
            raise ValueError("manifest counts must contain non-negative integers")
        result[key] = value
    return result


def update_step(
    run: DiscoveryRun,
    step: str,
    *,
    status: str,
    rows: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Atomically update one step in the run manifest."""
    if step not in STEP_NAMES:
        raise ValueError(f"unknown Discovery step: {step}")
    if status not in {"pending", "running", "complete", "failed"}:
        raise ValueError(f"invalid Discovery step status: {status}")
    manifest = _read_manifest(run.manifest_path)
    now = _iso_utc(datetime.now(UTC))
    step_state: dict[str, Any] = {"status": status, "updated_at": now}
    if rows is not None:
        if rows < 0:
            raise ValueError("step row count must not be negative")
        step_state["rows"] = rows
    if details:
        step_state.update(details)
        counts = details.get("counts")
        if counts is not None:
            if not isinstance(counts, dict):
                raise ValueError("step counts must be a mapping")
            manifest.setdefault("counts", {}).update(counts)
            step_state.pop("counts")
    if status == "complete":
        step_state["completed_at"] = now
    manifest.setdefault("steps", {})[step] = step_state
    manifest["updated_at"] = now
    _write_json(run.manifest_path, manifest)
