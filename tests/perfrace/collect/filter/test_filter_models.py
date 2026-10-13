from __future__ import annotations

import pytest
from pydantic import ValidationError

from perfrace.collect.filter.models import ModelJudgment


def _gates(evaluation_passed: bool = True) -> dict[str, object]:
    return {
        "accessible": {"passed": True, "evidence": ["LICENSE"]},
        "reproducibility": {"passed": True, "evidence": ["package.json"]},
        "evaluation_potential": {
            "passed": evaluation_passed,
            "evidence": ["src/cli.ts"],
        },
        "resource_feasibility": {
            "passed": True,
            "evidence": ["Linux CPU-only"],
            "linux_x86_64_runnable": True,
            "special_hardware_required": False,
        },
    }


def test_judgment_requires_process_when_evaluation_passes() -> None:
    with pytest.raises(ValidationError, match="preliminary_process"):
        ModelJudgment.model_validate(
            {
                "gates": _gates(),
                "reason": "Pass.",
                "preliminary_process": None,
                "optimization_profile": {
                    "computation": "Batch compilation",
                    "potential": "high",
                    "performance_hint": "Repeated parsing and validation.",
                },
            }
        )


def test_judgment_accepts_failed_evaluation_without_process() -> None:
    judgment = ModelJudgment.model_validate(
        {
            "gates": _gates(evaluation_passed=False),
            "reason": "No finite process.",
            "preliminary_process": None,
            "optimization_profile": {
                "computation": "Remote request forwarding",
                "potential": "low",
                "performance_hint": "The local path only forwards requests.",
            },
        }
    )

    assert judgment.gates.evaluation_potential.passed is False
