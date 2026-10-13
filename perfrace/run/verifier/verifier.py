"""PerfRace verifier adapter for Harbor trials.

Runs task.toml's declared ``n_repetitions`` copies of an instance's test
script, each inside its own disposable shadow container snapshotted from
the trial's own live state (see ``shadow.py``), with the PerfRace target
runtime environment. Every repetition reports its own outcome as the last
line of its stdout, JSON: ``{"correct": bool, "value": float | null}``.
This verifier aggregates all repetitions itself (see
``_aggregate_repetitions``) into one ``Measurement``, which it writes to
``measurement.json``.

Unlike a traditional terminal-bench-style verifier, which can compute its
own reward immediately, PerfRace's reward comes from comparing this
trial's metric value against the same task's ``nop``-baseline trial --
a comparison this verifier, scoped to one trial, can't make itself; see
``report.py`` for where it happens.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import statistics
from typing import Any

from harbor.environments.base import BaseEnvironment
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.task import Task
from harbor.models.trial.config import ServiceVolumeConfig
from harbor.models.trial.paths import EnvironmentPaths, TrialPaths
from harbor.models.verifier.result import VerifierResult
from harbor.utils.env import resolve_env_vars
from harbor.verifier.base import BaseVerifier

from perfrace.run.types import (
    LlmPricingConfig,
    Measurement,
    MeasurementConfig,
    PerfRaceConfig,
    VerifierVerdict,
)
from perfrace.run.services.session_identity import token_proxy_api_key
from perfrace.run.services.gateway import TokenProxyServiceError, read_token_proxy_summary
from perfrace.run.verifier.shadow import (
    ShadowRunResult,
    commit_snapshot,
    paused_main_container,
    repetition_session_id,
    run_measurement,
    sanitize_image_tag,
)

MEASUREMENT_FILENAME = "measurement.json"

# Default per-repetition timeout when verifier_timeout_sec is not supplied.
DEFAULT_REPETITION_TIMEOUT_SEC = 1800.0
# Reserved off the top of the overall verifier timeout for shadow
# teardown/result-collection overhead after the last repetition finishes.
REPETITION_TIMEOUT_BUFFER_SEC = 120.0


class PerfRaceVerifierResult(VerifierResult):
    """``VerifierResult`` enriched with the measurement produced, so
    callers (e.g. ``CheckpointTrial``'s checkpoint feedback) can react to
    it without re-reading ``measurement.json`` themselves.

    ``measurement`` is only ``None`` if ``verify()`` is never able to
    return one at all (a ``VerifierResult`` constructed some other way);
    ``PerfRaceVerifier.verify()`` itself always populates it when it
    returns normally, raising instead of returning if it can't.
    """

    measurement: Measurement | None = None


class PerfRaceVerifier(BaseVerifier):
    """Run task.toml's declared measurement repetitions and aggregate them.

    Registered via ``[verifier].import_path`` (Harbor's native
    ``VerifierFactory``/``BaseVerifier`` pluggability). ``task``/
    ``trial_paths``/``environment``/``override_env``/``logger``/
    ``verifier_env``/``step_name``/``include_logs``/``exclude_logs`` are
    ``BaseVerifier``'s own constructor parameters; everything else is
    PerfRace-owned execution context passed through ``[verifier].kwargs``.
    """

    def __init__(
        self,
        *,
        task: Task,
        trial_paths: TrialPaths,
        environment: BaseEnvironment,
        override_env: dict[str, str] | None = None,
        logger: logging.Logger | None = None,
        verifier_env: dict[str, str] | None = None,
        step_name: str | None = None,
        include_logs: list[str] | None = None,
        exclude_logs: list[str] | None = None,
        container_token_proxy_base_url: str | None = None,
        host_token_proxy_base_url: str | None = None,
        token_proxy_secret: str | None = None,
        verifier_timeout_sec: float | None = None,
        override_n_repetitions: int | None = None,
        **_: Any,
    ) -> None:
        if not isinstance(environment, DockerEnvironment):
            raise TypeError(
                f"PerfRaceVerifier requires a DockerEnvironment; got {type(environment).__name__}"
            )
        super().__init__(
            task=task,
            trial_paths=trial_paths,
            environment=environment,
            override_env=override_env,
            logger=logger,
            verifier_env=verifier_env,
            step_name=step_name,
            include_logs=include_logs,
            exclude_logs=exclude_logs,
        )
        self._docker_environment = environment
        self._container_token_proxy_base_url = _strip_url(container_token_proxy_base_url)
        self._host_token_proxy_base_url = _strip_url(host_token_proxy_base_url)
        self._token_proxy_secret = token_proxy_secret
        self._verifier_timeout_sec = verifier_timeout_sec
        self._override_n_repetitions = override_n_repetitions

    async def verify(self) -> VerifierResult:
        """Run instance tests and report what happened, writing this
        checkpoint's ``measurement.json`` before returning or raising so it
        always ends up with a verdict on disk.

        Reward computation happens in the runner, after ``Job.run()``
        completes and every task's nop-baseline trial can be paired with its
        candidate trial(s); a single verifier instance only ever sees one
        trial and cannot perform that pairing itself.
        """
        try:
            measurement_config = self._measurement_config()
            measurement = await self._run_measurement(measurement_config)
            self._write_measurement(measurement)
            return PerfRaceVerifierResult(measurement=measurement)
        except asyncio.CancelledError:
            self._write_stub_measurement("TIMEOUT")
            raise
        except Exception:
            self._write_stub_measurement("VERIFIER_ERROR")
            raise

    def _synthesize_measurement(
        self, verdict: VerifierVerdict, *, details: dict[str, Any] | None = None
    ) -> Measurement | None:
        """Build a placeholder ``value=None`` measurement for a checkpoint
        with no measurement of its own, sourcing metric/unit from task.toml.
        Returns ``None`` if task.toml has no usable
        ``[perfrace.measurement]`` table to source them from.
        """
        config = PerfRaceConfig.from_task_dir(self.task.task_dir)
        if config is None or config.measurement is None:
            return None
        return Measurement(
            verdict=verdict,
            value=None,
            metric=config.measurement.measurement,
            unit=config.measurement.unit or "unspecified",
            details=details or {},
        )

    def _write_measurement(self, measurement: Measurement) -> None:
        report_path = self.trial_paths.verifier_dir / MEASUREMENT_FILENAME
        try:
            report_path.write_text(measurement.model_dump_json(), encoding="utf-8")
        except OSError as exc:
            self.logger.warning(f"Failed to write {MEASUREMENT_FILENAME}: {exc}")

    def _write_stub_measurement(self, verdict: VerifierVerdict) -> None:
        measurement = self._synthesize_measurement(verdict)
        if measurement is not None:
            self._write_measurement(measurement)

    def _shadow_session_id(self) -> str:
        # self.environment.session_id is e.g. "eucalypt--eval-speed__aBc3D__env"
        # (Harbor's own f"{trial_name}__env" convention) -- drop that "__env"
        # role suffix and add this verifier's own, keeping step_name (e.g.
        # CheckpointTrial's "checkpoint-01") ahead of it so each checkpoint's
        # shadow gets its own distinct, addressable session.
        base = self.environment.session_id.removesuffix("__env")
        if self.step_name:
            return f"{base}__{self.step_name}__verify-shadow"
        return f"{base}__verify-shadow"

    def _test_script_path(self) -> str:
        return shlex.quote(
            str(
                EnvironmentPaths.tests_dir
                / self.task.paths.test_path.relative_to(self.task.paths.tests_dir)
            )
        )

    def _shadow_mounts(self) -> list[ServiceVolumeConfig]:
        #
        #  Bind mounts, not upload_dir(): declared before the shadow starts,
        # safe since this verifier is Docker-only, and shared read-only
        # across concurrent fanned-out shadows without copying.
        return [
            ServiceVolumeConfig(
                type="bind",
                source=self.trial_paths.verifier_dir.resolve().absolute().as_posix(),
                target=str(EnvironmentPaths.verifier_dir),
            ),
            ServiceVolumeConfig(
                type="bind",
                source=self.task.paths.tests_dir.resolve().absolute().as_posix(),
                target=str(EnvironmentPaths.tests_dir),
                read_only=True,
            ),
        ]

    def _measurement_config(self) -> MeasurementConfig:
        """task.toml's ``[perfrace.measurement]`` table, or raise -- every
        instance this verifier runs against must declare one; there's no
        legitimate verification outcome without a metric/unit to report.

        ``override_n_repetitions`` (job-config-owned, like
        ``max_concurrent_shadows``), when set, replaces task.toml's own
        declared ``n_repetitions`` -- e.g. for a cheap smoke run that
        shouldn't wait for a task's real repetition count.
        """
        config = PerfRaceConfig.from_task_dir(self.task.task_dir)
        if config is None or config.measurement is None:
            raise ValueError(
                f"{self.task.name}: task.toml has no usable [perfrace.measurement] table"
            )
        measurement_config = config.measurement
        if self._override_n_repetitions is not None:
            measurement_config = measurement_config.model_copy(
                update={"n_repetitions": self._override_n_repetitions}
            )
        return measurement_config

    def _target_runtime_env(self, *, session_id: str | None = None) -> dict[str, str]:
        # Mirrors Harbor's own native Verifier.verify() precedence
        # (task-level < verifier_env < job-level override_env), since
        # BaseVerifier subclasses don't get this merge for free -- each
        # implements verify()/its own env assembly independently.
        merged_env = {
            **self.task.config.verifier.env,
            **(self.verifier_env or {}),
            **self.override_env,
        }
        env = resolve_env_vars(merged_env) if merged_env else {}
        if self._container_token_proxy_base_url is None:
            return env

        model = _task_llm_model(self.task)
        if model is None:
            return env

        if self._token_proxy_secret is None:
            return env

        session_id = session_id or self.environment.session_id
        api_key = token_proxy_api_key(session_id, model, secret=self._token_proxy_secret)

        env.update(
            {
                "LLM_BASE_URL": f"{self._container_token_proxy_base_url}/v1",
                "LLM_API_KEY": api_key,
                "LLM_MODEL": model,
                "PERFRACE_TOKEN_PROXY_RESET_URL": (
                    f"{self._container_token_proxy_base_url}/sessions/{session_id}/reset"
                ),
                "PERFRACE_TOKEN_PROXY_SUMMARY_URL": (
                    f"{self._container_token_proxy_base_url}/sessions/{session_id}/summary"
                ),
            }
        )
        return env

    async def _read_token_proxy_summary(self, session_id: str) -> dict[str, Any]:
        """Read one shadow's audited usage from the host-only token proxy."""
        if self._host_token_proxy_base_url is None:
            raise ValueError("llm-cost measurement requires host_token_proxy_base_url")
        try:
            return await read_token_proxy_summary(
                self._host_token_proxy_base_url,
                session_id,
            )
        except TokenProxyServiceError as exc:
            raise ValueError(str(exc)) from exc

    async def _llm_cost_details(
        self,
        *,
        session_id: str,
        model: str,
        pricing: LlmPricingConfig,
    ) -> dict[str, Any]:
        """Compute one shadow's USD reference cost from audited proxy usage."""
        summary = await self._read_token_proxy_summary(session_id)
        summary_model = summary.get("model")
        if summary_model != model:
            raise ValueError(
                f"token-proxy summary model mismatch for {session_id}: "
                f"expected {model!r}, got {summary_model!r}"
            )
        try:
            input_tokens = int(summary["input_tokens"])
            cached_input_tokens = int(summary["cached_input_tokens"])
            output_tokens = int(summary["output_tokens"])
            requests = int(summary["requests"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"token-proxy summary for {session_id} has invalid usage") from exc
        if min(input_tokens, cached_input_tokens, output_tokens, requests) < 0:
            raise ValueError(f"token-proxy summary for {session_id} has negative usage")

        uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
        return {
            "cost_usd": pricing.estimate_usd(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
            ),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "uncached_input_tokens": uncached_input_tokens,
            "output_tokens": output_tokens,
            "requests": requests,
            "model": model,
            "pricing": pricing.model_dump(mode="json"),
        }

    async def _run_measurement(self, measurement_config: MeasurementConfig) -> Measurement:
        """Run this test script as one or more independent shadows,
        snapshotted from this checkpoint's current environment state (see
        ``shadow.run_measurement``), then aggregate the result(s) (see
        ``_aggregate_repetitions``) into one ``Measurement``.

        ``measurement_config.repetition_scope`` decides how many: for the
        default ``"external"``, ``n`` is ``measurement_config.n_repetitions``
        (PerfRaceVerifier itself fans out and aggregates); for
        ``"internal"``, ``n`` is always 1 -- the test script handles its own
        repetition and reports one already-aggregated result, which
        ``_aggregate_repetitions`` passes through unchanged since there's
        only ever one to aggregate.

        Every repetition captures its own stdout in memory (see
        ``shadow.py``) rather than redirecting to one shared host file,
        since concurrent repetitions can't all redirect to the same path.
        """
        command = f"bash {self._test_script_path()}"
        session_id = self._shadow_session_id()
        tag = sanitize_image_tag(f"perfrace-shadow-{session_id}")
        await commit_snapshot(self._docker_environment, tag)
        n = (
            1
            if measurement_config.repetition_scope == "internal"
            else measurement_config.n_repetitions
        )
        async with paused_main_container(self._docker_environment):
            results = await run_measurement(
                self._docker_environment,
                tag,
                command,
                n=n,
                timeout_sec=self._repetition_timeout_sec(),
                trial_paths=self.trial_paths,
                environment_name=self.task.short_name,
                base_session_id=session_id,
                mounts=self._shadow_mounts(),
                env_factory=lambda rep_session_id: (
                    self._target_runtime_env(session_id=rep_session_id) or None
                ),
            )
        if measurement_config.measurement != "llm-cost":
            return self._aggregate_repetitions(results, measurement_config)

        config = PerfRaceConfig.from_task_dir(self.task.task_dir)
        if config is None or config.llm is None or config.llm.pricing is None:
            raise ValueError(f"{self.task.name}: llm-cost requires [perfrace.llm.pricing]")
        cost_details: list[dict[str, Any] | None] = [None] * n
        pending_costs = [
            (
                index,
                self._llm_cost_details(
                    session_id=repetition_session_id(session_id, index),
                    model=config.llm.model,
                    pricing=config.llm.pricing,
                ),
            )
            for index, result in enumerate(results, start=1)
            if result.exit_code != -1 and not result.timed_out
        ]
        completed_costs = await asyncio.gather(*(coro for _, coro in pending_costs))
        for (index, _), detail in zip(pending_costs, completed_costs, strict=True):
            cost_details[index - 1] = detail
        return self._aggregate_repetitions(
            results,
            measurement_config,
            llm_cost_details=cost_details,
        )

    def _repetition_timeout_sec(self) -> float:
        if self._verifier_timeout_sec is None:
            return DEFAULT_REPETITION_TIMEOUT_SEC
        return max(60.0, self._verifier_timeout_sec - REPETITION_TIMEOUT_BUFFER_SEC)

    def _aggregate_repetitions(
        self,
        results: list[ShadowRunResult],
        measurement_config: MeasurementConfig,
        *,
        llm_cost_details: list[dict[str, Any] | None] | None = None,
    ) -> Measurement:
        """Combine every repetition's own ``{"correct": bool, "value": ...,
        "details": {...}}`` result into one ``Measurement``: the overall verdict is ACCEPTED
        only if the fraction reporting ``correct`` meets task.toml's
        ``min_pass_rate``; the reported value is the mean of every
        repetition's own non-null value (including from repetitions that
        were themselves incorrect -- a failed repetition still cost real
        work), reported only when the overall verdict is ACCEPTED.
        """
        if llm_cost_details is not None and len(llm_cost_details) != len(results):
            raise ValueError("llm-cost detail count does not match repetition count")

        per_repetition = []
        for index, result in enumerate(results, start=1):
            repetition = self._parse_repetition_result(result, index=index)
            cost_detail = llm_cost_details[index - 1] if llm_cost_details is not None else None
            if cost_detail is not None:
                repetition["reported_value"] = repetition["value"]
                repetition["value"] = cost_detail["cost_usd"]
                repetition["token_usage"] = cost_detail
            per_repetition.append(repetition)
        n = len(per_repetition)
        pass_rate = sum(1 for r in per_repetition if r["correct"]) / n if n else 0.0
        overall_correct = pass_rate >= measurement_config.min_pass_rate
        values = [r["value"] for r in per_repetition if r["value"] is not None]
        aggregated_value = statistics.mean(values) if values else None
        return Measurement(
            verdict="ACCEPTED" if overall_correct else "WRONG_ANSWER",
            value=aggregated_value if overall_correct else None,
            metric=measurement_config.measurement,
            unit=measurement_config.unit or "unspecified",
            details={
                "repetitions": per_repetition,
                "pass_rate": pass_rate,
                "min_pass_rate": measurement_config.min_pass_rate,
            },
        )

    def _parse_repetition_result(self, result: ShadowRunResult, *, index: int) -> dict[str, Any]:
        """A repetition whose shadow never produced real output (an infra
        failure or its own inner timeout -- see ``shadow.run_measurement``)
        counts as a normal failed repetition, not a protocol violation --
        there's nothing to parse. A repetition that ran to completion but
        whose last stdout line isn't the declared ``{"correct": bool,
        "value": ..., "details": object?}`` JSON is a genuine protocol violation (a
        task-authoring bug) and raises.
        """
        if result.exit_code == -1 or result.timed_out:
            parsed: dict[str, Any] = {"correct": False, "value": None}
            if result.host_resources is not None:
                parsed["host_resources"] = result.host_resources
            return parsed
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise ValueError(f"{self.task.name}: repetition {index} produced no stdout to parse")
        try:
            raw = json.loads(lines[-1])
        except ValueError as exc:
            raise ValueError(
                f"{self.task.name}: repetition {index}'s last stdout line is not valid "
                f"JSON: {lines[-1]!r}"
            ) from exc
        if not isinstance(raw, dict) or "correct" not in raw:
            raise ValueError(
                f"{self.task.name}: repetition {index}'s stdout JSON is missing 'correct': {raw!r}"
            )
        parsed = {"correct": bool(raw["correct"]), "value": raw.get("value")}
        if "details" in raw:
            if not isinstance(raw["details"], dict):
                raise ValueError(
                    f"{self.task.name}: repetition {index}'s stdout JSON 'details' "
                    f"must be an object: {raw['details']!r}"
                )
            parsed["details"] = raw["details"]
        if result.host_resources is not None:
            parsed["host_resources"] = result.host_resources
        return parsed


def _task_llm_model(task: Task) -> str | None:
    config = PerfRaceConfig.from_task_dir(task.task_dir)
    if config is None or config.llm is None:
        return None
    return config.llm.model


def _strip_url(value: str | None) -> str | None:
    return value.rstrip("/") if value is not None else None
