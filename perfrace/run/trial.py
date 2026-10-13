"""PerfRace-owned multi-checkpoint trial.

Agent execution and official verification share ``AgentConfig.task_budget_sec``
seconds in a persistent task container. Each turn receives the remaining budget;
after it returns, the loop checks whether to enter the final-delivery phase.
Final delivery receives the remaining agent time and is followed by verification.

Checkpoint outputs are archived under ``checkpoints/<name>/``. The first turn
receives ``instruction.md``; subsequent turns receive continuation guidance from
the latest measurement. Harbor supplies the underlying agent and verifier phases.
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Coroutine, override

from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.task import Task
from harbor.models.agent.context import AgentContext
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.result import ExceptionInfo, StepResult, TimingInfo
from harbor.tasks.client import TaskDownloadResult
from harbor.trial.errors import VerifierTimeoutError
from harbor.trial.trial import Trial

from perfrace.run.feedback import (
    continuation_guidance,
    with_verification_budget_guidance,
)
from perfrace.run.services.resources import (
    CpuLease,
    bind_environment_cpu_lease,
    get_host_cpu_allocator,
    trial_cpu_leases_enabled,
    unbind_environment_cpu_lease,
    write_cpu_compose_override,
)
from perfrace.run.services.gateway import read_token_proxy_summary
from perfrace.run.services.session_identity import token_proxy_api_key
from perfrace.run.types import PerfRaceConfig, Measurement
from perfrace.run.verifier import MEASUREMENT_FILENAME


def _with_trial_token_proxy_env(config: TrialConfig) -> TrialConfig:
    """Route a checkpoint agent through its per-trial token-proxy identity."""
    verifier_kwargs = getattr(getattr(config, "verifier", None), "kwargs", {})
    base_url = verifier_kwargs.get("container_token_proxy_base_url")
    secret = verifier_kwargs.get("token_proxy_secret")
    model = getattr(config.agent, "model_name", None)
    if not isinstance(base_url, str) or not isinstance(secret, str) or not model:
        return config

    session_id = f"{config.trial_name}__agent"
    env = {
        **config.agent.env,
        "LLM_BASE_URL": f"{base_url.rstrip('/')}/v1",
        "LLM_API_KEY": token_proxy_api_key(session_id, model, secret=secret),
        "LLM_MODEL": model,
    }
    return config.model_copy(update={"agent": config.agent.model_copy(update={"env": env})})


@dataclass(frozen=True)
class _TokenProxyUsage:
    """One cumulative token-proxy summary used for checkpoint deltas."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    requests: int
    cost_usd: float | None

    @classmethod
    def from_summary(cls, summary: dict[str, Any]) -> "_TokenProxyUsage":
        """Validate the cumulative counters returned by the proxy."""
        try:
            usage = cls(
                input_tokens=int(summary["input_tokens"]),
                cached_input_tokens=int(summary["cached_input_tokens"]),
                output_tokens=int(summary["output_tokens"]),
                requests=int(summary["requests"]),
                cost_usd=(
                    float(summary["cost_usd"]) if summary.get("cost_usd") is not None else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("token-proxy summary has invalid usage") from exc
        numeric = (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
            usage.requests,
        )
        if min(numeric) < 0 or (usage.cost_usd is not None and usage.cost_usd < 0):
            raise ValueError("token-proxy summary has negative usage")
        return usage

    def delta_from(self, previous: "_TokenProxyUsage") -> "_TokenProxyUsage":
        """Return usage accumulated since an earlier cumulative summary."""
        previous_cost = previous.cost_usd
        if previous_cost is None and previous.requests == 0:
            previous_cost = 0.0
        cost_usd = None
        if self.cost_usd is not None and previous_cost is not None:
            cost_usd = self.cost_usd - previous_cost
        delta = _TokenProxyUsage(
            input_tokens=self.input_tokens - previous.input_tokens,
            cached_input_tokens=self.cached_input_tokens - previous.cached_input_tokens,
            output_tokens=self.output_tokens - previous.output_tokens,
            requests=self.requests - previous.requests,
            cost_usd=cost_usd,
        )
        numeric = (
            delta.input_tokens,
            delta.cached_input_tokens,
            delta.output_tokens,
            delta.requests,
        )
        if min(numeric) < 0 or (delta.cost_usd is not None and delta.cost_usd < -1e-9):
            raise ValueError("token-proxy cumulative usage moved backwards")
        return delta


class CheckpointTrial(Trial):
    """Runs natural agent turns until their shared active-time budget expires.

    Completed research turns are verified while budget remains. Final delivery
    resumes the native agent session and is always followed by final scoring.
    """

    # Bounds _sync_agent_output()/_upload_agent_logs() -- copying agent
    # logs between the container and the host. A stuck docker exec here
    # has no timeout of its own and can hang indefinitely; must fail only
    # this checkpoint, not the whole trial.
    _LOG_SYNC_TIMEOUT_SEC = 300.0
    _FINAL_DELIVERY_NOTICE_SEC = 300.0
    _FINAL_DELIVERY_INSTRUCTION = (
        "The total work budget is ending. Stop starting new work. Leave the "
        "current workspace clean and coherent, then finish."
    )

    def __init__(
        self,
        config: TrialConfig,
        *,
        _task: Task | None = None,
        _task_download_result: TaskDownloadResult,
    ):
        task_budget_sec = config.agent.task_budget_sec
        if task_budget_sec is None or not math.isfinite(task_budget_sec) or task_budget_sec <= 300:
            raise ValueError("CheckpointTrial requires finite task_budget_sec > 300")
        config = _with_trial_token_proxy_env(config)
        super().__init__(
            config,
            _task=_task,
            _task_download_result=_task_download_result,
        )
        verifier_kwargs = getattr(getattr(config, "verifier", None), "kwargs", {})
        host_token_proxy_base_url = verifier_kwargs.get("host_token_proxy_base_url")
        self._host_token_proxy_base_url = (
            host_token_proxy_base_url.rstrip("/")
            if isinstance(host_token_proxy_base_url, str)
            else None
        )
        trial_name = getattr(config, "trial_name", "")
        self._token_proxy_session_id = f"{trial_name}__agent" if trial_name else ""
        self._pending_token_proxy_usage: _TokenProxyUsage | None = None
        self._trial_cpu_lease: CpuLease | None = None
        if trial_cpu_leases_enabled():
            perfrace_config = PerfRaceConfig.from_task_dir(self.task.task_dir)
            measurement = perfrace_config.measurement if perfrace_config is not None else None
            if measurement is None or measurement.repetition_scope != "internal":
                raise ValueError("trial CPU leases require an internal-repetition measurement")
        if (
            self._agent_timeout_sec is None
            or not math.isfinite(self._agent_timeout_sec)
            or self._agent_timeout_sec <= 0
        ):
            raise ValueError("CheckpointTrial requires a finite positive agent timeout")
        self._total_agent_budget_sec = float(task_budget_sec)
        if self._total_agent_budget_sec <= self._FINAL_DELIVERY_NOTICE_SEC:
            raise ValueError(
                "CheckpointTrial total agent budget must exceed its final delivery notice"
            )
        if not self.agent.SUPPORTS_RESUME:
            raise ValueError(
                f"Agent '{self.agent.name()}' does not support resume; "
                "cannot run a time-budgeted checkpoint trial"
            )
        if not callable(getattr(self.agent, "finalize", None)):
            raise ValueError(f"Agent '{self.agent.name()}' does not support final delivery")

    @override
    async def _prepare(self) -> None:
        if not trial_cpu_leases_enabled():
            await super()._prepare()
            return

        allocator = get_host_cpu_allocator()
        if allocator is None:
            raise RuntimeError("trial CPU leases require a host CPU allocator")
        if not isinstance(self.agent_environment, DockerEnvironment):
            raise ValueError("trial CPU leases require a Docker environment")
        count = self.agent_environment.effective_cpus
        if count is None or count < 1:
            raise ValueError("trial CPU leases require a positive task CPU count")

        lease = await allocator.acquire(count)
        self._trial_cpu_lease = lease
        bind_environment_cpu_lease(self.agent_environment, lease)
        compose_path = write_cpu_compose_override(
            self.paths.trial_dir / "trial-cpu-resources.json",
            lease,
        )
        self.agent_environment.extra_docker_compose_paths.append(compose_path)
        await super()._prepare()

    async def _release_trial_cpu_lease(self) -> None:
        lease = unbind_environment_cpu_lease(self.agent_environment)
        if lease is None:
            return
        await lease.release()
        self._trial_cpu_lease = None

    # -- checkpoint path helpers ------------------------------------------------
    # Own archiving layout under "checkpoints/<name>/", distinct from
    # Harbor's own "steps/<name>/" (TrialPaths.step_dir()).

    def _checkpoint_dir(self, name: str) -> Path:
        return self.paths.trial_dir / "checkpoints" / name

    def _checkpoint_verifier_dir(self, name: str) -> Path:
        return self._checkpoint_dir(name) / "verifier"

    def _checkpoint_agent_dir(self, name: str) -> Path:
        return self._checkpoint_dir(name) / "agent"

    def _checkpoint_artifacts_dir(self, name: str) -> Path:
        return self._checkpoint_dir(name) / "artifacts"

    def _checkpoint_resumes(self, index: int) -> bool:
        return index > 1

    def _iteration_name(self, index: int) -> str:
        return f"checkpoint-{index:02d}"

    async def _read_agent_token_proxy_usage(self) -> _TokenProxyUsage | None:
        """Read cumulative audited usage for this trial's agent session."""
        if self._host_token_proxy_base_url is None:
            return None
        summary = await read_token_proxy_summary(
            self._host_token_proxy_base_url,
            self._token_proxy_session_id,
        )
        if summary.get("session_id") != self._token_proxy_session_id:
            raise ValueError(
                "token-proxy summary session mismatch: "
                f"expected {self._token_proxy_session_id!r}, "
                f"got {summary.get('session_id')!r}"
            )
        return _TokenProxyUsage.from_summary(summary)

    async def _begin_checkpoint_token_accounting(self) -> None:
        """Capture the starting proxy counter for the next verified workspace."""
        if self._pending_token_proxy_usage is not None:
            return
        self._pending_token_proxy_usage = await self._read_agent_token_proxy_usage()

    async def _settle_checkpoint_token_accounting(self, step_result: StepResult) -> None:
        """Overwrite checkpoint token fields with the audited proxy delta."""
        before = self._pending_token_proxy_usage
        if before is None:
            return
        after = await self._read_agent_token_proxy_usage()
        if after is None:
            raise RuntimeError("token proxy became unavailable during checkpoint accounting")
        delta = after.delta_from(before)
        context = step_result.agent_result or AgentContext()
        context.n_input_tokens = delta.input_tokens
        context.n_cache_tokens = delta.cached_input_tokens
        context.n_output_tokens = delta.output_tokens
        context.cost_usd = max(delta.cost_usd, 0.0) if delta.cost_usd is not None else None
        metadata = dict(context.metadata or {})
        metadata["token_accounting"] = {
            "source": "token-proxy",
            "requests": delta.requests,
        }
        context.metadata = metadata
        step_result.agent_result = context
        self._pending_token_proxy_usage = None

    def _clear_agent_reported_token_usage(self, step_result: StepResult) -> None:
        """Reserve token fields for proxy accounting when the proxy is enabled."""
        if self._host_token_proxy_base_url is None or step_result.agent_result is None:
            return
        step_result.agent_result.n_input_tokens = None
        step_result.agent_result.n_cache_tokens = None
        step_result.agent_result.n_output_tokens = None
        step_result.agent_result.cost_usd = None

    async def _run_log_sync(
        self, coro: Coroutine[Any, Any, None], *, step_result: StepResult
    ) -> None:
        """Run ``_sync_agent_output()``/``_upload_agent_logs()`` under
        ``_LOG_SYNC_TIMEOUT_SEC``, recording (not raising) a timeout or
        any other failure -- an existing exception on ``step_result``
        (from the agent phase) is kept, not overwritten.
        """
        try:
            await asyncio.wait_for(coro, timeout=self._LOG_SYNC_TIMEOUT_SEC)
        except Exception as exc:
            if step_result.exception_info is None:
                step_result.exception_info = ExceptionInfo.from_exception(exc)

    # -- checkpoint reset helpers -------------------------------------------

    async def _reset_agent_logs_for_checkpoint(self, *, resume: bool) -> None:
        if self.agent_environment.capabilities.mounted:
            return
        # A resumed checkpoint continues the previous checkpoint's session,
        # which lives under the agent dir -- must survive, not be emptied.
        if resume:
            return
        await self.agent_environment.empty_dirs(
            [self.agent_env_paths.agent_dir],
            chmod=True,
        )

    async def _reset_shared_verifier_dirs_for_checkpoint(self) -> None:
        await self.agent_environment.empty_dirs(
            [self.agent_env_paths.verifier_dir],
            chmod=True,
        )
        await self.agent_environment.empty_dirs(
            [self.agent_env_paths.tests_dir],
            chmod=False,
        )

    def _archive_checkpoint_outputs(self, name: str, *, preserve_agent: bool) -> None:
        self._artifact_handler.move_dir_contents(
            self.paths.verifier_dir, self._checkpoint_verifier_dir(name)
        )
        if preserve_agent:
            # Copy the agent directory so the live session remains available for
            # resumption. Archive failures are logged without removing live state.
            if self.paths.agent_dir.exists():
                try:
                    shutil.copytree(
                        self.paths.agent_dir,
                        self._checkpoint_agent_dir(name),
                        symlinks=True,
                        dirs_exist_ok=True,
                    )
                except (OSError, shutil.Error) as exc:
                    self.logger.warning(
                        f"Checkpoint {name!r}: failed to archive a snapshot of "
                        f"the agent dir (live dir is unaffected, resume still "
                        f"works): {exc}"
                    )
        else:
            try:
                self._artifact_handler.move_dir_contents(
                    self.paths.agent_dir, self._checkpoint_agent_dir(name)
                )
            except (OSError, shutil.Error) as exc:
                self.logger.warning(f"Checkpoint {name!r}: failed to archive the agent dir: {exc}")
        try:
            self._artifact_handler.move_dir_contents_preserving(
                self.paths.artifacts_dir,
                self._checkpoint_artifacts_dir(name),
                preserve_dirs=[self._main_artifacts_mount_dir],
            )
        except (OSError, shutil.Error) as exc:
            self.logger.warning(f"Checkpoint {name!r}: failed to archive the artifacts dir: {exc}")

    # -- checkpoint measurement -------------------------------------------

    def _checkpoint_measurement(self, name: str) -> Measurement | None:
        """Read and parse this checkpoint's own archived measurement.json
        into a Measurement. Returns None if it's missing or invalid.
        """
        report_path = self._checkpoint_verifier_dir(name) / MEASUREMENT_FILENAME
        try:
            text = report_path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            return Measurement.model_validate(json.loads(text))
        except ValueError:
            return None

    async def _run_agent_iteration(
        self,
        *,
        name: str,
        instruction: str,
        timeout_sec: float | None,
        resume: bool,
    ) -> tuple[StepResult, bool, float]:
        step_result = StepResult(step_name=name)
        step_results = self.result.step_results
        if step_results is None:
            raise RuntimeError("Agent iteration requires initialized step results")
        step_results.append(step_result)
        self._checkpoint_dir(name).mkdir(parents=True, exist_ok=True)
        await self._reset_agent_logs_for_checkpoint(resume=resume)
        await self._begin_checkpoint_token_accounting()

        succeeded = True
        started = asyncio.get_running_loop().time()
        try:
            await self._run_agent_phase(
                target=step_result,
                instruction=instruction,
                timeout_sec=timeout_sec,
                user=self.task.config.agent.user,
                resume=resume,
            )
        except Exception as exc:
            succeeded = False
            step_result.exception_info = ExceptionInfo.from_exception(exc)
        finally:
            elapsed_sec = asyncio.get_running_loop().time() - started
            self._clear_agent_reported_token_usage(step_result)
            await self._run_log_sync(
                self._sync_agent_output(step_result),
                step_result=step_result,
            )
        await self._run_log_sync(
            self._upload_agent_logs(),
            step_result=step_result,
        )
        return step_result, succeeded, elapsed_sec

    async def _run_verifier_iteration(
        self,
        *,
        name: str,
        step_result: StepResult,
        preserve_agent: bool,
    ) -> Measurement | None:
        await self._reset_shared_verifier_dirs_for_checkpoint()
        step_result.verifier = TimingInfo(started_at=self._now())
        try:
            step_result.verifier_result = await self._run_shared_verifier(
                timeout_sec=self._verifier_timeout_sec,
                user=self.task.config.verifier.user,
                step_name=name,
            )
        except asyncio.TimeoutError as exc:
            if step_result.exception_info is None:
                step_result.exception_info = ExceptionInfo.from_exception(
                    VerifierTimeoutError(
                        f"Verifier execution timed out after {self._verifier_timeout_sec} seconds"
                    )
                )
            self.logger.debug(f"Checkpoint {name!r} verifier timed out: {exc}")
        except Exception as exc:
            if step_result.exception_info is None:
                step_result.exception_info = ExceptionInfo.from_exception(exc)
            self.logger.debug(f"Checkpoint {name!r} verifier failed: {exc}")
        finally:
            step_result.verifier.finished_at = self._now()

        await self._collect_artifacts_phased(artifacts_dir=self.paths.artifacts_dir)
        self._archive_checkpoint_outputs(name, preserve_agent=preserve_agent)
        return self._checkpoint_measurement(name)

    async def _run_budgeted_verifier_iteration(
        self,
        *,
        name: str,
        step_result: StepResult,
        preserve_agent: bool,
    ) -> tuple[float, Measurement | None]:
        """Run one official verification and return its elapsed time and report."""
        started = monotonic()
        measurement: Measurement | None = None
        try:
            measurement = await self._run_verifier_iteration(
                name=name,
                step_result=step_result,
                preserve_agent=preserve_agent,
            )
        finally:
            elapsed_sec = monotonic() - started
            self.logger.debug(
                "Checkpoint %s charged %.1fs verifier time to the shared work budget",
                name,
                elapsed_sec,
            )
        return elapsed_sec, measurement

    async def _workspace_fingerprint(self, *, name: str) -> str | None:
        """Return an optional agent-owned workspace fingerprint."""
        fingerprint_provider = getattr(self.agent, "checkpoint_fingerprint", None)
        if not callable(fingerprint_provider):
            return None
        try:
            return await fingerprint_provider(self.agent_environment)
        except Exception as exc:
            self.logger.warning(
                "Checkpoint %r workspace fingerprint failed; running verifier: %s",
                name,
                exc,
            )
            return None

    async def _reuse_checkpoint_measurement(
        self,
        *,
        name: str,
        source_name: str,
        preserve_agent: bool,
    ) -> Measurement:
        """Archive a checkpoint while reusing an identical workspace's report."""
        source = self._checkpoint_verifier_dir(source_name) / MEASUREMENT_FILENAME
        measurement = self._checkpoint_measurement(source_name)
        if measurement is None:
            raise RuntimeError(
                f"Cannot reuse missing or invalid measurement from checkpoint {source_name!r}"
            )
        destination_dir = self._checkpoint_verifier_dir(name)
        destination_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination_dir / MEASUREMENT_FILENAME)
        await self._collect_artifacts_phased(artifacts_dir=self.paths.artifacts_dir)
        self._archive_checkpoint_outputs(name, preserve_agent=preserve_agent)
        self.logger.info(
            "Checkpoint %r reused measurement from %r because the workspace "
            "fingerprint was unchanged",
            name,
            source_name,
        )
        return measurement

    async def _run_checkpoint_verifier(
        self,
        *,
        name: str,
        step_result: StepResult,
        preserve_agent: bool,
        fingerprint: str | None,
        last_verified_fingerprint: str | None,
        last_verified_name: str | None,
    ) -> tuple[float, Measurement | None, bool]:
        """Verify changed workspaces and reuse reports for identical ones."""
        reused = (
            fingerprint is not None
            and fingerprint == last_verified_fingerprint
            and last_verified_name is not None
        )
        if not reused:
            elapsed_sec, measurement = await self._run_budgeted_verifier_iteration(
                name=name,
                step_result=step_result,
                preserve_agent=preserve_agent,
            )
        else:
            started = monotonic()
            measurement = await self._reuse_checkpoint_measurement(
                name=name,
                source_name=last_verified_name,
                preserve_agent=preserve_agent,
            )
            elapsed_sec = monotonic() - started
        await self._settle_checkpoint_token_accounting(step_result)
        return elapsed_sec, measurement, reused

    async def _run_final_delivery(
        self,
        *,
        step_result: StepResult,
        timeout_sec: float,
    ) -> None:
        finalize = getattr(self.agent, "finalize")
        if step_result.agent_result is None:
            step_result.agent_result = AgentContext()
        if step_result.agent_execution is None:
            step_result.agent_execution = TimingInfo(started_at=self._now())
        if (
            step_result.exception_info is not None
            and step_result.exception_info.exception_type == "AgentTimeoutError"
        ):
            step_result.exception_info = None
        try:
            plan = self._network_plan()
            with self.agent_environment.with_default_user(self.task.config.agent.user):
                async with self._phase_network_policy(
                    self.agent_environment,
                    baseline_policy=plan.agent_env_baseline,
                    phase_policy=plan.agent_phase,
                ):
                    with self.agent_environment.scoped_exec_env(self.agent.extra_env):
                        with self._log_context("agent", self.agent_environment, None):
                            await asyncio.wait_for(
                                finalize(
                                    self._FINAL_DELIVERY_INSTRUCTION,
                                    self.agent_environment,
                                    step_result.agent_result,
                                ),
                                timeout=timeout_sec,
                            )
        except asyncio.TimeoutError:
            self.logger.debug(
                "Final delivery reached the shared agent deadline after %.1f seconds",
                timeout_sec,
            )
        except Exception as exc:
            if step_result.exception_info is None:
                step_result.exception_info = ExceptionInfo.from_exception(exc)
        finally:
            if step_result.agent_execution is not None:
                step_result.agent_execution.finished_at = self._now()
            self._clear_agent_reported_token_usage(step_result)
            await self._run_log_sync(
                self._sync_agent_output(step_result),
                step_result=step_result,
            )
            await self._run_log_sync(
                self._upload_agent_logs(),
                step_result=step_result,
            )

    async def _run_final_checkpoint(
        self,
        *,
        last_verified_fingerprint: str | None,
        last_verified_name: str | None,
        delivery_timeout_sec: float,
    ) -> None:
        """Run final delivery first, then score exactly the delivered workspace."""
        name = "final-delivery"
        step_result = StepResult(step_name=name)
        step_results = self.result.step_results
        if step_results is None:
            raise RuntimeError("Final checkpoint requires initialized step results")
        step_results.append(step_result)
        self._checkpoint_dir(name).mkdir(parents=True, exist_ok=True)
        await self._begin_checkpoint_token_accounting()

        if delivery_timeout_sec > 0:
            await self._run_final_delivery(
                step_result=step_result,
                timeout_sec=delivery_timeout_sec,
            )
        fingerprint = await self._workspace_fingerprint(name=name)
        _, measurement, reused = await self._run_checkpoint_verifier(
            name=name,
            step_result=step_result,
            preserve_agent=False,
            fingerprint=fingerprint,
            last_verified_fingerprint=last_verified_fingerprint,
            last_verified_name=last_verified_name,
        )
        self._write_progress()
        record_measurement = getattr(self.agent, "record_measurement", None)
        if measurement is not None and not reused and callable(record_measurement):
            await record_measurement(measurement, self.agent_environment)

    def _write_progress(self) -> None:
        """Publish the same TrialResult schema during execution for external viewers."""
        path = self.paths.trial_dir / "progress.json"
        pending = path.with_suffix(".tmp")
        pending.write_text(self.result.model_dump_json(indent=2), encoding="utf-8")
        pending.replace(path)

    # -- main loop ---------------------------------------------------------

    @override
    async def _run(self) -> None:
        self.result.step_results = []
        prepare = getattr(self.agent, "prepare_checkpoint_trial", None)
        if callable(prepare):
            await prepare(self.agent_environment)
        instruction = with_verification_budget_guidance(self.task.instruction)
        remaining_sec = self._total_agent_budget_sec
        index = 1
        last_verified_fingerprint: str | None = None
        last_verified_name: str | None = None

        while remaining_sec > self._FINAL_DELIVERY_NOTICE_SEC:
            name = self._iteration_name(index)
            budget_observer = getattr(self.agent, "set_checkpoint_budget", None)
            if callable(budget_observer):
                budget_observer(
                    total_sec=self._total_agent_budget_sec,
                    remaining_sec=remaining_sec,
                )
            step_result, _, elapsed_sec = await self._run_agent_iteration(
                name=name,
                instruction=instruction,
                timeout_sec=remaining_sec,
                resume=self._checkpoint_resumes(index),
            )
            remaining_sec = max(0.0, remaining_sec - elapsed_sec)
            skip_to_final = getattr(self.agent, "checkpoint_trial_skip_to_final_checkpoint", None)
            if callable(skip_to_final) and skip_to_final() is True:
                await self._settle_checkpoint_token_accounting(step_result)
                await self._collect_artifacts_phased(artifacts_dir=self.paths.artifacts_dir)
                self._archive_checkpoint_outputs(name, preserve_agent=True)
                break
            if remaining_sec <= self._FINAL_DELIVERY_NOTICE_SEC:
                break
            fingerprint = await self._workspace_fingerprint(name=name)
            (
                verifier_elapsed_sec,
                measurement,
                reused_measurement,
            ) = await self._run_checkpoint_verifier(
                name=name,
                step_result=step_result,
                preserve_agent=True,
                fingerprint=fingerprint,
                last_verified_fingerprint=last_verified_fingerprint,
                last_verified_name=last_verified_name,
            )
            if not reused_measurement and fingerprint is not None and measurement is not None:
                last_verified_fingerprint = fingerprint
                last_verified_name = name
            remaining_sec = max(0.0, remaining_sec - verifier_elapsed_sec)
            self._write_progress()
            record_measurement = getattr(self.agent, "record_measurement", None)
            if measurement is not None and not reused_measurement and callable(record_measurement):
                await record_measurement(measurement, self.agent_environment)
            if remaining_sec <= self._FINAL_DELIVERY_NOTICE_SEC:
                break
            instruction = continuation_guidance(measurement)
            index += 1

        await self._run_final_checkpoint(
            last_verified_fingerprint=last_verified_fingerprint,
            last_verified_name=last_verified_name,
            delivery_timeout_sec=remaining_sec,
        )
        await self._stop_agent_environment()
        self.paths.cleanup_empty_mount_dirs()

    @override
    async def _recover_outputs(self) -> None:
        await self._sync_agent_output(self.result)
        await self._stop_agent_environment()

    @override
    async def _finalize(self) -> None:
        try:
            await super()._finalize()
        finally:
            await self._release_trial_cpu_lease()
