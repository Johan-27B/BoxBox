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


PROMOTION_SCHEMA_VERSION = 1
PROMOTION_MARGIN_ERROR_PREFIX = "promotion improvement does not clear the materiality threshold"


def validate_promotion_record(
    payload: Any,
    *,
    expected_candidate_commit: str,
) -> list[str]:
    """Validate the generic evidence packet required before official measurement.

    The packet is deliberately limited to claims the agent can make from the
    current workspace: comparable samples, a distinct candidate tree, and a
    correctness check. The verifier remains the authority for correctness and
    official timing.
    """
    errors: list[str] = []

    def mapping(value: Any, field: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        errors.append(f"{field} must be an object")
        return {}

    def positive_samples(value: Any, field: str) -> list[float]:
        if not isinstance(value, list) or len(value) < 3:
            errors.append(f"{field} must contain at least three samples")
            return []
        samples: list[float] = []
        for index, sample in enumerate(value):
            if isinstance(sample, bool) or not isinstance(sample, int | float):
                errors.append(f"{field}[{index}] must be a finite number")
                continue
            parsed = float(sample)
            if not math.isfinite(parsed) or parsed <= 0:
                errors.append(f"{field}[{index}] must be > 0 and finite")
                continue
            samples.append(parsed)
        return samples

    def required_string(value: Any, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")

    root = mapping(payload, "record")
    if root.get("schema_version") != PROMOTION_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PROMOTION_SCHEMA_VERSION}")
    if root.get("candidate_commit") != expected_candidate_commit:
        errors.append("candidate_commit must match the current HEAD")

    baseline_commit = root.get("baseline_commit")
    if (
        not isinstance(baseline_commit, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40}", baseline_commit)
    ):
        errors.append("baseline_commit must be a full commit hash")
    elif baseline_commit.lower() == expected_candidate_commit.lower():
        errors.append("baseline_commit must differ from candidate_commit")

    required_string(root.get("workload_command"), "workload_command")
    baseline = mapping(root.get("baseline"), "baseline")
    candidate = mapping(root.get("candidate"), "candidate")
    baseline_samples = positive_samples(
        baseline.get("samples_seconds"), "baseline.samples_seconds"
    )
    candidate_samples = positive_samples(
        candidate.get("samples_seconds"), "candidate.samples_seconds"
    )

    def check_statistics(
        record: dict[str, Any], samples: list[float], label: str
    ) -> tuple[float | None, float | None]:
        median = record.get("median_seconds")
        noise = record.get("noise_seconds")
        if (
            isinstance(median, bool)
            or not isinstance(median, int | float)
            or not math.isfinite(float(median))
            or float(median) <= 0
        ):
            errors.append(f"{label}.median_seconds must be > 0 and finite")
            median_value = None
        else:
            median_value = float(median)
        if (
            isinstance(noise, bool)
            or not isinstance(noise, int | float)
            or not math.isfinite(float(noise))
            or float(noise) < 0
        ):
            errors.append(f"{label}.noise_seconds must be >= 0 and finite")
            noise_value = None
        else:
            noise_value = float(noise)
        if len(samples) >= 3:
            recomputed_median = statistics.median(samples)
            recomputed_noise = 1.4826 * statistics.median(
                abs(sample - recomputed_median) for sample in samples
            )
            if median_value is not None and not math.isclose(
                median_value, recomputed_median, rel_tol=1e-6, abs_tol=1e-9
            ):
                errors.append(f"{label}.median_seconds must equal the median of samples")
            if noise_value is not None and not math.isclose(
                noise_value, recomputed_noise, rel_tol=1e-6, abs_tol=1e-9
            ):
                errors.append(f"{label}.noise_seconds must equal the robust noise estimate")
        return median_value, noise_value

    baseline_median, baseline_noise = check_statistics(baseline, baseline_samples, "baseline")
    candidate_median, _candidate_noise = check_statistics(candidate, candidate_samples, "candidate")

    correctness = mapping(root.get("correctness"), "correctness")
    if correctness.get("passed") is not True:
        errors.append("correctness.passed must be true")
    required_string(correctness.get("command"), "correctness.command")
    required_string(correctness.get("evidence"), "correctness.evidence")

    if baseline_median is not None and baseline_noise is not None and candidate_median is not None:
        threshold = max(0.05 * baseline_median, 2 * baseline_noise)
        improvement = baseline_median - candidate_median
        recorded_threshold = root.get("materiality_threshold_seconds")
        if (
            isinstance(recorded_threshold, bool)
            or not isinstance(recorded_threshold, int | float)
            or not math.isclose(float(recorded_threshold), threshold, rel_tol=1e-6, abs_tol=1e-9)
        ):
            errors.append("materiality_threshold_seconds must match the baseline noise threshold")
        if improvement < threshold:
            errors.append(f"{PROMOTION_MARGIN_ERROR_PREFIX}: need at least {threshold} seconds")

    return errors
