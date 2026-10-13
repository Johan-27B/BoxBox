"""Mechanical validation for agent-authored hypothesis cost estimates."""

from __future__ import annotations

import re
import math
import shlex
import statistics
from typing import Any, Iterable


ESTIMATOR_PATH = ".autoresearch/tools/estimate_upper_bound.py"
ESTIMATE_SCHEMA_VERSION = 1
MATERIALITY_THRESHOLD_ERROR_PREFIX = (
    "cost_model.lower_bound_seconds is below the materiality threshold"
)


def created_hypotheses(commands: Iterable[str]) -> list[str]:
    """Return literal try/* branches created by a command batch."""
    hypothesis_ref = re.compile(r"(?:refs/heads/)?try/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)")
    hypotheses: list[str] = []
    for command in commands:
        for fragment in re.split(r"(?:&&|\|\||[;|\n])", command):
            try:
                tokens = shlex.split(fragment)
            except ValueError:
                continue
            if "git" not in tokens:
                continue
            tokens = tokens[tokens.index("git") + 1 :]
            while tokens and tokens[0].startswith("-"):
                option = tokens.pop(0)
                if option in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}:
                    if tokens:
                        tokens.pop(0)
            if not tokens:
                continue
            operation, arguments = tokens[0], tokens[1:]
            creates_ref = False
            if operation == "checkout":
                creates_ref = any(
                    argument in {"-b", "-B", "--orphan"}
                    or argument.startswith(("-btry/", "-Btry/", "--orphan="))
                    for argument in arguments
                )
            elif operation == "switch":
                creates_ref = any(
                    argument in {"-c", "-C", "--create", "--force-create"}
                    or argument.startswith(("-ctry/", "-Ctry/", "--create=", "--force-create="))
                    for argument in arguments
                )
            elif operation == "branch":
                deletion = any(argument in {"-d", "-D", "--delete"} for argument in arguments)
                listing = any(argument == "--list" for argument in arguments)
                creates_ref = not deletion and not listing
            elif operation in {"update-ref", "symbolic-ref"}:
                creates_ref = True
            elif operation == "push":
                creates_ref = any("refs/heads/try/" in argument for argument in arguments)
            if not creates_ref:
                continue
            for argument in arguments:
                match = hypothesis_ref.search(argument)
                if match is None:
                    continue
                hypothesis = match.group("name")
                if hypothesis not in hypotheses:
                    hypotheses.append(hypothesis)
    return hypotheses


def validate_materiality_record(
    payload: Any,
    *,
    expected_hypothesis: str,
    expected_base_commit: str,
    estimator_sha256: str,
) -> list[str]:
    """Return all reasons an estimate is stale, malformed, or immaterial."""
    errors: list[str] = []

    def mapping(value: Any, field: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        errors.append(f"{field} must be an object")
        return {}

    def number(value: Any, field: str, *, minimum: float = 0.0) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(f"{field} must be a finite number")
            return None
        result = float(value)
        if not math.isfinite(result):
            errors.append(f"{field} must be a finite number")
            return None
        if result < minimum:
            errors.append(f"{field} must be >= {minimum}")
            return None
        return result

    def check_close(actual: float | None, expected: float, field: str) -> None:
        if actual is not None and not math.isclose(
            actual,
            expected,
            rel_tol=1e-6,
            abs_tol=1e-9,
        ):
            errors.append(f"{field} must equal the independently recomputed value {expected}")

    root = mapping(payload, "record")
    if root.get("schema_version") != ESTIMATE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ESTIMATE_SCHEMA_VERSION}")
    if root.get("hypothesis") != expected_hypothesis:
        errors.append(f"hypothesis must be {expected_hypothesis!r}")
    if root.get("base_commit") != expected_base_commit:
        errors.append("base_commit must match the current main commit")

    estimator = mapping(root.get("estimator"), "estimator")
    if estimator.get("path") != ESTIMATOR_PATH:
        errors.append(f"estimator.path must be {ESTIMATOR_PATH!r}")
    if estimator.get("sha256") != estimator_sha256:
        errors.append("estimator.sha256 must match the current estimator tool")

    baseline = mapping(root.get("baseline"), "baseline")
    if not isinstance(baseline.get("command"), str) or not baseline["command"].strip():
        errors.append("baseline.command must be a non-empty string")
    raw_samples = baseline.get("samples_seconds")
    samples: list[float] = []
    if not isinstance(raw_samples, list) or len(raw_samples) < 3:
        errors.append("baseline.samples_seconds must contain at least three samples")
    else:
        for index, sample in enumerate(raw_samples):
            parsed = number(sample, f"baseline.samples_seconds[{index}]", minimum=0.0)
            if parsed is not None:
                samples.append(parsed)
        if any(sample <= 0 for sample in samples):
            errors.append("baseline.samples_seconds values must be > 0")

    baseline_seconds = number(baseline.get("median_seconds"), "baseline.median_seconds")
    noise_seconds = number(baseline.get("noise_seconds"), "baseline.noise_seconds")
    if len(samples) == len(raw_samples or []) and samples:
        recomputed_baseline = statistics.median(samples)
        deviations = [abs(sample - recomputed_baseline) for sample in samples]
        recomputed_noise = 1.4826 * statistics.median(deviations)
        check_close(baseline_seconds, recomputed_baseline, "baseline.median_seconds")
        check_close(noise_seconds, recomputed_noise, "baseline.noise_seconds")

    cost = mapping(root.get("cost_model"), "cost_model")
    affected = number(cost.get("affected_operations"), "cost_model.affected_operations", minimum=1)
    avoidable = number(
        cost.get("avoidable_cost_per_operation_seconds"),
        "cost_model.avoidable_cost_per_operation_seconds",
    )
    removable = number(cost.get("removable_fraction"), "cost_model.removable_fraction")
    overhead = number(cost.get("added_overhead_seconds"), "cost_model.added_overhead_seconds")
    uncertainty = number(cost.get("uncertainty_seconds"), "cost_model.uncertainty_seconds")
    gain = number(cost.get("estimated_gain_seconds"), "cost_model.estimated_gain_seconds")
    lower_bound = number(cost.get("lower_bound_seconds"), "cost_model.lower_bound_seconds")
    threshold = number(
        cost.get("materiality_threshold_seconds"),
        "cost_model.materiality_threshold_seconds",
    )
    if removable is not None and not 0 < removable <= 1:
        errors.append("cost_model.removable_fraction must be > 0 and <= 1")

    model_values = (affected, avoidable, removable, overhead, uncertainty)
    if all(value is not None for value in model_values):
        recomputed_gain = affected * avoidable * removable - overhead
        check_close(gain, recomputed_gain, "cost_model.estimated_gain_seconds")
        if gain is not None and uncertainty is not None:
            check_close(
                lower_bound,
                gain - uncertainty,
                "cost_model.lower_bound_seconds",
            )
    if baseline_seconds is not None and noise_seconds is not None:
        recomputed_threshold = max(0.05 * baseline_seconds, 2 * noise_seconds)
        check_close(
            threshold,
            recomputed_threshold,
            "cost_model.materiality_threshold_seconds",
        )
        if lower_bound is not None and lower_bound < recomputed_threshold:
            errors.append(f"{MATERIALITY_THRESHOLD_ERROR_PREFIX} {recomputed_threshold}")

    commands = root.get("measurement_commands")
    if (
        not isinstance(commands, list)
        or not commands
        or any(not isinstance(command, str) or not command.strip() for command in commands)
    ):
        errors.append("measurement_commands must contain non-empty command strings")
    assumptions = root.get("assumptions")
    if (
        not isinstance(assumptions, list)
        or not assumptions
        or any(
            not isinstance(assumption, str) or not assumption.strip() for assumption in assumptions
        )
    ):
        errors.append("assumptions must contain non-empty strings")

    return errors
