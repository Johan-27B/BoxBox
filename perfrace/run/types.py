"""Shared types for PerfRace run configuration, results, and caching."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from dirhash import dirhash
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ScoringDirection = Literal["minimize", "maximize"]

# One checkpoint's verify() outcome. ACCEPTED/WRONG_ANSWER/OOM/RUNTIME_ERROR
# are the four outcomes a shadow that ran to completion can produce; TIMEOUT/
# VERIFIER_ERROR cover verify() itself being cut off by the outer verifier
# timeout or raising an unexpected exception -- see PerfRaceVerifier.verify()
# for how each gets recorded.
VerifierVerdict = Literal[
    "ACCEPTED", "WRONG_ANSWER", "OOM", "RUNTIME_ERROR", "TIMEOUT", "VERIFIER_ERROR"
]


# ---------------------------------------------------------------------------
# PerfRace measurement reports
# ---------------------------------------------------------------------------


class Measurement(BaseModel):
    """PerfRace measurement result for one verifier run.

    ``details`` is opaque to PerfRace core. Token workloads may store per-run
    token breakdowns there, while wall-clock or throughput instances can store
    their own diagnostics without changing the top-level contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: int = Field(default=1, ge=1)
    verdict: VerifierVerdict
    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    value: int | float | None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_value(self) -> "Measurement":
        if self.verdict == "ACCEPTED" and self.value is None:
            raise ValueError("ACCEPTED measurements must include value")
        return self

    def reward_against(self, baseline: "Measurement", direction: ScoringDirection) -> float:
        """Compute this measurement's reward relative to a baseline measurement.

        Callers are responsible for confirming ``baseline`` and this
        measurement belong to the same task (e.g. by comparing Harbor's own
        ``TrialResult.task_name`` for each) before calling this method.
        """
        if baseline.metric != self.metric:
            raise ValueError(
                f"metric mismatch: baseline={baseline.metric!r} candidate={self.metric!r}"
            )
        if baseline.unit != self.unit:
            raise ValueError(f"unit mismatch: baseline={baseline.unit!r} candidate={self.unit!r}")

        if self.verdict != "ACCEPTED" or self.value is None:
            return 0.0
        if baseline.verdict != "ACCEPTED" or baseline.value is None:
            raise ValueError("baseline measurement must be ACCEPTED and include value")

        baseline_value = float(baseline.value)
        candidate_value = float(self.value)
        if baseline_value <= 0 or candidate_value <= 0:
            raise ValueError("reward computation requires positive measurement values")

        if direction == "minimize":
            return baseline_value / candidate_value
        if direction == "maximize":
            return candidate_value / baseline_value
        raise ValueError(f"Unsupported scoring direction: {direction}")


# ---------------------------------------------------------------------------
# Instance metadata
# ---------------------------------------------------------------------------


class PerfRaceConfig(BaseModel):
    """Task identity and measurement configuration parsed from ``task.toml``.

    Task names follow Harbor's name and directory fallback rules. The loader
    validates the measurement and LLM sub-tables independently; use
    ``perfrace lint`` to validate the complete task schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: Path
    task_name: str
    instance_id: str
    measurement: MeasurementConfig | None = None
    llm: LlmConfig | None = None
    task_checksum: str | None = None

    @property
    def requires_llm_token_proxy(self) -> bool:
        return self.measurement is not None and self.measurement.measurement in {
            "llm-tokens",
            "llm-cost",
        }

    @property
    def cache_fields(self) -> dict[str, Any] | None:
        """This instance's contribution to a PerfRace baseline cache key
        (see ``cache.py::baseline_cache_key``): its measurement protocol plus
        its content checksum, so the cache invalidates whenever either
        changes. ``None`` if this instance has no usable measurement
        protocol, or wasn't loaded with ``include_checksum=True``.
        """
        if self.measurement is None or self.measurement.unit is None:
            return None
        if self.task_checksum is None:
            return None
        return {
            "metric": self.measurement.measurement,
            "unit": self.measurement.unit,
            "direction": self.measurement.direction,
            "llm_model": self.llm.model if self.llm is not None else None,
            "task_checksum": self.task_checksum,
            "trial_schema_version": Measurement.model_fields["schema_version"].default,
        }

    @classmethod
    def from_task_dir(
        cls, task_dir: Path, *, include_checksum: bool = False
    ) -> "PerfRaceConfig | None":
        """Load and validate ``task_dir/task.toml``.

        Returns ``None`` for missing or unreadable configuration, a missing
        ``[perfrace]`` table, or invalid measurement/LLM sub-tables.
        ``include_checksum`` also hashes the task directory for cache keys.
        """
        try:
            data = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            return None

        perfrace = data.get("perfrace")
        if not isinstance(perfrace, dict):
            return None

        task_table = data.get("task")
        if isinstance(task_table, dict) and isinstance(task_table.get("name"), str):
            task_name = task_table["name"]
            instance_id = task_name.split("/", 1)[-1]
        else:
            task_name = task_dir.name
            instance_id = task_dir.name

        measurement_data = perfrace.get("measurement")
        measurement = None
        if measurement_data is not None:
            try:
                measurement = MeasurementConfig.model_validate(measurement_data)
            except ValidationError:
                return None

        llm_data = perfrace.get("llm")
        llm = None
        if llm_data is not None:
            try:
                llm = LlmConfig.model_validate(llm_data)
            except ValidationError:
                return None

        task_checksum = dirhash(task_dir, "sha256") if include_checksum else None
        return cls(
            path=task_dir,
            task_name=task_name,
            instance_id=instance_id,
            measurement=measurement,
            llm=llm,
            task_checksum=task_checksum,
        )


class MeasurementConfig(BaseModel):
    """Measurement protocol declared by an instance: what to measure, how
    many times, and how to reduce repeated readings to one number.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    measurement: str = Field(min_length=1)
    direction: ScoringDirection
    workload: str | None = None
    n_warmup: int = Field(default=0, ge=0)
    n_repetitions: int = Field(default=1, ge=1)
    aggregator: Literal["mean"] = "mean"
    min_pass_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    subject: str | None = None
    unit: str | None = None
    # Who runs n_repetitions: "external" (default) is PerfRaceVerifier
    # itself, fanning test.sh out across n_repetitions shadows and
    # aggregating; "internal" is test.sh's own loop, reporting one
    # already-aggregated result that PerfRaceVerifier passes through.
    repetition_scope: Literal["external", "internal"] = "external"


class LlmPricingConfig(BaseModel):
    """Versioned reference rates for one LLM-backed task's USD measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    currency: Literal["USD"] = "USD"
    input_usd_per_million_tokens: float = Field(gt=0)
    cached_input_usd_per_million_tokens: float = Field(ge=0)
    output_usd_per_million_tokens: float = Field(gt=0)

    def estimate_usd(
        self,
        *,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Return the reference cost, billing cached input at its declared rate."""
        uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
        return (
            uncached_input_tokens * self.input_usd_per_million_tokens
            + cached_input_tokens * self.cached_input_usd_per_million_tokens
            + output_tokens * self.output_usd_per_million_tokens
        ) / 1_000_000


class LlmConfig(BaseModel):
    """Stable model identifier required by an LLM-backed instance."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: str = Field(min_length=1)
    pricing: LlmPricingConfig | None = None


PerfRaceConfig.model_rebuild()


# ---------------------------------------------------------------------------
# run.json (PerfRace's own audit summary beside Harbor's job outputs)
# ---------------------------------------------------------------------------


class RunTrialSummary(BaseModel):
    """One Harbor trial's entry in ``run.json``.

    The same shape is used for the nop-baseline trial and for each candidate
    trial. ``perf_trial``/``error`` are mutually exclusive (whichever the
    trial's ``measurement.json`` read produced); ``reward``/``reward_error``
    are only ever set on candidate entries, once a baseline is available to
    pair against.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    trial_name: str
    agent: str
    trial_uri: str
    artifact: str
    perf_trial: Measurement | None = None
    error: str | None = None
    reward: float | None = None
    reward_error: str | None = None


class RunTaskSummary(BaseModel):
    """One task's nop-baseline trial paired with its candidate trial(s)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_name: str
    baseline: RunTrialSummary | None
    candidates: list[RunTrialSummary] = Field(default_factory=list)


class RunSummary(BaseModel):
    """PerfRace's own audit summary for one Harbor job, written as ``run.json``.

    ``git_commit`` records the PerfRace commit this run executed at. The
    resolved Harbor job config itself (tasks/agents/environment/orchestrator)
    is written alongside this file as ``job.yaml``, not embedded here, so
    reproducing a run means replaying that YAML at this commit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: int = Field(default=2, ge=1)
    job_name: str
    note: str | None = None
    agent_tag: str | None = None
    enable_cache: bool
    used_api_gateway: bool
    git_commit: str | None = None
    trial_count: int = Field(ge=0)
    stats: dict[str, int] = Field(default_factory=dict)
    tasks: list[RunTaskSummary] = Field(default_factory=list)
