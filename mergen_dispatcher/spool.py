"""Dispatcher side of the spool: staging, atomic publication and recovery."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import shutil
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from mergen_spool import contract
from mergen_spool.fs import (create_marker, fsync_directory, lock_directory, read_json, remove_unlocked,
                             write_json_atomic)

LOG = logging.getLogger("mergen.dispatcher")
CHUNK = 1024 * 1024
JOB_NAME = re.compile(r"^[a-f0-9]{32}$")


class SpoolLayoutError(RuntimeError):
    """The runtime directory is unsafe to use; the service must not start."""


class SpoolViolation(Exception):
    """The executor side broke the contract; its output is not trusted."""


class Spool:
    def __init__(self, root: Path, max_result_bytes: int, wall: Callable[[], float] = time.time):
        self.root = root
        self.staging = root / contract.STAGING_DIR
        self.jobs = root / contract.JOBS_DIR
        self.trash = root / contract.TRASH_DIR
        self._max_result_bytes = max_result_bytes
        self._wall = wall

    def prepare(self) -> None:
        """Refuse an unsafe runtime root, then create the dispatcher's directories."""
        try:
            info = os.lstat(self.root)
        except FileNotFoundError:
            raise SpoolLayoutError("the runtime root does not exist (see docs/GPU_HOST_RUNBOOK.md)") from None
        if not stat.S_ISDIR(info.st_mode):
            raise SpoolLayoutError("the runtime root is not a real directory")
        if info.st_mode & 0o007:
            raise SpoolLayoutError("the runtime root is open to other users")
        if not info.st_mode & stat.S_ISGID:
            raise SpoolLayoutError("the runtime root is not setgid; the executor could not read job files")
        for directory in (self.staging, self.jobs, self.trash):
            try:
                directory.mkdir(mode=0o770)
            except FileExistsError:
                pass
            if not stat.S_ISDIR(os.lstat(directory).st_mode):
                raise SpoolLayoutError(f"{directory.name}/ is not a real directory")

    def job_directory(self, job_id: str) -> Path:
        return self.jobs / job_id

    def new_staging(self, job_id: str) -> Path:
        path = self.staging / f"{job_id}-{secrets.token_hex(4)}"
        path.mkdir(mode=0o770)
        return path

    def remove_staging(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    def publish(self, staging: Path, job, size: int) -> Path:
        """Make a fully written job visible to the executor with one rename."""
        document = contract.SpoolJob(
            schemaVersion=contract.SCHEMA_VERSION, kind="mergen-spool-job", jobId=job.job_id,
            module=job.module, disease=job.disease,
            input=contract.InputRef(path=contract.INPUT_FILE, sha256=job.input_sha256, size=size),
            maxResultBytes=self._max_result_bytes, publishedAt=int(self._wall()))
        # input.zip was fsynced while it was written; this fsyncs job.json and staging/.
        write_json_atomic(staging / contract.JOB_FILE, document.model_dump())
        target = self.job_directory(job.job_id)
        if os.path.lexists(target):
            raise SpoolViolation("a directory for this job is already published")
        os.rename(staging, target)
        fsync_directory(self.jobs)
        fsync_directory(self.staging)
        return target

    def read_ready(self) -> contract.ExecutorReady | None:
        try:
            return contract.ExecutorReady.model_validate(read_json(self.root / contract.READY_FILE))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise SpoolViolation("executor.json is not a valid v1 readiness document") from None

    def read_status(self, directory: Path, job_id: str) -> contract.SpoolStatus | None:
        path = directory / contract.STATUS_FILE
        if not os.path.lexists(path):
            return None
        try:
            status = contract.SpoolStatus.model_validate(read_json(path))
        except (OSError, ValueError):
            raise SpoolViolation("status.json is not a valid v1 status") from None
        if status.jobId != job_id:
            raise SpoolViolation("status.json names another job")
        return status

    def lock_job(self, directory: Path) -> int | None:
        """The job directory's lock, once the executor has let go of it."""
        return lock_directory(directory, blocking=False)

    @contextmanager
    def open_result(self, directory: Path, ref: contract.ResultRef) -> Iterator[BinaryIO]:
        """Open the result the status names once, and keep that descriptor.

        Size and digest are checked on it, and the archive check and the upload
        read the same descriptor: replacing result.zip by path afterwards changes
        nothing the dispatcher sends, and an in-place change fails the digest
        that the upload computes again.
        """
        try:
            fd = os.open(directory / contract.RESULT_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            raise SpoolViolation("result.zip is missing or not a regular file") from None
        # Unbuffered: every read reaches the file, so a buffer can never stand in
        # for changed bytes, and the upload digest sees any in-place change.
        with os.fdopen(fd, "rb", buffering=0) as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size != ref.size
                    or info.st_size > self._max_result_bytes):
                raise SpoolViolation("result.zip does not match its status")
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(CHUNK), b""):
                digest.update(block)
            if digest.hexdigest() != ref.sha256:
                raise SpoolViolation("result.zip checksum does not match its status")
            handle.seek(0)
            yield handle

    def cancel(self, directory: Path) -> None:
        """Tell the executor the lease is gone. Idempotent."""
        try:
            create_marker(directory / contract.CANCEL_FILE)
        except OSError as exc:
            LOG.info("cancel marker not written (%s)", type(exc).__name__)

    def discard(self, directory: Path) -> None:
        """Take a job out of the executor's view, then delete it once unlocked."""
        target = self.trash / f"{directory.name}-{secrets.token_hex(4)}"
        try:
            os.rename(directory, target)
        except FileNotFoundError:
            return
        fsync_directory(self.jobs)
        self._remove(target)

    def sweep_trash(self) -> None:
        for entry in self._entries(self.trash):
            self._remove(entry)

    def recover(self) -> list[contract.SpoolJob]:
        """Start-up: drop half-built deliveries, sweep the trash and return the
        published jobs whose lease must be checked before any new claim."""
        for entry in self._entries(self.staging):
            # Staging was never visible to the executor: nothing there is worth keeping.
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        self.sweep_trash()
        published = []
        for entry in self._entries(self.jobs):
            job = self._published_job(entry)
            if job is None:
                LOG.warning("spool: discarding an unrecognised entry in jobs/")
                self.discard(entry)
            else:
                published.append(job)
        return published

    def _published_job(self, entry: Path) -> contract.SpoolJob | None:
        if entry.is_symlink() or not entry.is_dir() or not JOB_NAME.fullmatch(entry.name):
            return None
        try:
            job = contract.SpoolJob.model_validate(read_json(entry / contract.JOB_FILE))
        except (OSError, ValueError):
            return None
        return job if job.jobId == entry.name else None

    def _remove(self, path: Path) -> None:
        try:
            if path.is_symlink() or not path.is_dir():
                path.unlink(missing_ok=True)
            elif not remove_unlocked(path):
                LOG.info("spool: the executor still holds a discarded job; removal deferred")
        except OSError as exc:
            LOG.warning("spool: an entry could not be removed yet (%s)", type(exc).__name__)

    @staticmethod
    def _entries(directory: Path) -> list[Path]:
        try:
            return sorted(directory.iterdir())
        except FileNotFoundError:
            return []
