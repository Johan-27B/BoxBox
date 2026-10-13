"""Run-directory and manifest lifecycle for candidate Filter datasets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
RUN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class FilterRun:
    """Paths and immutable parameters for one Filter dataset."""

    name: str
    root: Path
    candidate_file: Path
    candidate_sha256: str
    model: str
    reasoning_effort: str
    concurrency: int
    timeout_seconds: int
    retries: int
    max_output_tokens: int
    prompt_sha256: str
    schema_sha256: str
    snapshot_policy_sha256: str
    authorship_policy_sha256: str
    created_at: datetime

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def snapshots_path(self) -> Path:
        return self.root / "snapshots.jsonl"

    @property
    def results_path(self) -> Path:
        return self.root / "results.jsonl"

    @property
    def authorship_path(self) -> Path:
        return self.root / "authorship.jsonl"

    @property
    def passed_path(self) -> Path:
        return self.root / "passed.jsonl"

    @property
    def high_priority_path(self) -> Path:
        return self.root / "high_priority.jsonl"

    @property
    def rejected_path(self) -> Path:
        return self.root / "rejected.jsonl"

    @property
    def errors_path(self) -> Path:
        return self.root / "errors.jsonl"

    @property
    def log_path(self) -> Path:
        return self.root / "filter.log"

    @property
    def proxy_log_path(self) -> Path:
        return self.root / "proxy.log"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"manifest {field} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"manifest {field} must include a UTC offset")
    return parsed.astimezone(UTC)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Filter manifest: {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Filter manifest must be a JSON object: {path}")
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported Filter manifest schema: {payload.get('schema_version')!r}")
    return payload


def _validate_run_name(name: str) -> str:
    if not RUN_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "run name must start with an alphanumeric character and contain only "
            "letters, digits, '.', '_' or '-'"
        )
    return name


def open_run(
    output_root: Path,
    *,
    run_name: str | None,
    candidate_file: Path,
    model: str,
    reasoning_effort: str,
    concurrency: int,
    timeout_seconds: int,
    retries: int,
    max_output_tokens: int,
    prompt_sha256: str,
    schema_sha256: str,
    snapshot_policy_sha256: str,
    authorship_policy_sha256: str,
) -> FilterRun:
    """Create or resume a Filter run with matching immutable parameters."""
    candidate_file = candidate_file.expanduser().resolve()
    if not candidate_file.is_file():
        raise FileNotFoundError(f"candidate file not found: {candidate_file}")
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if retries < 0:
        raise ValueError("retries must not be negative")
    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be positive")
    for name, value in (
        ("prompt_sha256", prompt_sha256),
        ("schema_sha256", schema_sha256),
        ("snapshot_policy_sha256", snapshot_policy_sha256),
        ("authorship_policy_sha256", authorship_policy_sha256),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")

    candidate_sha256 = _sha256_file(candidate_file)
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if run_name is None:
        base_name = datetime.now(UTC).strftime("filter-%Y%m%dT%H%M%SZ")
        run_name = base_name
        suffix = 2
        while (output_root / run_name).exists():
            run_name = f"{base_name}-{suffix}"
            suffix += 1
    run_name = _validate_run_name(run_name)
    root = output_root / run_name
    manifest_path = root / "manifest.json"
    expected = {
        "run_name": run_name,
        "candidate_file": str(candidate_file),
        "candidate_sha256": candidate_sha256,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "concurrency": concurrency,
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "max_output_tokens": max_output_tokens,
        "prompt_sha256": prompt_sha256,
        "schema_sha256": schema_sha256,
        "snapshot_policy_sha256": snapshot_policy_sha256,
        "authorship_policy_sha256": authorship_policy_sha256,
    }

    if manifest_path.is_file():
        manifest = _read_manifest(manifest_path)
        mismatches = [key for key, value in expected.items() if manifest.get(key) != value]
        if mismatches:
            raise ValueError(
                f"Filter run {run_name!r} has incompatible manifest fields: "
                + ", ".join(mismatches)
            )
        created_at = _parse_utc(manifest.get("created_at"), "created_at")
    else:
        if root.exists() and any(root.iterdir()):
            raise ValueError(f"Filter run directory is non-empty without a manifest: {root}")
        root.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC).replace(microsecond=0)
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            **expected,
            "created_at": _iso_utc(created_at),
            "updated_at": _iso_utc(created_at),
            "status": "running",
            "counts": {
                "input": 0,
                "processed": 0,
                "passed": 0,
                "rejected": 0,
                "errors": 0,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
            "cost_usd": 0.0,
        }
        _write_json(manifest_path, manifest)

    return FilterRun(
        name=run_name,
        root=root,
        candidate_file=candidate_file,
        candidate_sha256=candidate_sha256,
        model=model,
        reasoning_effort=reasoning_effort,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
        retries=retries,
        max_output_tokens=max_output_tokens,
        prompt_sha256=prompt_sha256,
        schema_sha256=schema_sha256,
        snapshot_policy_sha256=snapshot_policy_sha256,
        authorship_policy_sha256=authorship_policy_sha256,
        created_at=created_at,
    )


def update_manifest(run: FilterRun, **changes: Any) -> None:
    """Atomically update the Filter manifest."""
    manifest = _read_manifest(run.manifest_path)
    manifest.update(changes)
    manifest["updated_at"] = _iso_utc(datetime.now(UTC))
    _write_json(run.manifest_path, manifest)
