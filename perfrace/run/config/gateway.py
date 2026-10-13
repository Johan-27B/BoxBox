"""PerfRace-owned configuration for host-side model gateways.

A local proxy declares its listener port once. The loader substitutes that
port into ``command`` and ``base_url``, then resolves the agent references
before constructing Harbor's native ``JobConfig``::

    api_gateway:
      port: 4000
      command: "/path/to/gateway --port ${api_gateway.port}"
      base_url: "http://localhost:${api_gateway.port}/v1"
      api_key: "${env:LLM_API_KEY}"

    job:
      agents:
        - name: copilot-cli
          env:
            COPILOT_PROVIDER_BASE_URL: "${api_gateway.container_base_url}"
            COPILOT_PROVIDER_API_KEY: "${api_gateway.api_key}"

The example agent receives ``http://host.docker.internal:4000/v1`` and the
proxy API key; provider credentials remain on the host-side proxy process.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

_PORT_REFERENCE = "${api_gateway.port}"
# A trial container cannot use these host-side loopback addresses directly.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


class ApiGatewayConfig(BaseModel):
    """Configure a host-side model gateway and its container-facing endpoint.

    ``port`` is the sole local listener-port declaration. ``command`` and
    ``base_url`` may reference it with ``${api_gateway.port}``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command: str | None = None
    healthcheck: str | None = None
    base_url: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    api_key: str | None = None
    log_dir: Path | None = None

    def resolved(self) -> "ApiGatewayConfig":
        """Materialize references and defaults for the runtime gateway config.

        ``LoadedRun`` records this concrete form so dry-run output, logs, and
        the gateway service all describe the same endpoint.
        """
        return self.model_copy(
            update={
                "command": self.resolved_command(),
                "base_url": self.resolved_base_url(),
                "healthcheck": self.resolved_healthcheck(),
            }
        )

    def resolved_command(self) -> str | None:
        """Return ``command`` with its optional port reference substituted."""
        return _resolve_port_reference(self.command, self.port)

    def resolved_base_url(self) -> str | None:
        """Return ``base_url`` with its optional port reference substituted."""
        return _resolve_port_reference(self.base_url, self.port)

    def resolved_container_base_url(self) -> str | None:
        """Translate the host gateway endpoint into a trial-container endpoint.

        A loopback host in ``base_url`` is reachable only from the PerfRace
        process. Docker trials instead reach that same host endpoint through
        ``host.docker.internal``; a non-loopback URL is already routable and
        is returned unchanged.

        Returns:
            The container-reachable URL, or ``None`` when no gateway endpoint
            is configured.

        Raises:
            ValueError: If ``base_url`` is not an absolute HTTP(S) URL.
        """
        base_url = self.resolved_base_url()
        if base_url is None:
            return None

        parsed = _parse_http_url(base_url)
        if parsed.hostname not in _LOOPBACK_HOSTS:
            return base_url
        netloc = "host.docker.internal"
        if parsed.port is not None:
            netloc += f":{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    def resolved_healthcheck(self) -> str | None:
        """Return the readiness endpoint for a gateway process started by this run.

        An explicit ``healthcheck`` always wins. Otherwise, a locally launched
        proxy uses ``/health/liveliness`` at ``base_url``'s origin. A remote
        gateway with no ``command`` is not polled implicitly.

        Returns:
            The healthcheck URL, or ``None`` when this run has nothing to
            launch or poll.
        """
        if self.healthcheck is not None:
            return self.healthcheck
        if self.command is None or self.resolved_base_url() is None:
            return None

        parsed = _parse_http_url(self.resolved_base_url() or "")
        return urlunsplit((parsed.scheme, parsed.netloc, "/health/liveliness", "", ""))


def _parse_http_url(value: str) -> SplitResult:
    """Parse the configured gateway endpoint before deriving an address from it.

    Raises:
        ValueError: If the endpoint is not an absolute HTTP(S) URL with a
            valid optional port.
    """
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("api_gateway.base_url must be an absolute http(s) URL")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("api_gateway.base_url has an invalid port") from exc
    return parsed


def _resolve_port_reference(value: str | None, port: int | None) -> str | None:
    """Replace the only supported command/base-URL reference with ``port``.

    ``None`` remains ``None`` so external proxies can omit ``command``. A
    literal value does not require a ``port`` field.
    """
    if value is None or _PORT_REFERENCE not in value:
        return value
    if port is None:
        raise ValueError("${api_gateway.port} requires api_gateway.port")
    return value.replace(_PORT_REFERENCE, str(port))
