"""Environment-only configuration.

Required values have no defaults. Every error names the variable, never its
value, so a misconfigured token cannot end up in the journal.
"""
from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from backend.live_contracts import valid_worker_id

GIB = 1024**3
TAILSCALE_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"),
                      ipaddress.ip_network("fd7a:115c:a1e0::/48"))


class ConfigError(ValueError):
    """A missing or unsafe setting. The message names the variable only."""


@dataclass(frozen=True)
class DispatcherConfig:
    control_url: str
    token: str = field(repr=False)
    worker_id: str
    runtime_root: Path
    poll_seconds: float = 15.0
    lease_renew_seconds: float = 60.0
    request_timeout_seconds: float = 30.0
    max_input_bytes: int = 2 * GIB
    max_expanded_bytes: int = 8 * GIB
    max_result_bytes: int = 2 * GIB
    # Fixed behaviour. Tests shorten these; an operator has no reason to.
    heartbeat_seconds: float = 30.0
    spool_poll_seconds: float = 2.0
    executor_stale_seconds: float = 90.0
    backoff_initial_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    transfer_attempts: int = 5

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DispatcherConfig":
        env = os.environ if environ is None else environ
        return cls(
            control_url=_control_url(env.get("MERGEN_CONTROL_URL", "")),
            token=_token(env.get("MERGEN_WORKER_TOKEN", "")),
            worker_id=_worker_id(env.get("MERGEN_WORKER_ID", "")),
            runtime_root=_absolute("MERGEN_RUNTIME_ROOT",
                                   env.get("MERGEN_RUNTIME_ROOT", "/var/lib/mergen/runtime")),
            poll_seconds=_number(env, "MERGEN_POLL_INTERVAL_SECONDS", 15, 1, 300),
            lease_renew_seconds=_number(env, "MERGEN_LEASE_RENEW_SECONDS", 60, 5, 600),
            request_timeout_seconds=_number(env, "MERGEN_REQUEST_TIMEOUT_SECONDS", 30, 1, 300),
            max_input_bytes=_integer(env, "MERGEN_MAX_INPUT_BYTES", 2 * GIB, 1, 64 * GIB),
            max_expanded_bytes=_integer(env, "MERGEN_MAX_EXPANDED_BYTES", 8 * GIB, 1, 64 * GIB),
            max_result_bytes=_integer(env, "MERGEN_MAX_RESULT_BYTES", 2 * GIB, 1, 64 * GIB),
        )


def _control_url(raw: str) -> str:
    name = "MERGEN_CONTROL_URL"
    if not raw:
        raise ConfigError(f"{name} is required")
    try:
        parts = urlsplit(raw)
        parts.port  # noqa: B018 - raises ValueError for an invalid port
    except ValueError:
        raise ConfigError(f"{name} is not a valid URL") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError(f"{name} must be an http or https URL")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ConfigError(f"{name} must be an origin only: no credentials, path, query or fragment")
    if parts.scheme == "http" and not _private_http_host(parts.hostname):
        # The token travels in a header; plain http is acceptable only where
        # WireGuard (Tailscale) or loopback already protects the bytes.
        raise ConfigError(f"{name} may use plain http only for a Tailscale or loopback address")
    return f"{parts.scheme}://{parts.netloc}"


def _private_http_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False  # a name, MagicDNS or public, needs TLS
    return address.is_loopback or any(address in network for network in TAILSCALE_NETWORKS)


def _token(raw: str) -> str:
    if len(raw) < 32:
        raise ConfigError("MERGEN_WORKER_TOKEN must contain at least 32 characters")
    if len(raw) > 4096 or not raw.isascii() or any(ch.isspace() or not ch.isprintable() for ch in raw):
        raise ConfigError("MERGEN_WORKER_TOKEN must be printable ASCII without whitespace")
    return raw


def _worker_id(raw: str) -> str:
    if not valid_worker_id(raw):
        raise ConfigError("MERGEN_WORKER_ID must be 2-63 lowercase letters, digits or hyphens")
    return raw


def _absolute(name: str, raw: str) -> Path:
    path = Path(raw)
    if not raw or not path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"{name} must be an absolute path without '..'")
    return path


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name)
    if raw is None:
        return float(default)
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


def _integer(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value
