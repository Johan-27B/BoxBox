"""Structured Filter judgments and normalized results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GateName = Literal[
    "accessible",
    "reproducibility",
    "evaluation_potential",
    "resource_feasibility",
]


class GateJudgment(BaseModel):
    """One evidence-based Filter gate decision."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    evidence: list[str] = Field(min_length=1)


class ResourceFeasibilityJudgment(GateJudgment):
    """Platform and hardware requirements for the proposed local process."""

    linux_x86_64_runnable: bool
    special_hardware_required: bool


class FilterGates(BaseModel):
    """The four Filter gate judgments."""

    model_config = ConfigDict(extra="forbid")

    accessible: GateJudgment
    reproducibility: GateJudgment
    evaluation_potential: GateJudgment
    resource_feasibility: ResourceFeasibilityJudgment


class PreliminaryProcess(BaseModel):
    """A plausible finite project process for Pair Verification."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    workload_carrier: Literal[
        "portable_artifact",
        "intrinsic_computation",
        "environment_bound",
        "private_trace_bound",
        "device_bound",
        "no_runtime_operation",
        "unresolved",
    ]
    setup_commands: list[str] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    smoke_command: str = Field(min_length=1)
    input: str = Field(min_length=1)
    output: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    correctness: str = Field(min_length=1)
    external_services: list[str] = Field(default_factory=list)


class OptimizationProfile(BaseModel):
    """A concise computation and performance-opportunity assessment."""

    model_config = ConfigDict(extra="forbid")

    computation: str = Field(min_length=1)
    potential: Literal["low", "medium", "high"]
    performance_hint: str = Field(min_length=1)


class ModelJudgment(BaseModel):
    """Strict model output before deterministic status derivation."""

    model_config = ConfigDict(extra="forbid")

    gates: FilterGates
    reason: str = Field(min_length=1)
    preliminary_process: PreliminaryProcess | None = None
    optimization_profile: OptimizationProfile

    @model_validator(mode="after")
    def require_process_for_evaluation(self) -> "ModelJudgment":
        if self.gates.evaluation_potential.passed and self.preliminary_process is None:
            raise ValueError("preliminary_process is required when evaluation potential passes")
        return self
