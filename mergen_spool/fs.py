"""Filesystem primitives of the spool: atomic replace, bounded reads, locks.

Visibility and durability are separate problems. A rename makes a file or a
directory appear to the other process in one step, so it never sees a partial
write; fsync makes that state survive a power cut. Both sides use both. A
reader still verifies every checksum: fsync narrows the crash window, it does
not replace verification.
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import shutil
import stat
from pathlib import Path

MAX_CONTROL_BYTES = 64 * 1024
FILE_MODE = 0o660


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(path: Path, document: dict) -> None:
    """Write beside the target, fsync, rename over it, fsync the directory.

    A reader opens either the old file or the new one, never a partial one.
    """
    data = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    fsync_directory(path.parent)


def read_json(path: Path, limit: int = MAX_CONTROL_BYTES) -> object:
    """Read one small control file: no symlink, no FIFO or device, no more
    than `limit` bytes. Raises OSError or ValueError; never returns partial data."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("control file is not a regular file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("control file is too large")
    return json.loads(data)


def write_json_atomic_at(dir_fd: int, name: str, document: dict) -> None:
    """write_json_atomic relative to an open directory descriptor.

    The write lands in the directory the caller holds even if its path has
    changed since, which is how the executor works inside a job directory.
    """
    data = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    temporary = f".{name}.{secrets.token_hex(4)}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE,
                 dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        raise
    os.fsync(dir_fd)


def read_json_at(dir_fd: int, name: str, limit: int = MAX_CONTROL_BYTES) -> object:
    """read_json relative to an open directory descriptor."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("control file is not a regular file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("control file is too large")
    return json.loads(data)


def exists_at(dir_fd: int, name: str) -> bool:
    """Whether `name` exists in the directory, without following a link."""
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def create_marker(path: Path) -> bool:
    """Create an empty marker file once. False when it already exists."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
    except FileExistsError:
        return False
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_directory(path.parent)
    return True


def lock_directory(path: Path, *, blocking: bool) -> int | None:
    """Take the exclusive lock of a job directory.

    Returns the descriptor that holds it, or None when another process holds
    it and `blocking` is false. Closing the descriptor releases the lock.
    """
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        os.close(fd)
        return None
    except BaseException:
        os.close(fd)
        raise
    return fd


def remove_unlocked(path: Path) -> bool:
    """Delete a job directory only while nobody else holds its lock."""
    fd = lock_directory(path, blocking=False)
    if fd is None:
        return False
    try:
        shutil.rmtree(path)
    finally:
        os.close(fd)
    return True
