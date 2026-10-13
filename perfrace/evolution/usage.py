"""Durable token, cost, endpoint, and API-delay accounting."""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from perfrace.evolution.paths import HarnessEvolutionPaths
from perfrace.evolution.state import write_text_atomic
from perfrace.run.services.gateway import load_cost_models
from perfrace.run.types import RunSummary

_TRAIN_JOB = re.compile(r"^train-i(?P<iteration>\d+)-h(?P<generation>\d+)")
_VALIDATION_AGENT = re.compile(r"^offline-harness-h(?P<generation>\d+)$")
_META_SESSION = re.compile(
    r"^(?P<experiment>.+)-(?P<phase>debug|overview|evolve)"
    r"-i(?P<iteration>\d+)-h(?P<generation>\d+)"
)
_FORWARD = re.compile(r"Forwarding token proxy request: session=(\S+) model=(\S+)")
_HTTP_ERROR = re.compile(r"Upstream LLM gateway returned HTTP error: session=(\S+) status=(\d+)")


def _session_contexts(
    paths: HarnessEvolutionPaths,
    experiment_name: str,
) -> dict[str, dict[str, object]]:
    """Map durable target and meta sessions to experiment stages."""
    contexts: dict[str, dict[str, object]] = {}
    for summary_path in paths.jobs.glob("*/perfrace/run.json"):
        try:
            summary = RunSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        train_match = _TRAIN_JOB.match(summary.job_name)
        for task in summary.tasks:
            for candidate in task.candidates:
                session_id = f"{candidate.trial_name}__agent"
                if train_match:
                    contexts[session_id] = {
                        "phase": "target",
                        "iteration": int(train_match.group("iteration")),
                        "generation": int(train_match.group("generation")),
                        "task": task.task_name,
                    }
                    continue
                validation_match = _VALIDATION_AGENT.match(candidate.agent)
                if validation_match and summary.job_name.startswith("validation-global"):
                    contexts[session_id] = {
                        "phase": "validation",
                        "iteration": None,
                        "generation": int(validation_match.group("generation")),
                        "task": task.task_name,
                    }
    for job_dir in paths.jobs.iterdir() if paths.jobs.is_dir() else ():
        if not job_dir.is_dir():
            continue
        train_match = _TRAIN_JOB.match(job_dir.name)
        is_validation = job_dir.name.startswith("validation-global")
        if train_match is None and not is_validation:
            continue
        for config_path in job_dir.glob("*/config.json"):
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            agent = config.get("agent")
            if not isinstance(agent, dict) or agent.get("import_path") != (
                "perfrace.installed.evolved:EvolvedHarnessAgent"
            ):
                continue
            session_id = f"{config_path.parent.name}__agent"
            if session_id in contexts:
                continue
            if train_match:
                contexts[session_id] = {
                    "phase": "target",
                    "iteration": int(train_match.group("iteration")),
                    "generation": int(train_match.group("generation")),
                    "task": None,
                }
                continue
            validation_match = _VALIDATION_AGENT.match(str(agent.get("name") or ""))
            if validation_match:
                contexts[session_id] = {
                    "phase": "validation",
                    "iteration": None,
                    "generation": int(validation_match.group("generation")),
                    "task": None,
                }
    for path in (paths.root / "gateway" / "token-proxy").glob("*.jsonl"):
        match = _META_SESSION.match(path.stem)
        if match and match.group("experiment") == experiment_name:
            contexts[path.stem] = {
                "phase": match.group("phase"),
                "iteration": int(match.group("iteration")),
                "generation": int(match.group("generation")),
                "task": None,
            }
    return contexts


def _usage_values(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize one OpenAI-compatible usage object."""
    input_tokens = int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("input_token_count")
        or 0
    )
    output_tokens = int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("output_token_count")
        or 0
    )
    input_details = (
        usage.get("prompt_tokens_details")
        or usage.get("input_tokens_details")
        or usage.get("input_token_details")
        or {}
    )
    output_details = (
        usage.get("completion_tokens_details")
        or usage.get("output_tokens_details")
        or usage.get("output_token_details")
        or {}
    )
    cached_tokens = int(input_details.get("cached_tokens") or 0)
    cache_write_tokens = int(
        input_details.get("cache_write_tokens")
        or input_details.get("cache_creation_input_tokens")
        or 0
    )
    reasoning_tokens = int(output_details.get("reasoning_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": int(usage.get("total_tokens") or input_tokens + output_tokens),
    }


def _cost_usd(model: str | None, values: dict[str, int]) -> float | None:
    """Price one normalized usage record with the repository cost model."""
    cost_model = load_cost_models().get(model or "")
    if cost_model is None:
        return None
    uncached = max(values["input_tokens"] - values["cached_input_tokens"], 0)
    return (
        uncached * cost_model.input_cost_per_token
        + values["cached_input_tokens"] * cost_model.cached_input_cost_per_token
        + values["output_tokens"] * cost_model.output_cost_per_token
    )


def _request_counts(request_log: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Count forwarded and failed requests without inferring missing token usage."""
    forwarded: dict[str, int] = defaultdict(int)
    errors: dict[str, int] = defaultdict(int)
    if not request_log.is_file():
        return forwarded, errors
    for line in request_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if match := _FORWARD.search(line):
            forwarded[match.group(1)] += 1
        if match := _HTTP_ERROR.search(line):
            errors[match.group(1)] += 1
    return forwarded, errors


def _endpoint_map(session_ids: set[str], nginx_log: Path) -> dict[str, tuple[str, ...]]:
    """Map sticky sessions to every observed nginx upstream."""
    endpoints: dict[str, set[str]] = defaultdict(set)
    if not nginx_log.is_file():
        return {}
    try:
        lines = nginx_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] in session_ids:
            endpoints[parts[0]].add(parts[1])
    return {session: tuple(sorted(values)) for session, values in endpoints.items()}


def _api_delays(paths: HarnessEvolutionPaths, session_ids: set[str]) -> dict[str, list[float]]:
    """Load target-agent API timing samples from Harbor trial results."""
    delays: dict[str, list[float]] = defaultdict(list)
    for result_path in paths.jobs.glob("*/*/result.json"):
        session_id = f"{result_path.parent.name}__agent"
        if session_id not in session_ids:
            continue
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for step in result.get("step_results") or []:
            metadata = (step.get("agent_result") or {}).get("metadata") or {}
            samples = metadata.get("api_request_times_msec") or []
            delays[session_id].extend(float(sample) for sample in samples)
    return delays


def _percentile(values: list[float], quantile: float) -> float:
    """Return one linearly interpolated percentile."""
    ordered = sorted(values)
    rank = (len(ordered) - 1) * quantile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _delay_summary(values: list[float]) -> dict[str, float | int] | None:
    """Summarize millisecond API timings in seconds."""
    if not values:
        return None
    return {
        "samples": len(values),
        "mean_seconds": statistics.fmean(values) / 1000,
        "median_seconds": statistics.median(values) / 1000,
        "p95_seconds": _percentile(values, 0.95) / 1000,
    }


def _aggregate_sessions(
    sessions: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    """Aggregate numeric usage fields by one session attribute."""
    result: dict[str, dict[str, Any]] = {}
    for session in sessions:
        value = session.get(key)
        if value is None:
            continue
        label = str(value)
        aggregate = result.setdefault(
            label,
            {
                "sessions": 0,
                "usage_records": 0,
                "forwarded_requests": 0,
                "http_errors": 0,
                "missing_usage_records": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "unpriced_records": 0,
            },
        )
        aggregate["sessions"] += 1
        for field in (
            "usage_records",
            "forwarded_requests",
            "http_errors",
            "missing_usage_records",
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "unpriced_records",
        ):
            aggregate[field] += session[field]
        aggregate["cost_usd"] += session["cost_usd"]
    return result


def _total_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate every observed session into one experiment total."""
    tagged = [{**session, "_total": "all"} for session in sessions]
    totals = _aggregate_sessions(tagged, "_total")
    return totals.get(
        "all",
        {
            "sessions": 0,
            "usage_records": 0,
            "forwarded_requests": 0,
            "http_errors": 0,
            "missing_usage_records": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "unpriced_records": 0,
        },
    )


def build_usage_report(
    paths: HarnessEvolutionPaths,
    *,
    experiment_name: str,
    completed_iterations: int,
    nginx_log: Path = Path("/var/log/nginx/perfrace-copilot-pool.log"),
) -> dict[str, Any]:
    """Build complete observed usage accounting without reconstructing missing records."""
    token_dir = paths.root / "gateway" / "token-proxy"
    contexts = _session_contexts(paths, experiment_name)
    forwarded, errors = _request_counts(token_dir / "token-proxy-requests.log")
    token_paths = sorted(token_dir.glob("*.jsonl"))
    token_path_by_session = {path.stem: path for path in token_paths}
    session_ids = set(token_path_by_session) | set(contexts) | set(forwarded) | set(errors)
    endpoints = _endpoint_map(session_ids, nginx_log)
    delays = _api_delays(paths, session_ids)
    sessions: list[dict[str, Any]] = []
    malformed_records = 0
    for initial_session_id in sorted(session_ids):
        models: set[str] = set()
        totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }
        usage_records = 0
        cost_usd = 0.0
        unpriced_records = 0
        session_id = initial_session_id
        path = token_path_by_session.get(initial_session_id)
        lines = (
            path.read_text(encoding="utf-8", errors="replace").splitlines()
            if path is not None
            else ()
        )
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed_records += 1
                continue
            record_session = record.get("session_id")
            if isinstance(record_session, str) and record_session:
                session_id = record_session
            usage = record.get("usage")
            if not isinstance(usage, dict):
                continue
            model = record.get("model")
            if isinstance(model, str):
                models.add(model)
            values = _usage_values(usage)
            for field, value in values.items():
                totals[field] += value
            usage_records += 1
            record_cost = _cost_usd(model if isinstance(model, str) else None, values)
            if record_cost is None:
                unpriced_records += 1
            else:
                cost_usd += record_cost
        context = contexts.get(session_id)
        if context is None:
            match = _META_SESSION.match(session_id)
            if match and match.group("experiment") == experiment_name:
                context = {
                    "phase": match.group("phase"),
                    "iteration": int(match.group("iteration")),
                    "generation": int(match.group("generation")),
                    "task": None,
                }
            else:
                context = {
                    "phase": "unknown",
                    "iteration": None,
                    "generation": None,
                    "task": None,
                }
        observed_endpoints = endpoints.get(session_id, ())
        session_delays = delays.get(session_id, [])
        sessions.append(
            {
                "session_id": session_id,
                **context,
                "endpoint": observed_endpoints[0] if len(observed_endpoints) == 1 else None,
                "endpoint_observations": list(observed_endpoints),
                "models": sorted(models),
                "usage_records": usage_records,
                "forwarded_requests": forwarded.get(session_id, 0),
                "http_errors": errors.get(session_id, 0),
                "missing_usage_records": max(
                    forwarded.get(session_id, 0) - usage_records,
                    0,
                ),
                **totals,
                "cost_usd": cost_usd,
                "unpriced_records": unpriced_records,
                "api_delay": _delay_summary(session_delays),
                "missing_api_delay_samples": max(usage_records - len(session_delays), 0),
            }
        )
    sessions.sort(key=lambda item: item["session_id"])
    all_delays = [sample for values in delays.values() for sample in values]
    endpoint_delays: dict[str, list[float]] = defaultdict(list)
    for session_id, values in delays.items():
        observed_endpoints = endpoints.get(session_id, ())
        if len(observed_endpoints) == 1:
            endpoint_delays[observed_endpoints[0]].extend(values)
    return {
        "schema_version": 1,
        "experiment_name": experiment_name,
        "completed_iterations": completed_iterations,
        "sessions": sessions,
        "total": _total_sessions(sessions),
        "by_phase": _aggregate_sessions(sessions, "phase"),
        "by_iteration": _aggregate_sessions(sessions, "iteration"),
        "by_endpoint": _aggregate_sessions(sessions, "endpoint"),
        "api_delay": _delay_summary(all_delays),
        "api_delay_by_endpoint": {
            endpoint: _delay_summary(values)
            for endpoint, values in sorted(endpoint_delays.items())
        },
        "malformed_usage_records": malformed_records,
        "multi_endpoint_sessions": [
            session["session_id"]
            for session in sessions
            if len(session["endpoint_observations"]) > 1
        ],
        "unknown_sessions": [
            session["session_id"] for session in sessions if session["phase"] == "unknown"
        ],
    }


def _markdown_table(rows: list[tuple[str, dict[str, Any]]]) -> str:
    """Render one compact token/cost table."""
    lines = [
        "| Group | Requests | Missing usage | Input | Cached | Output | Cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, values in rows:
        lines.append(
            f"| {label} | {values['usage_records']:,} | "
            f"{values['missing_usage_records']:,} | {values['input_tokens']:,} | "
            f"{values['cached_input_tokens']:,} | {values['output_tokens']:,} | "
            f"${values['cost_usd']:.6f} |"
        )
    return "\n".join(lines)


def render_usage_markdown(report: dict[str, Any]) -> str:
    """Render the durable human-readable cost report."""
    lines = [
        "# Harness Evolution usage",
        "",
        f"- Experiment: `{report['experiment_name']}`",
        f"- Completed iterations: {report['completed_iterations']}",
        f"- Malformed usage records: {report['malformed_usage_records']}",
        f"- Total configured cost: ${report['total']['cost_usd']:.6f}",
        f"- Missing usage records: {report['total']['missing_usage_records']}",
        "",
        "## By phase",
        "",
        _markdown_table(sorted(report["by_phase"].items())),
        "",
        "## By iteration",
        "",
        _markdown_table(
            sorted(
                report["by_iteration"].items(),
                key=lambda item: int(item[0]),
            )
        ),
        "",
        "## By nginx endpoint",
        "",
        _markdown_table(sorted(report["by_endpoint"].items())),
        "",
        "## API delay",
        "",
    ]
    api_delay = report["api_delay"]
    if api_delay is None:
        lines.append("No target-agent API-delay samples were available.")
    else:
        lines.append(
            f"{api_delay['samples']:,} samples; mean "
            f"{api_delay['mean_seconds']:.3f}s, median "
            f"{api_delay['median_seconds']:.3f}s, p95 "
            f"{api_delay['p95_seconds']:.3f}s."
        )
    if report["api_delay_by_endpoint"]:
        lines.extend(
            [
                "",
                "| Endpoint | Samples | Mean | Median | P95 |",
                "| --- | ---: | ---: | ---: | ---: |",
                *[
                    f"| `{endpoint}` | {values['samples']:,} | "
                    f"{values['mean_seconds']:.3f}s | "
                    f"{values['median_seconds']:.3f}s | "
                    f"{values['p95_seconds']:.3f}s |"
                    for endpoint, values in report["api_delay_by_endpoint"].items()
                ],
            ]
        )
    if report["multi_endpoint_sessions"]:
        lines.extend(
            [
                "",
                "## Sticky endpoint violations",
                "",
                *[f"- `{session}`" for session in report["multi_endpoint_sessions"]],
            ]
        )
    if report["unknown_sessions"]:
        lines.extend(
            [
                "",
                "## Unclassified sessions",
                "",
                *[f"- `{session}`" for session in report["unknown_sessions"]],
            ]
        )
    return "\n".join(lines) + "\n"


def write_usage_report(
    paths: HarnessEvolutionPaths,
    *,
    experiment_name: str,
    completed_iterations: int,
) -> dict[str, Any]:
    """Write JSON and Markdown usage reports only when their content changes."""
    report = build_usage_report(
        paths,
        experiment_name=experiment_name,
        completed_iterations=completed_iterations,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_usage_markdown(report)
    if not paths.usage_report.is_file() or paths.usage_report.read_text() != json_text:
        write_text_atomic(paths.usage_report, json_text)
    if not paths.usage_markdown.is_file() or paths.usage_markdown.read_text() != markdown:
        write_text_atomic(paths.usage_markdown, markdown)
    return report
