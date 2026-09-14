"""Start the worker API only on an explicitly configured Tailscale address."""
import ipaddress
import os

import uvicorn

from backend.live_store import LiveSettings


def control_host() -> str:
    raw = os.environ.get("MERGEN_CONTROL_HOST", "")
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise SystemExit("MERGEN_CONTROL_HOST must be a Tailscale IP address") from exc
    tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
    tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
    if address not in tailscale_v4 and address not in tailscale_v6:
        raise SystemExit("MERGEN_CONTROL_HOST must be a Tailscale IP address")
    if len(os.environ.get("MERGEN_CONTROL_TOKEN", "")) < 32:
        raise SystemExit("MERGEN_CONTROL_TOKEN must contain at least 32 characters")
    return str(address)


def validate_live_settings() -> None:
    # Fail at start, not on the first worker request: under systemd a missing
    # runtime path is a configuration error (see LiveSettings.from_env).
    try:
        LiveSettings.from_env()
    except ValueError as exc:
        raise SystemExit(f"Live settings are invalid: {exc}") from None


if __name__ == "__main__":
    host = control_host()
    validate_live_settings()
    uvicorn.run("backend.control:app", host=host, port=9100, access_log=False)
