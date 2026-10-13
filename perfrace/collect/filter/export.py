"""Filter result normalization, persistence, and split exports."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..discovery.export import validate_candidate
from .models import ModelJudgment
from .runs import FilterRun

GATE_ORDER = (
    "accessible",
    "reproducibility",
    "evaluation_potential",
    "resource_feasibility",
)
HIGH_PRIORITY_CREATED_AFTER = datetime(2023, 1, 1, tzinfo=UTC)
HIGH_PRIORITY_MIN_STARS = 100
HIGH_PRIORITY_MAX_STARS = 5_000
HIGH_PRIORITY_MAX_DISK_KB = 500_000
HIGH_PRIORITY_EXCLUDED = re.compile(
    r"\b(agent|workflow|mcp|prompt|chatbot|llm|remote api|github actions|orchestration)\b",
    re.IGNORECASE,
)
HIGH_PRIORITY_CORE = re.compile(
    r"\b(parse|parser|parsing|compile|compiler|solver|simulation|numerical|matrix|"
    r"tensor|graph|query|index|storage|database|compress|decompress|encode|decode|"
    r"render|layout|geometry|proof|prover|crypto|hash|sort|join|aggregate|"
    r"static analysis|type.?check|schedule|routing|optimization|transform|fft|signal|"
    r"image|audio|video|serialization|filesystem|interpreter|runtime)\b",
    re.IGNORECASE,
)
HIGH_PRIORITY_REPO_NATIVE = re.compile(
    r"\b(test suite|unit tests?|integration tests?|benchmark suite|repository benchmark|"
    r"repo(?:sitory)? build|workspace build|checked-in (?:test|benchmark|fixture)|tests?/)\b",
    re.IGNORECASE,
)


def is_high_priority(candidate: dict[str, Any]) -> bool:
    """Return whether a Filter PASS belongs in the strict Pair Verification shortlist."""
    filter_data = candidate.get("filter") or {}
    profile = filter_data.get("optimization_profile") or {}
    process = filter_data.get("preliminary_process") or {}
    if profile.get("potential") != "high":
        return False
    if process.get("workload_carrier") not in {
        "portable_artifact",
        "intrinsic_computation",
    }:
        return False
    stars = candidate.get("stargazer_count")
    if (
        not isinstance(stars, int)
        or not HIGH_PRIORITY_MIN_STARS <= stars < HIGH_PRIORITY_MAX_STARS
    ):
        return False
    created_at = candidate.get("created_at")
    if not isinstance(created_at, str):
        return False
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if created.tzinfo is None or created.astimezone(UTC) < HIGH_PRIORITY_CREATED_AFTER:
        return False
    disk_usage_kb = candidate.get("disk_usage_kb")
    if not isinstance(disk_usage_kb, int) or disk_usage_kb >= HIGH_PRIORITY_MAX_DISK_KB:
        return False
    if process.get("external_services"):
        return False
    evidence_text = " ".join(
        str(value or "")
        for value in (
            candidate.get("description"),
            profile.get("computation"),
            profile.get("performance_hint"),
            process.get("name"),
            process.get("input"),
            process.get("output"),
            process.get("correctness"),
        )
    )
    return (
        HIGH_PRIORITY_EXCLUDED.search(evidence_text) is None
        and HIGH_PRIORITY_CORE.search(evidence_text) is not None
        and HIGH_PRIORITY_REPO_NATIVE.search(evidence_text) is None
    )


def read_candidates(path: Path) -> list[dict[str, Any]]:
    """Read and validate ranked Discovery candidates."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid candidate JSON on line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(candidate, dict):
                raise ValueError(f"candidate line {line_number} must be an object")
            validate_candidate(candidate)
            repo_url = candidate["repo_url"]
            if repo_url in seen:
                raise ValueError(f"duplicate candidate repository: {repo_url}")
            seen.add(repo_url)
            candidates.append(candidate)
    return candidates


def load_latest_records(path: Path) -> dict[str, dict[str, Any]]:
    """Load the latest complete record for each repository."""
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path} line {line_number}: {exc.msg}") from exc
            if not isinstance(record, dict) or not isinstance(record.get("repo_url"), str):
                raise ValueError(f"{path} line {line_number} has no repo_url")
            records[record["repo_url"]] = record
    return records


def append_record(path: Path, record: dict[str, Any]) -> None:
    """Append and fsync one complete JSONL record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def precheck_rejection(
    candidate: dict[str, Any],
    *,
    gate: str,
    reason: str,
    evidence: list[str],
) -> dict[str, Any]:
    """Build a terminal REJECT result from deterministic precheck evidence."""
    gates = {
        name: {
            "passed": False,
            "evidence": (
                evidence if name == gate else ["Not evaluated after deterministic precheck."]
            ),
        }
        for name in GATE_ORDER
    }
    return {
        "repo_url": candidate["repo_url"],
        "status": "REJECT",
        "failed_gate": gate,
        "reason": reason,
        "candidate": candidate,
        "snapshot_sha256": None,
        "filter": {
            "precheck": {
                "rule": gate,
                "evidence": evidence,
            },
            "gates": gates,
            "reason": reason,
            "preliminary_process": None,
            "model": None,
            "reasoning_effort": None,
            "usage": {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "requests": 0,
                "models": [],
            },
            "cost_usd": 0.0,
        },
    }


def error_result(
    candidate: dict[str, Any],
    *,
    error_type: str,
    error: str,
    snapshot_sha256: str | None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    attempts: int | None = None,
    usage: dict[str, Any] | None = None,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """Build a retryable ERROR result."""
    return {
        "repo_url": candidate["repo_url"],
        "status": "ERROR",
        "failed_gate": None,
        "reason": error,
        "candidate": candidate,
        "snapshot_sha256": snapshot_sha256,
        "error_type": error_type,
        "error": error,
        "filter": (
            {
                "model": model,
                "reasoning_effort": reasoning_effort,
                "attempts": attempts,
                "usage": usage,
                "cost_usd": cost_usd,
            }
            if model is not None
            else None
        ),
    }


def judged_result(
    candidate: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Derive PASS or REJECT from one strict model judgment."""
    judgment = ModelJudgment.model_validate(outcome["judgment"])
    gates = judgment.gates.model_dump(mode="json")
    resource = gates["resource_feasibility"]
    if not resource["linux_x86_64_runnable"]:
        resource["passed"] = False
        resource["evidence"].append("Structured resource check: linux_x86_64_runnable = false")
    if resource["special_hardware_required"]:
        resource["passed"] = False
        resource["evidence"].append("Structured resource check: special_hardware_required = true")
    failed_gate = next(
        (name for name in GATE_ORDER if not gates[name]["passed"]),
        None,
    )
    if failed_gate is None and judgment.optimization_profile.potential == "low":
        failed_gate = "optimization_potential"
    status = "PASS" if failed_gate is None else "REJECT"
    return {
        "repo_url": candidate["repo_url"],
        "status": status,
        "failed_gate": failed_gate,
        "reason": judgment.reason,
        "candidate": candidate,
        "snapshot_sha256": outcome["snapshot_sha256"],
        "filter": {
            "gates": gates,
            "reason": judgment.reason,
            "preliminary_process": (
                judgment.preliminary_process.model_dump(mode="json")
                if judgment.preliminary_process is not None
                else None
            ),
            "optimization_profile": judgment.optimization_profile.model_dump(mode="json"),
            "model": outcome["model"],
            "reasoning_effort": outcome["reasoning_effort"],
            "attempts": outcome["attempts"],
            "usage": outcome["usage"],
            "cost_usd": outcome["cost_usd"],
        },
    }


def _atomic_write(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def rebuild_exports(
    run: FilterRun,
    candidates: list[dict[str, Any]],
) -> dict[str, int | float]:
    """Rebuild normalized and split outputs in input ranking order."""
    latest = load_latest_records(run.results_path)
    ordered = [
        latest[candidate["repo_url"]]
        for candidate in candidates
        if candidate["repo_url"] in latest
    ]
    passed = [
        {**record["candidate"], "filter": record["filter"]}
        for record in ordered
        if record["status"] == "PASS"
    ]
    passed.sort(
        key=lambda candidate: (
            -candidate["stargazer_count"],
            -(
                candidate["authorship"]["ai_ratio"]
                if candidate["authorship"]["ai_ratio"] is not None
                else -1
            ),
            candidate["repo_url"],
        )
    )
    high_priority = [candidate for candidate in passed if is_high_priority(candidate)]
    rejected = [record for record in ordered if record["status"] == "REJECT"]
    errors = [record for record in ordered if record["status"] == "ERROR"]
    _atomic_write(run.results_path, ordered)
    _atomic_write(run.passed_path, passed)
    _atomic_write(run.high_priority_path, high_priority)
    _atomic_write(run.rejected_path, rejected)
    _atomic_write(run.errors_path, errors)

    usage = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    cost = 0.0
    cost_available = True
    for record in ordered:
        filter_data = record.get("filter") or {}
        record_usage = filter_data.get("usage") or {}
        for key in usage:
            usage[key] += int(record_usage.get(key) or 0)
        record_cost = filter_data.get("cost_usd")
        if filter_data.get("model") is not None and record_cost is None:
            cost_available = False
        elif record_cost is not None:
            cost += float(record_cost)
    return {
        "input": len(candidates),
        "processed": len(ordered),
        "passed": len(passed),
        "high_priority": len(high_priority),
        "rejected": len(rejected),
        "errors": len(errors),
        **usage,
        "cost_usd": round(cost, 8) if cost_available else -1.0,
    }
