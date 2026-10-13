"""Shared continuation feedback for PerfRace verifier outcomes."""

from __future__ import annotations

from perfrace.run.types import Measurement, VerifierVerdict

VERDICT_GUIDANCE: dict[VerifierVerdict, str] = {
    "ACCEPTED": (
        "Last checkpoint: ACCEPTED, {value} {unit}. Continue from the current "
        "workspace and use this result as evidence for what to do next."
    ),
    "WRONG_ANSWER": (
        "Last checkpoint: WRONG_ANSWER -- your last change broke correctness. "
        "Fix that first, before any new optimization. Check every workload you "
        "can run locally, not just the one you time yourself: your score "
        "depends on staying correct on workloads you cannot see directly, so a "
        "change that only looks correct on the timed workload is not enough."
    ),
    "OOM": (
        "Last checkpoint: OOM -- your last change used enough memory to get "
        "killed by the kernel OOM killer. Investigate memory usage before "
        "attempting any further optimization."
    ),
    "RUNTIME_ERROR": (
        "Last checkpoint: RUNTIME_ERROR -- the test script exited without "
        "producing a measurement (a crash or a build failure). Confirm the "
        "project still builds and runs at all before doing anything else."
    ),
    "TIMEOUT": (
        "Last checkpoint: TIMEOUT -- the verifier did not finish within its "
        "time budget. Normal implementations have enough time to finish, so "
        "treat this as evidence of a candidate regression rather than dismissing "
        "it as verifier slowness. The regression may be a hang or severe time or "
        "memory growth that appears only under other inputs, resource limits, or "
        "runtime settings. Restore general correctness and performance before "
        "adding more changes. Do not hard-code or tune specifically for one "
        "workload you can run locally: the verifier covers settings you cannot "
        "see directly."
    ),
    "VERIFIER_ERROR": (
        "Last checkpoint: VERIFIER_ERROR -- the verifier itself failed "
        "unexpectedly (not a normal pass/fail outcome). Confirm the project "
        "is in a sane, buildable, correct state before continuing."
    ),
}

NO_MEASUREMENT_GUIDANCE = (
    "No verifier report is available from your last checkpoint. Confirm the "
    "project still builds and produces correct output before doing anything else."
)

VERIFICATION_BUDGET_GUIDANCE = (
    "Official verification elapsed time is deducted from the same remaining "
    "work budget as optimization."
)

MEASUREMENT_CONFIRMATION = """\
Original optimization task:
{original_task}

Current terminal state:
{terminal_output}

You requested official evaluation of the current candidate.
Official verification elapsed time is deducted from the same remaining work
budget as optimization.

[!] Submission checklist
Complete every item with evidence from the current trajectory:
- Candidate delta [TODO/DONE]: Identify the substantive candidate change made
  since task start or the most recent submit.
- Correctness [TODO/DONE]: Record the local end-to-end correctness command and
  successful result for the exact current candidate.
- Performance [TODO/DONE]: Record comparable workload measurements for the
  current candidate and the initial baseline or most recent official result.
- Signal [TODO/DONE]: Confirm that the measured speedup exceeds observed noise
  or variability.

When every item is DONE, call {completion_tool} again. Continue target research
or call self_rewrite while completing the checklist."""


def with_verification_budget_guidance(instruction: str) -> str:
    """Append the shared work-budget policy to a checkpoint task."""
    return f"{instruction}\n\nWork-budget policy:\n{VERIFICATION_BUDGET_GUIDANCE}"


def continuation_guidance(measurement: Measurement | None) -> str:
    """Return agent-independent feedback for the latest verifier outcome."""
    if measurement is None:
        outcome = NO_MEASUREMENT_GUIDANCE
    else:
        outcome = VERDICT_GUIDANCE[measurement.verdict].format(
            value=measurement.value,
            unit=measurement.unit,
        )
    return f"{outcome} {VERIFICATION_BUDGET_GUIDANCE}"
