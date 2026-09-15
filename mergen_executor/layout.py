"""Start-up checks: the executor refuses a spool it cannot trust.

The runtime root (tmpfiles) and jobs/ (dispatcher) belong to the spool owner;
the executor only verifies them. Its own state directory holds the pause file
and the GPU lock, so only the executor account (and root) may write there.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from mergen_spool import contract

ROOT_MODE = 0o2770


class LayoutError(RuntimeError):
    """The spool or the state directory is unsafe; the service must not start."""


def _directory(path: Path, label: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise LayoutError(f"{label} does not exist (see docs/GPU_HOST_RUNBOOK.md)") from None
    if not stat.S_ISDIR(info.st_mode):  # lstat: a link is not a directory
        raise LayoutError(f"{label} is not a real directory")
    return info


def verify_spool(runtime_root: Path, spool_owner_uid: int) -> None:
    root = _directory(runtime_root, "the runtime root")
    mode = stat.S_IMODE(root.st_mode)
    if mode != ROOT_MODE:
        raise LayoutError(f"the runtime root has mode {mode:04o}; the contract is {ROOT_MODE:04o}")
    if root.st_uid != spool_owner_uid:
        raise LayoutError("the runtime root is not owned by MERGEN_SPOOL_OWNER")
    if root.st_gid not in {os.getegid(), *os.getgroups()}:
        raise LayoutError("the executor is not a member of the runtime root's group")
    verify_jobs_directory(runtime_root, spool_owner_uid)


def verify_jobs_directory(runtime_root: Path, spool_owner_uid: int) -> bool:
    """False while the dispatcher has not created jobs/ yet; raises when it
    exists outside the contract, because then any job in it is suspect."""
    path = runtime_root / contract.JOBS_DIR
    if not os.path.lexists(path):
        return False
    info = _directory(path, "jobs/")
    mode = stat.S_IMODE(info.st_mode)
    if mode != contract.JOBS_MODE:
        raise LayoutError(f"jobs/ has mode {mode:04o}; the contract is {contract.JOBS_MODE:04o}")
    if info.st_uid != spool_owner_uid:
        raise LayoutError("jobs/ is not owned by MERGEN_SPOOL_OWNER")
    if info.st_gid != os.lstat(runtime_root).st_gid:
        raise LayoutError("jobs/ does not belong to the runtime root's group")
    return True


def verify_state(state_root: Path) -> None:
    info = _directory(state_root, "the executor state directory")
    if info.st_uid != os.geteuid():
        raise LayoutError("the executor state directory is not owned by the executor")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise LayoutError("the executor state directory is open to other accounts")
