"""Environment-only configuration.

There is no network setting and no credential here: nothing may name the VPS
or carry a token. Every error names the variable, never its value.
"""
from __future__ import annotations

import os
import pwd
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3


class ConfigError(ValueError):
    """A missing or unsafe setting. The message names the variable only."""


@dataclass(frozen=True)
class ExecutorConfig:
    runtime_root: Path
    state_root: Path
    spool_owner_uid: int
    pause_file: Path
    gpu_lock_path: Path
    poll_seconds: float = 2.0
    gpu_wait_seconds: float = 30.0
    max_input_bytes: int = 2 * GIB
    max_expanded_bytes: int = 8 * GIB
    max_result_bytes: int = 2 * GIB
    # Fixed: the dispatcher ignores a readiness document older than 90 s.
    ready_refresh_seconds: float = 30.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ExecutorConfig":
        env = os.environ if environ is None else environ
        state = _absolute("MERGEN_EXECUTOR_STATE",
                          env.get("MERGEN_EXECUTOR_STATE", "/var/lib/mergen/executor"))
        return cls(
            runtime_root=_absolute("MERGEN_RUNTIME_ROOT",
                                   env.get("MERGEN_RUNTIME_ROOT", "/var/lib/mergen/runtime")),
            state_root=state,
            spool_owner_uid=_account("MERGEN_SPOOL_OWNER",
                                     env.get("MERGEN_SPOOL_OWNER", "mergen-dispatcher")),
            pause_file=_inside(state, "MERGEN_PAUSE_FILE",
                               env.get("MERGEN_PAUSE_FILE", str(state / "pause"))),
            gpu_lock_path=_inside(state, "MERGEN_GPU_LOCK_PATH",
                                  env.get("MERGEN_GPU_LOCK_PATH", str(state / "gpu.lock"))),
            poll_seconds=_number(env, "MERGEN_EXECUTOR_POLL_SECONDS", 2, 0.5, 60),
            # Below the dispatcher's 90 s readiness window even while waiting.
            gpu_wait_seconds=_number(env, "MERGEN_GPU_WAIT_SECONDS", 30, 1, 60),
            max_input_bytes=_integer(env, "MERGEN_MAX_INPUT_BYTES", 2 * GIB, 1, 64 * GIB),
            max_expanded_bytes=_integer(env, "MERGEN_MAX_EXPANDED_BYTES", 8 * GIB, 1, 64 * GIB),
            max_result_bytes=_integer(env, "MERGEN_MAX_RESULT_BYTES", 2 * GIB, 1, 64 * GIB),
        )


def _absolute(name: str, raw: str) -> Path:
    path = Path(raw)
    if not raw or not path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"{name} must be an absolute path without '..'")
    return path


def _inside(state: Path, name: str, raw: str) -> Path:
    # Only the executor account (and root) can create files in its 0700 state
    # directory, so nobody else can pause it or take its GPU lock.
    path = _absolute(name, raw)
    if path.parent != state:
        raise ConfigError(f"{name} must name a file directly inside MERGEN_EXECUTOR_STATE")
    return path


def _account(name: str, raw: str) -> int:
    try:
        return pwd.getpwnam(raw).pw_uid
    except KeyError:
        raise ConfigError(f"{name} names no local account") from None


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
