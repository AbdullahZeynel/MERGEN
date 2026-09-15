"""Exec a model runner after Landlock confines all writes to one output tree."""
from __future__ import annotations

import argparse
import ctypes
import os
import platform
import sys

_CREATE, _ADD, _RESTRICT = 444, 445, 446
_VERSION = 1
_PATH_BENEATH = 1
_NO_NEW_PRIVS = 38
_WRITE = sum(1 << bit for bit in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14))


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneath(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32),
                ("reserved", ctypes.c_uint32)]


def supported() -> bool:
    if platform.system() != "Linux":
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    # ABI 2 adds REFER and ABI 3 adds TRUNCATE. Both are in _WRITE, so an
    # older ABI cannot enforce the complete write policy used below.
    return libc.syscall(_CREATE, 0, 0, _VERSION) >= 3


def confine_writes(output: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    ruleset = Ruleset(_WRITE)
    ruleset_fd = libc.syscall(_CREATE, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if ruleset_fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    output_fd = os.open(output, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        rule = PathBeneath(_WRITE, output_fd, 0)
        if libc.syscall(_ADD, ruleset_fd, _PATH_BENEATH, ctypes.byref(rule), 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_add_rule")
        if libc.prctl(_NO_NEW_PRIVS, 1, 0, 0, 0) < 0:
            raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
        if libc.syscall(_RESTRICT, ruleset_fd, 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(output_fd)
        os.close(ruleset_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--module", required=True)
    args = parser.parse_args()
    try:
        confine_writes(args.output)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("MERGEN_CONTROL_", "MERGEN_WORKER_", "MERGEN_VPS_"))}
        env.update(PYTHONDONTWRITEBYTECODE="1", TMPDIR=args.output, TEMP=args.output, TMP=args.output)
        os.execve(args.python, [args.python, "-P", "-m", args.module], env)
    except OSError:
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
