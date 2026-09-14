"""Refuse a VPS services.env that lacks explicit live runtime settings.

    python3 infra/vps/check_services_env.py /etc/mergen/services.env

install-services.sh never overwrites an existing services.env, so an upgrade
from the demo-only layout keeps a file without the live settings. The backend
refuses to guess them under systemd; this check makes the gap visible at
install time instead of at the first live request. It reports key names only
and never prints a value from the file.
"""
from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

REQUIRED = ("MERGEN_RUNTIME_ROOT", "MERGEN_DATABASE_PATH")


def parse_env(text: str) -> dict[str, str]:
    """The part of systemd EnvironmentFile syntax this file uses: KEY=VALUE,
    `#` and `;` comments, optional matching quotes. A later assignment
    overrides an earlier one, as it does for systemd."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;" or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def problems(values: dict[str, str]) -> list[str]:
    found: list[str] = []
    paths: dict[str, PurePosixPath] = {}
    for key in REQUIRED:
        value = values.get(key, "")
        if not value:
            found.append(f"{key} is missing or empty")
            continue
        path = PurePosixPath(value)
        if not path.is_absolute() or ".." in path.parts:
            found.append(f"{key} must be an absolute path without '..'")
            continue
        paths[key] = path
    if len(paths) == len(REQUIRED) and not paths["MERGEN_DATABASE_PATH"].is_relative_to(
            paths["MERGEN_RUNTIME_ROOT"]):
        found.append("MERGEN_DATABASE_PATH must be inside MERGEN_RUNTIME_ROOT")
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_services_env.py ENV_FILE", file=sys.stderr)
        return 2
    try:
        text = Path(args[0]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print("services.env check: the file cannot be read", file=sys.stderr)
        return 1
    found = problems(parse_env(text))
    if not found:
        print("services.env check: live runtime settings are explicit")
        return 0
    print("services.env check failed (values are not printed):", file=sys.stderr)
    for item in found:
        print(f"  - {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
