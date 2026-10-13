"""PerfRace-owned host resource allocation configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

DEFAULT_HOST_RESOURCE_LOCK_DIR = Path("/tmp/perfrace-host-resources")
DEFAULT_TRIAL_CONTROLLER_MEMORY_MB = 16 * 1024


class HostResourcesConfig(BaseModel):
    """Configure host-side resources used by local measurement shadows."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    enabled: bool = True
    trial_cpu_leases: bool = False
    trial_process_isolation: bool = False
    trial_controller_memory_mb: int = DEFAULT_TRIAL_CONTROLLER_MEMORY_MB
    lock_dir: Path = DEFAULT_HOST_RESOURCE_LOCK_DIR

    @field_validator("trial_controller_memory_mb")
    @classmethod
    def require_positive_controller_memory(cls, value: int) -> int:
        """Require a usable cgroup MemoryMax when process isolation is enabled."""
        if value < 1:
            raise ValueError("host_resources.trial_controller_memory_mb must be positive")
        return value

    @model_validator(mode="after")
    def require_enabled_host_resources(self) -> "HostResourcesConfig":
        """Reject contradictory isolation settings instead of silently disabling them."""
        if self.trial_process_isolation and not self.enabled:
            raise ValueError(
                "host_resources.trial_process_isolation requires host_resources.enabled"
            )
        return self

    @field_validator("lock_dir", mode="before")
    @classmethod
    def parse_lock_dir(cls, value: object) -> object:
        """Accept YAML path strings while retaining strict validation."""
        return Path(value) if isinstance(value, str) else value

    @field_validator("lock_dir")
    @classmethod
    def require_absolute_lock_dir(cls, value: Path) -> Path:
        """Require one unambiguous host-wide path across working directories."""
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("host_resources.lock_dir must be an absolute path")
        return expanded
