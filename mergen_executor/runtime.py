"""The executor loop: advertise readiness, take one job, run it, publish it."""
from __future__ import annotations

import errno
import fcntl
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import MappingProxyType

from backend.archive_io import InvalidArchive, validate_input_archive
from mergen_executor.adapter import AdapterFailure, ImagingAdapter, ImagingJob, ModelIdentity, model_identity
from mergen_executor.config import ExecutorConfig
from mergen_executor.finalize import check_gate, finalize
from mergen_executor.gpu import GpuProbe, UncheckedGpu
from mergen_executor.jobdir import JOB_NAME, Cancelled, JobRejected, LockedJob, StatusProblem
from mergen_executor.layout import verify_jobs_directory, verify_spool, verify_state
from mergen_spool import contract
from mergen_spool.fs import write_json_atomic

LOG = logging.getLogger("mergen.executor")
CAPABILITY = "imaging"
READY_TEMPORARY = re.compile(r"^\.executor\.json\.[0-9a-f]{8}\.tmp$")

# Outcomes of one tick.
COMPLETED, FAILED, CANCELLED, IDLE = "completed", "failed", "cancelled", "idle"
NO_ADAPTER, PAUSED, GPU_BUSY, GPU_LOCKED = "no-adapter", "paused", "gpu-busy", "gpu-locked"


class Executor:
    def __init__(self, config: ExecutorConfig, adapter: ImagingAdapter | None, *,
                 gpu: GpuProbe | None = None, wall: Callable[[], float] = time.time,
                 clock: Callable[[], float] = time.monotonic):
        self.config, self.adapter, self.gpu = config, adapter, gpu or UncheckedGpu()
        self._wall, self._clock = wall, clock
        self.jobs = config.runtime_root / contract.JOBS_DIR
        self.capabilities: list[str] = []
        # The model checked at start; every result this executor publishes names it.
        self.model: ModelIdentity | None = None
        self._stop = threading.Event()
        self._ready_lock = threading.Lock()
        self._last_ready: tuple | None = None
        self._last_ready_at = float("-inf")
        self._last_admission: str | None = None
        self._last_preflight_at = float("-inf")
        # Terminal, cancelled or unreadable jobs: never opened again.
        self._settled: set[str] = set()

    def stop(self) -> None:
        self._stop.set()

    # -- life cycle ------------------------------------------------------------
    def start(self) -> None:
        """Verify the layout, check the adapter, replace any stale readiness
        with `acceptingJobs: false` and fail runs a previous process left open."""
        verify_state(self.config.state_root)
        verify_spool(self.config.runtime_root, self.config.spool_owner_uid)
        self.capabilities = self._preflight()
        self._last_preflight_at = self._clock()
        for entry in os.scandir(self.config.runtime_root):
            if (READY_TEMPORARY.fullmatch(entry.name)
                    and entry.stat(follow_symlinks=False).st_uid == os.geteuid()):
                os.unlink(entry.path)
        self.publish_ready(accepting=False, force=True)
        self.recover()

    def loop(self) -> None:
        try:
            while not self._stop.is_set():
                outcome = self.tick()
                wait = self.config.gpu_wait_seconds if outcome == GPU_BUSY else self.config.poll_seconds
                self._stop.wait(wait)
        finally:
            try:
                self.publish_ready(accepting=False, force=True)
            except OSError:
                pass

    def tick(self) -> str:
        """One cycle: decide admission, advertise it, and run at most one job."""
        reason = self._admission()
        if reason is not None:
            self.publish_ready(accepting=False)
            return reason
        with self._gpu_lock() as held:
            if not held:
                self.publish_ready(accepting=False)
                return GPU_LOCKED
            self.publish_ready(accepting=True)
            job = self._next_job()
            if job is None:
                return IDLE
            self.publish_ready(accepting=False, force=True)
            try:
                return self._process(job)
            finally:
                self._settled.add(job.job_id)
                job.close()

    # -- readiness and admission -----------------------------------------------
    def publish_ready(self, *, accepting: bool, force: bool = False) -> None:
        accepting = accepting and bool(self.capabilities)
        state = (tuple(self.capabilities), accepting)
        with self._ready_lock:
            now = self._clock()
            if (not force and state == self._last_ready
                    and now - self._last_ready_at < self.config.ready_refresh_seconds):
                return
            document = contract.ExecutorReady(
                schemaVersion=contract.SCHEMA_VERSION, kind="mergen-executor-ready",
                capabilities=list(self.capabilities), acceptingJobs=accepting,
                updatedAt=int(self._wall()))
            write_json_atomic(self.config.runtime_root / contract.READY_FILE, document.model_dump())
            self._last_ready, self._last_ready_at = state, now

    def _preflight(self) -> list[str]:
        self.model = None
        if self.adapter is None:
            LOG.warning("no imaging adapter in this release; nothing is advertised")
            return []
        identity = model_identity(self.adapter)
        if identity is None:
            LOG.warning("the imaging adapter declares no valid model identity; nothing is advertised")
            return []
        try:
            self.adapter.preflight()
        except AdapterFailure as exc:
            LOG.warning("imaging adapter preflight failed (%s); nothing is advertised", exc.error_code)
            return []
        except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
            LOG.warning("imaging adapter preflight raised %s; nothing is advertised", type(exc).__name__)
            return []
        self.model = identity
        return [CAPABILITY]

    def _admission(self) -> str | None:
        # Pause and the GPU come first so a preflight retry, which opens the
        # GPU itself, never competes with the work this host is waiting on.
        if os.path.lexists(self.config.pause_file):
            reason = PAUSED
        elif not self.gpu.check().available:
            reason = GPU_BUSY
        elif not self._model_ready():
            reason = NO_ADAPTER
        else:
            reason = None
        if reason != self._last_admission:
            LOG.info("admission: %s", reason or "open")
            self._last_admission = reason
        return reason

    def _model_ready(self) -> bool:
        """Whether a model is advertised, retrying preflight on a slow cadence.

        A model that failed at start is not written off: preflight touches the
        GPU, so it can fail for a condition that passes. Retries are rate
        limited because each one loads the checkpoint.
        """
        if self.capabilities:
            return True
        now = self._clock()
        if now - self._last_preflight_at < self.config.preflight_retry_seconds:
            return False
        self._last_preflight_at = now
        self.capabilities = self._preflight()
        return bool(self.capabilities)

    @contextmanager
    def _gpu_lock(self) -> Iterator[bool]:
        """The single-inference rule across processes: only the holder of
        MERGEN_GPU_LOCK_PATH starts a job. Nobody else's GPU work is touched."""
        fd = os.open(self.config.gpu_lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True
        finally:
            os.close(fd)

    @contextmanager
    def _keep_ready(self) -> Iterator[None]:
        """Keep executor.json fresh (not accepting) while an adapter runs, so the
        dispatcher does not mistake a long job for a dead executor."""
        done = threading.Event()

        def beat():
            while not done.wait(self.config.ready_refresh_seconds):
                try:
                    self.publish_ready(accepting=False, force=True)
                except OSError as exc:
                    LOG.warning("readiness not refreshed (%s)", type(exc).__name__)

        thread = threading.Thread(target=beat, name="readiness", daemon=True)
        thread.start()
        try:
            yield
        finally:
            done.set()
            thread.join()

    # -- jobs --------------------------------------------------------------------
    def _next_job(self) -> LockedJob | None:
        if not verify_jobs_directory(self.config.runtime_root, self.config.spool_owner_uid):
            return None
        names = sorted(entry.name for entry in os.scandir(self.jobs) if JOB_NAME.fullmatch(entry.name))
        self._settled &= set(names)
        for name in names:
            if name in self._settled:
                continue
            job = LockedJob.acquire(self.jobs, name, self._wall)
            if job is None:
                continue  # locked by the dispatcher, gone, or not a real directory
            if self._runnable(job):
                return job
            self._settled.add(name)
            job.close()
        return None

    def _runnable(self, job: LockedJob) -> bool:
        try:
            status = job.read_status()
        except StatusProblem:
            LOG.warning("job %s: status.json is unreadable; left alone", job.tag)
            return False
        if status is not None:
            if status.state not in contract.TERMINAL_STATES:
                # Accepted or running while nobody holds the lock: a run died.
                self._fail_interrupted(job)
            return False
        if job.cancelled():
            LOG.info("job %s: cancelled before it started", job.tag)
            return False
        return True

    def _process(self, job: LockedJob) -> str:
        try:
            document = job.read_job()
            check_gate(job)
            job.advance("accepted")
            LOG.info("job %s: accepted", job.tag)
            with job.open_input(document, self.config.max_input_bytes) as archive:
                try:
                    manifest = validate_input_archive(archive, self.config.max_expanded_bytes)
                except InvalidArchive:
                    raise JobRejected("input-invalid", "the input fails the live input contract") from None
                if (manifest.module, manifest.disease) != (document.module, document.disease):
                    raise JobRejected("input-invalid", "the input manifest does not match job.json")
                input_dir, output_dir, volumes = job.prepare_work(archive, manifest)
            if job.cancelled():
                raise Cancelled
            job.advance("running")
            LOG.info("job %s: running", job.tag)
            imaging = ImagingJob(
                job_id=job.job_id, disease=document.disease, volumes=MappingProxyType(volumes),
                input_dir=input_dir, output_dir=output_dir,
                max_result_bytes=min(document.maxResultBytes, self.config.max_result_bytes),
                cancelled=lambda: self._stop.is_set() or job.cancelled())
            with self._keep_ready():
                name = self._run_adapter(imaging)
            if job.cancelled():
                raise Cancelled
            result = job.publish_result(name, document, model=self.model,
                                        max_result_bytes=self.config.max_result_bytes,
                                        max_expanded_bytes=self.config.max_expanded_bytes)
            job.remove_work()
            # The only way to `completed`: under the gate, after a last look for cancel.
            state, code = finalize(job, "completed", result=result)
            if state != "completed":
                LOG.warning("job %s: result withdrawn before the verdict (%s)", job.tag, code)
                return CANCELLED if code == "cancelled" else FAILED
            LOG.info("job %s: completed", job.tag)
            return COMPLETED
        except Cancelled:
            return self._finish(job, "cancelled", CANCELLED)
        except JobRejected as exc:
            return self._finish(job, exc.error_code, FAILED)
        except StatusProblem:
            LOG.error("job %s: status would not advance; the job is left as it is", job.tag)
            return FAILED
        except OSError as exc:
            LOG.error("job %s: local storage failed (%s)", job.tag, type(exc).__name__)
            code = "resource-exhausted" if exc.errno == errno.ENOSPC else "internal-error"
            return self._finish(job, code, FAILED)

    def _run_adapter(self, job: ImagingJob) -> str:
        try:
            name = self.adapter.run(job)
        except AdapterFailure as exc:
            raise JobRejected(exc.error_code, "the adapter reported a failure") from None
        except MemoryError:
            raise JobRejected("resource-exhausted", "the adapter ran out of memory") from None
        except Exception as exc:  # noqa: BLE001 - any adapter failure is a job failure
            # The type only: an adapter's message may quote file names or content.
            LOG.warning("job %s: the adapter raised %s", job.job_id[:8], type(exc).__name__)
            raise JobRejected("inference-failed", "the adapter raised") from None
        if self._stop.is_set():
            raise JobRejected("internal-error", "the executor is stopping")
        return name

    def _finish(self, job: LockedJob, error_code: str, outcome: str) -> str:
        """Clear what the run left and record the failure exactly once."""
        try:
            job.remove_leftovers(keep_result=False)
        except OSError as exc:
            LOG.warning("job %s: cleanup incomplete (%s)", job.tag, type(exc).__name__)
        try:
            _, written = finalize(job, "failed", error_code=error_code)
        except StatusProblem:
            LOG.error("job %s: the failure could not be recorded", job.tag)
            return outcome
        if written == "cancelled":
            outcome = CANCELLED
        LOG.warning("job %s: %s (%s)", job.tag, outcome, written)
        return outcome

    # -- recovery ------------------------------------------------------------------
    def recover(self) -> int:
        """After a restart: fail jobs a previous run left accepted or running and
        clear what it left behind. A result.zip without `completed` never counts."""
        if not verify_jobs_directory(self.config.runtime_root, self.config.spool_owner_uid):
            return 0
        failed = 0
        for name in sorted(entry.name for entry in os.scandir(self.jobs) if JOB_NAME.fullmatch(entry.name)):
            job = LockedJob.acquire(self.jobs, name, self._wall)
            if job is None:
                continue
            try:
                try:
                    status = job.read_status()
                except StatusProblem:
                    continue  # never guess what an unreadable status said
                if status is None:
                    job.remove_leftovers(keep_result=False)
                elif status.state in contract.TERMINAL_STATES:
                    job.remove_leftovers(keep_result=status.state == "completed")
                else:
                    self._fail_interrupted(job)
                    failed += 1
            finally:
                job.close()
        return failed

    def _fail_interrupted(self, job: LockedJob) -> None:
        job.remove_leftovers(keep_result=False)
        _, written = finalize(job, "failed", error_code="internal-error")
        LOG.warning("job %s: an interrupted run was failed (%s)", job.tag, written)
