"""The dispatcher loop: claim, deliver, supervise, publish; one job at a time."""
from __future__ import annotations

import errno
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import httpx

from backend.archive_io import InvalidArchive, validate_input_archive, validate_result_archive
from mergen_dispatcher.config import DispatcherConfig
from mergen_dispatcher.control import (ClaimedJob, ControlClient, ControlUnavailable, InputRejected,
                                       LeaseLost, ProtocolError, ResultChanged, ResultRejected)
from mergen_dispatcher.lease import Backoff, LeaseKeeper
from mergen_dispatcher.spool import Spool, SpoolViolation
from mergen_spool import contract

LOG = logging.getLogger("mergen.dispatcher")

# Outcomes of one job.
PUBLISHED = "published"     # the VPS accepted the result
FAILED = "failed"           # a failure code was reported to the VPS
LEASE_LOST = "lease-lost"   # nothing published and nothing reported
ABANDONED = "abandoned"     # could not finish; the VPS lease lapses and requeues
STOPPED = "stopped"         # shutdown; a delivered job stays for recovery


class _Stopped(Exception):
    pass


class _Undeliverable(Exception):
    pass


class Dispatcher:
    def __init__(self, config: DispatcherConfig, *, transport: httpx.BaseTransport | None = None,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 jitter: Callable[[], float] | None = None):
        self.config = config
        self.spool = Spool(config.runtime_root, config.max_result_bytes, wall)
        self.client = ControlClient(config, transport)
        self._transport, self._clock, self._wall = transport, clock, wall
        self._jitter = jitter
        self.backoff = self._new_backoff()
        self._stop = threading.Event()
        self._last_heartbeat: float | None = None
        self._ready_problem = False
        self._published: set[str] = set()

    def _new_backoff(self) -> Backoff:
        extra = {} if self._jitter is None else {"jitter": self._jitter}
        return Backoff(self.config.backoff_initial_seconds, self.config.backoff_max_seconds, **extra)

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self.client.close()

    def _sleep(self, seconds: float) -> bool:
        """Interruptible wait; True when the dispatcher is stopping."""
        return self._stop.wait(seconds)

    # -- main loop -------------------------------------------------------
    def run(self) -> None:
        self.spool.prepare()
        pending = self.spool.recover()
        LOG.info("dispatcher started; %d published job(s) to re-check", len(pending))
        while not self._stop.is_set():
            try:
                if pending:
                    # Nothing new is claimed while a delivered job is unresolved.
                    self.resume(pending[0])
                    pending.pop(0)
                    self.backoff.reset()
                    continue
                self.run_once()
                self.backoff.reset()
                delay = self.config.poll_seconds
            except ControlUnavailable as exc:
                delay = self.backoff.next()
                LOG.warning("control API unavailable (%s); next attempt in %.1fs", exc, delay)
            except ProtocolError as exc:
                delay = self.backoff.next()
                LOG.error("control API answered outside the contract (%s)", exc)
            except Exception:
                LOG.exception("unexpected dispatcher error")
                raise
            self._sleep(delay)

    def run_once(self) -> str:
        """One idle cycle: advertise what the executor can run, claim, process."""
        self.spool.sweep_trash()
        ready = self._executor_ready()
        if ready is None or not ready.capabilities:
            return "idle"  # nothing is advertised without a ready executor
        self._heartbeat(ready.capabilities)
        if not ready.acceptingJobs:
            return "busy"
        job = self.client.claim(list(ready.capabilities), self._clock)
        if job is None:
            return "idle"
        LOG.info("job %s: claimed (%s)", job.tag, job.module)
        return self._run_job(job, None)

    def resume(self, document: contract.SpoolJob) -> str:
        """Re-take a job published before a restart if the VPS still says it is ours."""
        directory = self.spool.job_directory(document.jobId)
        started = self._clock()
        try:
            seconds = self.client.renew(document.jobId)
        except (LeaseLost, ProtocolError):
            LOG.info("job %s: no longer ours after the restart; discarding", document.jobId[:8])
            self.spool.cancel(directory)
            self.spool.discard(directory)
            return LEASE_LOST
        job = ClaimedJob(document.jobId, document.module, document.disease,
                         document.input.sha256, seconds, started)
        LOG.info("job %s: resumed after a restart", job.tag)
        return self._run_job(job, directory)

    # -- one job -----------------------------------------------------------
    def _run_job(self, job: ClaimedJob, directory: Path | None) -> str:
        lease_client = ControlClient(self.config, self._transport)
        keeper = LeaseKeeper(lease_client.renew, job.job_id, job.lease_seconds, started=job.claimed_at,
                             renew_every=self.config.lease_renew_seconds,
                             backoff=self._new_backoff(), clock=self._clock).start()
        outcome = ABANDONED
        try:
            if directory is None:
                directory = self._deliver(job, keeper)
            outcome = self._supervise(job, directory, keeper)
        except InputRejected as exc:
            LOG.warning("job %s: input rejected (%s)", job.tag, exc)
            outcome = self._report(job, keeper, "input-invalid")
        except LeaseLost:
            outcome = LEASE_LOST
        except (_Undeliverable, ProtocolError) as exc:
            LOG.warning("job %s: input could not be delivered (%s)", job.tag, exc)
            outcome = self._report(job, keeper, "internal-error")
        except SpoolViolation as exc:
            LOG.error("job %s: spool contract violated (%s)", job.tag, exc)
            outcome = self._report(job, keeper, "internal-error")
        except OSError as exc:
            LOG.error("job %s: local storage failed (%s)", job.tag, type(exc).__name__)
            code = "resource-exhausted" if exc.errno == errno.ENOSPC else "internal-error"
            outcome = self._report(job, keeper, code)
        except _Stopped:
            outcome = STOPPED
        finally:
            keeper.stop()
            lease_client.close()
        if directory is not None and outcome != STOPPED:
            if outcome != PUBLISHED:
                self.spool.cancel(directory)
            self.spool.discard(directory)
        LOG.info("job %s: %s", job.tag, outcome)
        return outcome

    def _deliver(self, job: ClaimedJob, keeper: LeaseKeeper) -> Path:
        """Download, verify and validate in staging; publish with one rename."""
        backoff = self._new_backoff()
        for attempt in range(1, self.config.transfer_attempts + 1):
            staging = self.spool.new_staging(job.job_id)
            try:
                size = self.client.download(job, staging / contract.INPUT_FILE,
                                            self.config.max_input_bytes, keeper.valid)
                try:
                    manifest = validate_input_archive(staging / contract.INPUT_FILE,
                                                      self.config.max_expanded_bytes)
                except InvalidArchive:
                    raise InputRejected("the archive fails the live input contract") from None
                if (manifest.module, manifest.disease) != (job.module, job.disease):
                    raise InputRejected("the input manifest does not match the claimed job")
                if not keeper.valid():
                    raise LeaseLost("the lease ended before delivery")
                directory = self.spool.publish(staging, job, size)
                LOG.info("job %s: delivered to the executor", job.tag)
                return directory
            except ControlUnavailable as exc:
                self.spool.remove_staging(staging)
                if attempt == self.config.transfer_attempts or not keeper.valid():
                    raise _Undeliverable(f"{exc} after {attempt} attempt(s)") from None
                delay = backoff.next()
                LOG.info("job %s: %s; retry %d in %.1fs", job.tag, exc, attempt, delay)
                if self._sleep(delay):
                    raise _Stopped from None
            except BaseException:
                self.spool.remove_staging(staging)
                raise
        raise _Undeliverable("no transfer attempt is configured")

    def _supervise(self, job: ClaimedJob, directory: Path, keeper: LeaseKeeper) -> str:
        """Wait for the executor's verdict while the lease keeper runs."""
        previous = None
        while True:
            if not keeper.valid():
                LOG.warning("job %s: lease lost while the executor worked", job.tag)
                return LEASE_LOST
            status = self.spool.read_status(directory, job.job_id)
            if status is not None:
                if not contract.advances(previous, status.state):
                    raise SpoolViolation(f"status moved from {previous} to {status.state}")
                previous = status.state
                if status.state == "completed":
                    return self._publish(job, directory, status, keeper)
                if status.state == "failed":
                    LOG.warning("job %s: the executor reported %s", job.tag, status.errorCode)
                    return self._report(job, keeper, status.errorCode)
            self._keep_advertising()
            if self._sleep(self.config.spool_poll_seconds):
                return STOPPED

    def _publish(self, job: ClaimedJob, directory: Path, status: contract.SpoolStatus,
                 keeper: LeaseKeeper) -> str:
        if job.job_id in self._published:
            return PUBLISHED  # never upload one job twice
        # Nothing in the job directory may change between verification and the
        # end of the upload: hold its lock once the executor has released it.
        lock = self.spool.lock_job(directory)
        while lock is None:
            if not keeper.valid():
                return LEASE_LOST
            if self._sleep(self.config.spool_poll_seconds):
                raise _Stopped
            lock = self.spool.lock_job(directory)
        try:
            with self.spool.open_result(directory, status.result) as result:
                validate_result_archive(result, self.config.max_expanded_bytes,
                                        {"id": job.job_id, "module": job.module, "disease": job.disease})
                return self._upload(job, result, status.result, keeper)
        except (SpoolViolation, InvalidArchive) as exc:
            LOG.error("job %s: executor result rejected (%s)", job.tag, exc)
            return self._report(job, keeper, "inference-failed")
        finally:
            os.close(lock)

    def _upload(self, job: ClaimedJob, result: BinaryIO, ref: contract.ResultRef,
                keeper: LeaseKeeper) -> str:
        """Upload from the verified descriptor; retry only what cannot have completed."""
        backoff = self._new_backoff()
        for attempt in range(1, self.config.transfer_attempts + 1):
            # Never publish on a lease this worker cannot prove it still holds.
            if not keeper.valid():
                return LEASE_LOST
            try:
                self.client.upload(job.job_id, result, ref.size, ref.sha256, keeper.valid)
            except LeaseLost:
                # Also the answer to a retry after a lost response: the first
                # upload may have completed the job. Never report a failure here.
                LOG.warning("job %s: the VPS refused the result for this lease", job.tag)
                return LEASE_LOST
            except ResultChanged as exc:
                # The final chunk was withheld, so the VPS cannot have completed it.
                LOG.error("job %s: %s; nothing complete was sent", job.tag, exc)
                return self._report(job, keeper, "internal-error")
            except ResultRejected as exc:
                return self._report(job, keeper, exc.error_code)
            except ProtocolError as exc:
                LOG.error("job %s: upload answer outside the contract (%s)", job.tag, exc)
                return ABANDONED
            except ControlUnavailable as exc:
                delay = backoff.next()
                LOG.info("job %s: %s; retry %d in %.1fs", job.tag, exc, attempt, delay)
                if self._sleep(delay):
                    raise _Stopped from None
                continue
            self._published.add(job.job_id)
            LOG.info("job %s: result published", job.tag)
            return PUBLISHED
        return ABANDONED

    def _report(self, job: ClaimedJob, keeper: LeaseKeeper, error_code: str) -> str:
        """Tell the VPS the job failed, only while this worker still owns it."""
        backoff = self._new_backoff()
        for _ in range(3):
            if not keeper.valid():
                return LEASE_LOST
            try:
                self.client.fail(job.job_id, error_code)
                return FAILED
            except LeaseLost:
                return LEASE_LOST
            except (ControlUnavailable, ProtocolError):
                if self._sleep(backoff.next()):
                    break
        return ABANDONED

    # -- executor readiness and heartbeat ----------------------------------
    def _executor_ready(self) -> contract.ExecutorReady | None:
        try:
            ready = self.spool.read_ready()
        except SpoolViolation as exc:
            if not self._ready_problem:
                LOG.warning("executor readiness ignored: %s", exc)
            self._ready_problem = True
            return None
        self._ready_problem = False
        if ready is None or abs(self._wall() - ready.updatedAt) > self.config.executor_stale_seconds:
            return None
        return ready

    def _heartbeat(self, capabilities: list[str]) -> None:
        now = self._clock()
        if self._last_heartbeat is not None and now - self._last_heartbeat < self.config.heartbeat_seconds:
            return
        self.client.heartbeat(list(capabilities))
        self._last_heartbeat = now

    def _keep_advertising(self) -> None:
        ready = self._executor_ready()
        if ready is None or not ready.capabilities:
            return
        try:
            self._heartbeat(ready.capabilities)
        except (ControlUnavailable, ProtocolError):
            pass  # the lease keeper decides what an outage means for this job
