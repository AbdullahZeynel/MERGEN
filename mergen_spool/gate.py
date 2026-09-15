"""The finalization gate: the order between a cancel and the executor's verdict.

Checking for `cancel` and then writing `completed` leaves a window in which a
cancel can land between the two. The gate closes it: the dispatcher creates
`cancel`, and the executor re-checks it and writes its terminal status, only
while holding an exclusive flock on the job's `gate` file. Each side's step is
therefore atomic with respect to the other's: the executor either sees the
cancel before it writes a verdict, or has written the verdict before the
cancel exists.

The gate is held for that short step only, never while an adapter runs, so a
cancel stays visible to a running job. flock is released when its holder
dies, so a crash cannot leave the gate taken.
"""
from __future__ import annotations

import fcntl
import os
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mergen_spool import contract
from mergen_spool.fs import FILE_MODE


class GateUnavailable(Exception):
    """The gate cannot order this step."""


class GateMissing(GateUnavailable):
    """There is no gate file, or not one of a version this code understands."""


class GateBusy(GateUnavailable):
    """The other side held the gate longer than the caller would wait."""


def create_gate(directory: Path) -> None:
    """Write the gate into a job directory that is not published yet."""
    fd = os.open(directory / contract.GATE_FILE,
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
    try:
        os.write(fd, contract.GATE_CONTENT)
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def finalization_gate(dir_fd: int, *, timeout: float) -> Iterator[None]:
    """Hold the gate of the job directory open as `dir_fd` for one short step."""
    try:
        fd = os.open(contract.GATE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except OSError:
        raise GateMissing("the job has no usable gate") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.pread(fd, 64, 0) != contract.GATE_CONTENT:
            raise GateMissing("the gate is not a version-1 gate")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise GateBusy("the gate stayed busy") from None
                time.sleep(0.005)
        yield
    finally:
        os.close(fd)  # releases the lock
