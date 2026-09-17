"""Exec a model runner after Landlock confines all writes to one output tree.

The single exception is the NVIDIA compute nodes: the GPU is the point of this
process, and the driver cannot be opened read-only. Each node is named
explicitly and carries file rights only, so the rest of /dev stays closed.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import platform
import stat
import sys

_CREATE, _ADD, _RESTRICT = 444, 445, 446
_VERSION = 1
_PATH_BENEATH = 1
_NO_NEW_PRIVS = 38
_WRITE = sum(1 << bit for bit in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14))
# WRITE_FILE and TRUNCATE: the only rights of _WRITE a character device can
# carry. Granting the directory rights instead, or opening /dev as a tree,
# would let the runner create and unlink device nodes.
_DEVICE_WRITE = (1 << 1) | (1 << 14)
# The CUDA driver opens these nodes O_RDWR. Without a rule per node the
# confined runner initializes no driver at all and reports no GPU, which is
# indistinguishable from a host that has none. The list matches the unit's
# DeviceAllow lines: compute only, one device, no /dev/dri and no modeset.
DEVICE_NODES = ("/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools",
                "/dev/nvidia0")


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


def confine_writes(output: str, devices: tuple[str, ...] = DEVICE_NODES) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    ruleset = Ruleset(_WRITE)
    ruleset_fd = libc.syscall(_CREATE, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if ruleset_fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    try:
        _allow(libc, ruleset_fd, output, _WRITE,
               os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        for node in devices:
            # Only a real character device gets a rule. A missing node is a
            # host that lacks it; anything else there (a symlink, a regular
            # file someone dropped in) is refused rather than followed, and
            # the runner then finds no GPU.
            try:
                if not stat.S_ISCHR(os.lstat(node).st_mode):
                    continue
            except OSError:
                continue
            _allow(libc, ruleset_fd, node, _DEVICE_WRITE,
                   os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
        if libc.prctl(_NO_NEW_PRIVS, 1, 0, 0, 0) < 0:
            raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
        if libc.syscall(_RESTRICT, ruleset_fd, 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(ruleset_fd)


def _allow(libc, ruleset_fd: int, path: str, access: int, flags: int) -> None:
    path_fd = os.open(path, flags)
    try:
        rule = PathBeneath(access, path_fd, 0)
        if libc.syscall(_ADD, ruleset_fd, _PATH_BENEATH, ctypes.byref(rule), 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_add_rule")
    finally:
        os.close(path_fd)


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
