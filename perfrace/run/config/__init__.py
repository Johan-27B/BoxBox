"""Load configuration for ``perfrace run``.

``load_run`` builds a ``LoadedRun`` from a YAML config file plus CLI
overrides. Each piece (Harbor's ``JobConfig``, PerfRace's ``ApiGatewayConfig``)
validates itself independently, and ``LoadedRun`` is a plain return-value container
with no cross-field rules of its own::

        enable_cache: true

        performance_profile: {}

        host_resources:
            enabled: true

        api_gateway:
            base_url: http://127.0.0.1:4000/v1
            api_key: sk-upstream-proxy-key

        job:
            jobs_dir: data/jobs
            tasks:
                - path: instances/eucalypt--eval-speed

PerfRace owns the top-level fields (baseline caching, host CPU allocation,
Docker performance profiling, host LLM gateway, patch-mode submission,
note/agent_tag, verifier,
multi-checkpoint evaluation).
Harbor owns the ``job`` schema: datasets, tasks, agents, orchestrator, environment,
artifacts, metrics, and timeouts all keep Harbor semantics -- the runner is the only
place that adds the unconditional ``nop`` baseline agent, after this module returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from perfrace.settings import expand_environment
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import AgentConfig
from pydantic import BaseModel, ConfigDict, ValidationError

from perfrace.run.config.gateway import ApiGatewayConfig
from perfrace.run.config.resources import HostResourcesConfig
from perfrace.installed import AGENT_IMPORT_PATHS

# All relative paths are resolved against the repository root so behavior does
# not depend on the caller's working directory.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JOBS_DIR = Path("data/jobs")
_CONTAINER_BASE_URL_REFERENCE = "${api_gateway.container_base_url}"
_API_KEY_REFERENCE = "${api_gateway.api_key}"


class RunConfigError(ValueError):
    """Raised when a PerfRace run config is invalid."""


class PerformanceProfileConfig(BaseModel):
    """Opt in to the PerfRace Docker performance-analysis profile."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


@dataclass(frozen=True)
class LoadedRun:
    """Resolved input for one ``perfrace run`` invocation.

    ``job`` preserves Harbor's native ``JobConfig`` semantics. The remaining
    fields are PerfRace-owned run concerns that Harbor does not model:
    submission replay, baseline caching, the optional host-side API gateway,
    and audit metadata.
    """

    job: JobConfig
    api_gateway: ApiGatewayConfig | None
    submission_path: Path | None
    enable_cache: bool
    performance_profile: PerformanceProfileConfig | None = None
    host_resources: HostResourcesConfig = field(default_factory=HostResourcesConfig)
    note: str | None = None
    agent_tag: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """A plain JSON-able rendering, e.g. for ``perfrace run --dry-run``."""
        return {
            "job": self.job.model_dump(mode="json"),
            "api_gateway": (
                self.api_gateway.model_dump(mode="json") if self.api_gateway is not None else None
            ),
            "submission_path": (
                str(self.submission_path) if self.submission_path is not None else None
            ),
            "enable_cache": self.enable_cache,
            "performance_profile": (
                self.performance_profile.model_dump(mode="json")
                if self.performance_profile is not None
                else None
            ),
            "host_resources": self.host_resources.model_dump(mode="json"),
            "note": self.note,
            "agent_tag": self.agent_tag,
        }


def load_run(
    config_path: Path | str | None = None,
    *,
    agent: str | None = None,
    model: str | None = None,
    n_attempts: int | None = None,
    job_name: str | None = None,
    jobs_dir: Path | None = None,
    enable_cache: bool | None = None,
    patch: Path | str | None = None,
    note: str | None = None,
    agent_tag: str | None = None,
) -> LoadedRun:
    """Load a run config from YAML plus CLI overrides."""
    if agent is not None and patch is not None:
        raise RunConfigError("--agent and --patch are mutually exclusive")

    raw = _load_yaml(config_path) if config_path is not None else {}
    if not isinstance(raw, dict):
        raise RunConfigError("Run config must be a mapping")
    if "patch_workspace_dir" in raw:
        raise RunConfigError(
            "patch_workspace_dir has been removed; set [environment].workdir in each task"
        )

    api_gateway = None
    if raw.get("api_gateway") is not None:
        try:
            api_gateway = ApiGatewayConfig.model_validate(raw["api_gateway"]).resolved()
        except (ValidationError, ValueError) as exc:
            raise RunConfigError(str(exc)) from exc
    try:
        host_resources = HostResourcesConfig.model_validate(raw.get("host_resources", {}))
    except ValidationError as exc:
        raise RunConfigError(str(exc)) from exc
    performance_profile = None
    if raw.get("performance_profile") is not None:
        try:
            performance_profile = PerformanceProfileConfig.model_validate(
                raw["performance_profile"]
            )
        except ValidationError as exc:
            raise RunConfigError(str(exc)) from exc

    job_payload = dict(raw.get("job") or {})
    job_payload.setdefault("jobs_dir", DEFAULT_JOBS_DIR)
    if job_name is not None:
        job_payload["job_name"] = job_name
    if jobs_dir is not None:
        job_payload["jobs_dir"] = jobs_dir
    job_payload["jobs_dir"] = _workspace_path(job_payload["jobs_dir"])

    if agent is not None:
        job_payload["agents"] = [_candidate_agent_config(agent, model)]
    else:
        # Harbor defaults an omitted agents list to a single oracle agent.
        # PerfRace's own nop-baseline-only runs (no --agent, no job.agents in
        # YAML) should have zero candidate agents, not an accidental oracle
        # run, so make the "no candidate agent" case explicit here.
        job_payload.setdefault("agents", [])
    if n_attempts is not None:
        job_payload["n_attempts"] = n_attempts

    try:
        job_payload = _resolve_agent_gateway_references(job_payload, api_gateway)
        agents = job_payload.get("agents", [])
        normalized = []
        for candidate in agents:
            candidate = (
                candidate.model_dump() if isinstance(candidate, AgentConfig) else dict(candidate)
            )
            if candidate.get("name") in AGENT_IMPORT_PATHS:
                candidate["import_path"] = AGENT_IMPORT_PATHS[candidate.pop("name")]
            if "task_budget_sec" in raw:
                candidate["task_budget_sec"] = raw["task_budget_sec"]
            if "checkpoints" in candidate:
                raise ValueError("Use task_budget_sec, not checkpoints")
            implementation = candidate.get("import_path") or ""
            if implementation in AGENT_IMPORT_PATHS.values():
                if candidate.get("task_budget_sec") is None:
                    raise ValueError(
                        "Set task_budget_sec explicitly for a task optimization agent"
                    )
                if not candidate.get("model_name"):
                    raise ValueError("Set model_name explicitly for a task optimization agent")
            normalized.append(candidate)
        job_payload["agents"] = normalized
        job = JobConfig.model_validate(job_payload)
    except (ValidationError, ValueError) as exc:
        raise RunConfigError(str(exc)) from exc

    # Precedence: an explicit --enable-cache/--no-enable-cache flag wins;
    # otherwise fall back to the run config's own top-level enable_cache
    # field; otherwise default to disabled,
    if enable_cache is None:
        enable_cache = bool(raw.get("enable_cache", False))

    if api_gateway is not None:
        api_gateway = api_gateway.model_copy(update={"log_dir": job.jobs_dir / job.job_name})

    if patch is not None:
        submission_path = _workspace_path(patch)
    elif raw.get("submission_path") is not None:
        submission_path = _workspace_path(raw["submission_path"])
    else:
        submission_path = None

    return LoadedRun(
        job=job,
        api_gateway=api_gateway,
        submission_path=submission_path,
        enable_cache=enable_cache,
        performance_profile=performance_profile,
        host_resources=host_resources,
        note=note if note is not None else raw.get("note"),
        agent_tag=agent_tag if agent_tag is not None else raw.get("agent_tag"),
    )


def _candidate_agent_config(agent: str, model: str | None) -> AgentConfig:
    """Build the candidate agent's config from ``--agent``/``--model``.

    ``agent`` is a registered Harbor agent name (e.g. ``"claude-code"``) or,
    if it contains ``:``, an import path (``module.path:ClassName``,
    Harbor's own convention -- see ``harbor.utils.import_path``). Never used
    to configure ``nop``: the baseline agent is always injected separately by
    the runner, never user-configured.
    """
    if agent in AGENT_IMPORT_PATHS:
        return AgentConfig(import_path=AGENT_IMPORT_PATHS[agent], model_name=model)
    if ":" in agent:
        return AgentConfig(import_path=agent, model_name=model)
    return AgentConfig(name=agent, model_name=model)


def _resolve_agent_gateway_references(
    job_payload: dict[str, Any],
    gateway: ApiGatewayConfig | None,
) -> dict[str, Any]:
    """Resolve gateway references in raw Harbor agent environment mappings.

    This loader owns the ``job.agents`` payload shape. It only recognizes the
    two declared PerfRace references, leaving every other Harbor env value
    unchanged before ``JobConfig`` validates the payload.
    """
    agents = job_payload.get("agents")
    if not isinstance(agents, list):
        return job_payload

    resolved_agents: list[object] = []
    for agent in agents:
        if not isinstance(agent, dict) or not isinstance(agent.get("env"), dict):
            resolved_agents.append(agent)
            continue
        resolved_agent = dict(agent)
        resolved_agent["env"] = {
            key: _resolve_agent_gateway_reference(value, gateway)
            for key, value in agent["env"].items()
        }
        resolved_agents.append(resolved_agent)

    resolved_payload = dict(job_payload)
    resolved_payload["agents"] = resolved_agents
    return resolved_payload


def _resolve_agent_gateway_reference(
    value: object,
    gateway: ApiGatewayConfig | None,
) -> object:
    """Resolve one explicit gateway reference without templating arbitrary values."""
    if value == _CONTAINER_BASE_URL_REFERENCE:
        if gateway is None:
            raise ValueError("${api_gateway.container_base_url} requires api_gateway")
        resolved = gateway.resolved_container_base_url()
        if resolved is None:
            raise ValueError("${api_gateway.container_base_url} requires api_gateway.base_url")
        return resolved
    if value == _API_KEY_REFERENCE:
        if gateway is None or gateway.api_key is None:
            raise ValueError("${api_gateway.api_key} requires api_gateway.api_key")
        return gateway.api_key
    return value


# =============================================================================
# Helpers for loading YAML and resolving workspace-relative paths.
# =============================================================================


def _load_yaml(path: Path | str) -> object:
    """Load a YAML document."""
    try:
        return expand_environment(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RunConfigError(f"Failed to read run config {path}: {exc}") from exc


def _workspace_path(value: Path | str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()
