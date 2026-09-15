"""One job directory, held under its lock and reached only through its descriptor.

The dispatcher may rename a job directory into trash/ at any time, so every
file operation here is relative to the descriptor that holds the lock, and no
path component is ever followed through a link. job.json, input.zip, cancel and
gate belong to the dispatcher and are only read, the gate also locked (see
mergen_executor.finalize); status.json, result.zip and work/ belong to the
executor.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import stat
import time
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from backend.archive_io import InvalidArchive, validate_result_archive
from backend.live_contracts import InputManifest
from mergen_spool import contract
from mergen_spool.fs import exists_at, lock_directory, read_json_at, write_json_atomic_at

CHUNK = 1024 * 1024
JOB_NAME = re.compile(r"^[a-f0-9]{32}$")
RESULT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.zip$")
# Names this side may leave behind after a crash; nothing else is ever removed.
TEMPORARY = re.compile(r"^\.(status\.json|result\.zip)\.[0-9a-f]{8}\.tmp$")
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class JobRejected(Exception):
    """The job cannot run; `error_code` is what the dispatcher will report."""

    def __init__(self, error_code: str, reason: str):
        super().__init__(reason)
        self.error_code = error_code


class Cancelled(Exception):
    """The dispatcher cancelled the job; nothing may be published."""


class StatusProblem(Exception):
    """status.json is unreadable, already terminal, or would move backwards."""


class LockedJob:
    def __init__(self, fd: int, job_id: str, path: Path, wall: Callable[[], float]):
        self.fd, self.job_id, self.path, self._wall = fd, job_id, path, wall
        self.tag = job_id[:8]  # enough to correlate logs, not the full identifier

    @classmethod
    def acquire(cls, jobs: Path, job_id: str,
                wall: Callable[[], float] = time.time) -> "LockedJob | None":
        """Lock jobs/<job_id>; None when it is busy, gone or not a real directory."""
        if not JOB_NAME.fullmatch(job_id):
            return None
        try:
            fd = lock_directory(jobs / job_id, blocking=False)
        except OSError:
            return None
        return None if fd is None else cls(fd, job_id, jobs / job_id, wall)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def cancelled(self) -> bool:
        return exists_at(self.fd, contract.CANCEL_FILE)

    # -- control documents -------------------------------------------------
    def read_job(self) -> contract.SpoolJob:
        try:
            job = contract.SpoolJob.model_validate(read_json_at(self.fd, contract.JOB_FILE))
        except (OSError, ValueError):
            raise JobRejected("internal-error", "job.json is not a valid v1 job") from None
        if job.jobId != self.job_id:
            raise JobRejected("internal-error", "job.json names another job")
        if job.disease != "glioma":
            raise JobRejected("input-invalid", "the disease profile is not supported")
        return job

    def read_status(self) -> contract.SpoolStatus | None:
        if not exists_at(self.fd, contract.STATUS_FILE):
            return None
        try:
            status = contract.SpoolStatus.model_validate(read_json_at(self.fd, contract.STATUS_FILE))
        except (OSError, ValueError):
            raise StatusProblem("status.json is not a valid v1 status") from None
        if status.jobId != self.job_id:
            raise StatusProblem("status.json names another job")
        return status

    def advance(self, state: str, *, result: contract.ResultRef | None = None,
                error_code: str | None = None) -> None:
        """Write the next status. A terminal status is never rewritten and a
        status never moves backwards or repeats."""
        current = self.read_status()
        if current is not None:
            if current.state in contract.TERMINAL_STATES:
                raise StatusProblem(f"status is already {current.state}")
            if current.state == state or not contract.advances(current.state, state):
                raise StatusProblem(f"status cannot move from {current.state} to {state}")
        document = contract.SpoolStatus(
            schemaVersion=contract.SCHEMA_VERSION, kind="mergen-spool-status", jobId=self.job_id,
            state=state, updatedAt=int(self._wall()), result=result, errorCode=error_code)
        write_json_atomic_at(self.fd, contract.STATUS_FILE, document.model_dump(exclude_none=True))

    # -- input -------------------------------------------------------------
    def open_input(self, job: contract.SpoolJob, max_input_bytes: int) -> BinaryIO:
        """input.zip checked against job.json on one unbuffered descriptor; the
        caller validates and extracts from that same descriptor."""
        if job.input.size > max_input_bytes:
            raise JobRejected("input-invalid", "the input exceeds this executor's size limit")
        try:
            fd = os.open(contract.INPUT_FILE, READ, dir_fd=self.fd)
        except OSError:
            raise JobRejected("internal-error", "input.zip is missing or not a regular file") from None
        handle = os.fdopen(fd, "rb", buffering=0)
        try:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != job.input.size:
                raise JobRejected("internal-error", "input.zip does not match job.json")
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(CHUNK), b""):
                digest.update(block)
            if digest.hexdigest() != job.input.sha256:
                raise JobRejected("internal-error", "input.zip checksum does not match job.json")
            handle.seek(0)
            return handle
        except BaseException:
            handle.close()
            raise

    # -- work area -----------------------------------------------------------
    def prepare_work(self, archive: BinaryIO, manifest: InputManifest) -> tuple[Path, Path, dict]:
        """Extract the declared volumes into work/input and create an empty
        work/output. Every entry is created through a descriptor with
        O_EXCL|O_NOFOLLOW, so nothing can be redirected by a link."""
        self.remove_work()
        work = _make_directory(self.fd, contract.WORK_DIR)
        try:
            os.close(_make_directory(work, "output"))
            inputs = _make_directory(work, "input")
            try:
                volumes = {}
                with zipfile.ZipFile(archive) as bundle:
                    for item in manifest.files:
                        _extract(bundle, bundle.getinfo(item.path), inputs)
                        volumes[item.modality] = self.path / contract.WORK_DIR / "input" / item.path
            finally:
                os.close(inputs)
        finally:
            os.close(work)
        base = self.path / contract.WORK_DIR
        return base / "input", base / "output", volumes

    def remove_work(self) -> None:
        """Remove work/ entirely; it is the executor's alone."""
        try:
            info = os.lstat(contract.WORK_DIR, dir_fd=self.fd)
        except FileNotFoundError:
            return
        if stat.S_ISDIR(info.st_mode):
            shutil.rmtree(contract.WORK_DIR, dir_fd=self.fd)
        else:
            os.unlink(contract.WORK_DIR, dir_fd=self.fd)

    def remove_leftovers(self, *, keep_result: bool) -> None:
        """What a crashed run may leave: temporaries, work/ and, unless the job
        completed, a result.zip that was never announced."""
        for name in os.listdir(self.fd):
            if TEMPORARY.fullmatch(name):
                os.unlink(name, dir_fd=self.fd)
        self.remove_work()
        if not keep_result and exists_at(self.fd, contract.RESULT_FILE):
            os.unlink(contract.RESULT_FILE, dir_fd=self.fd)

    # -- result --------------------------------------------------------------
    def publish_result(self, name: str, job: contract.SpoolJob, *, max_result_bytes: int,
                       max_expanded_bytes: int) -> contract.ResultRef:
        """Copy the adapter's ZIP to a temporary name, fsync it, validate what
        was written and rename it to result.zip. `completed` is written only
        after this returns, and only by finalize() under the gate."""
        if not isinstance(name, str) or not RESULT_NAME.fullmatch(name):
            raise JobRejected("inference-failed", "the adapter returned an unusable result name")
        limit = min(job.maxResultBytes, max_result_bytes)
        source = self._open_output(name)
        temporary = f".result.zip.{secrets.token_hex(4)}.tmp"
        try:
            with os.fdopen(source, "rb", buffering=0) as reader:
                info = os.fstat(reader.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise JobRejected("inference-failed", "the adapter's result is not a regular file")
                if info.st_size > limit:
                    raise JobRejected("resource-exhausted", "the result exceeds its size limit")
                digest, size = self._copy(reader, temporary, limit)
            check = os.open(temporary, READ, dir_fd=self.fd)
            with os.fdopen(check, "rb", buffering=0) as written:
                try:
                    validate_result_archive(written, max_expanded_bytes,
                                            {"id": job.jobId, "module": job.module, "disease": job.disease})
                except InvalidArchive:
                    raise JobRejected("inference-failed", "the result fails the result contract") from None
            if self.cancelled():
                raise Cancelled
            if exists_at(self.fd, contract.RESULT_FILE):
                raise JobRejected("internal-error", "a result.zip already exists")
            os.rename(temporary, contract.RESULT_FILE, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass
            raise
        return contract.ResultRef(path=contract.RESULT_FILE, sha256=digest, size=size)

    def _open_output(self, name: str) -> int:
        try:
            work = os.open(contract.WORK_DIR, DIRECTORY, dir_fd=self.fd)
            try:
                output = os.open("output", DIRECTORY, dir_fd=work)
            finally:
                os.close(work)
            try:
                return os.open(name, READ, dir_fd=output)
            finally:
                os.close(output)
        except OSError:
            raise JobRejected("inference-failed", "the adapter left no readable result") from None

    def _copy(self, reader: BinaryIO, temporary: str, limit: int) -> tuple[str, int]:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660,
                     dir_fd=self.fd)
        digest, size = hashlib.sha256(), 0
        with os.fdopen(fd, "wb") as writer:
            for block in iter(lambda: reader.read(CHUNK), b""):
                size += len(block)
                if size > limit:
                    raise JobRejected("resource-exhausted", "the result exceeds its size limit")
                digest.update(block)
                writer.write(block)
            writer.flush()
            os.fsync(writer.fileno())
        return digest.hexdigest(), size


def _make_directory(parent: int, name: str) -> int:
    """Create `name` under `parent`, open it without following a link and give
    it the job-directory mode, so the dispatcher can remove it later."""
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
    except FileExistsError:
        pass
    fd = os.open(name, DIRECTORY, dir_fd=parent)
    try:
        os.fchmod(fd, contract.JOB_DIRECTORY_MODE)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _extract(bundle: zipfile.ZipFile, info: zipfile.ZipInfo, root: int) -> None:
    parts = PurePosixPath(info.filename).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise JobRejected("input-invalid", "an input member has an unsafe path")
    current = os.dup(root)
    try:
        for part in parts[:-1]:
            child = _make_directory(current, part)
            os.close(current)
            current = child
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660,
                     dir_fd=current)
        written = 0
        with os.fdopen(fd, "wb") as output, bundle.open(info) as source:
            for block in iter(lambda: source.read(CHUNK), b""):
                written += len(block)
                if written > info.file_size:
                    raise JobRejected("input-invalid", "an input member is larger than declared")
                output.write(block)
    finally:
        os.close(current)
