"""The executor's half of the finalization gate (see mergen_spool.gate).

A terminal status is written only while holding the job's gate, after one
last look for `cancel`. The dispatcher creates `cancel` only under the same
gate, so a cancel either precedes this step, which then writes
failed/cancelled and withdraws an announced result.zip, or it follows a
verdict that is already on disk. There is no third order: to the other side,
the check and the write are one step.
"""
from __future__ import annotations

import os

from mergen_executor.jobdir import JobRejected, LockedJob
from mergen_spool import contract
from mergen_spool.fs import exists_at
from mergen_spool.gate import GateBusy, GateMissing, GateUnavailable, finalization_gate

# The dispatcher holds the gate only to create one marker.
GATE_WAIT_SECONDS = 10.0


def check_gate(job: LockedJob) -> None:
    """Refuse, before any work, a job whose verdict could not be ordered
    against a cancel. A gate the dispatcher holds right now is a usable one."""
    try:
        with finalization_gate(job.fd, timeout=0):
            pass
    except GateBusy:
        pass
    except GateMissing:
        raise JobRejected("internal-error", "the job has no usable finalization gate") from None


def finalize(job: LockedJob, state: str, *, result: contract.ResultRef | None = None,
             error_code: str | None = None) -> tuple[str, str | None]:
    """Write the terminal status and return the (state, errorCode) written."""
    try:
        with finalization_gate(job.fd, timeout=GATE_WAIT_SECONDS):
            if job.cancelled() and error_code != "cancelled":
                state, result, error_code = "failed", None, "cancelled"
            if state != "completed":
                _withdraw_result(job)
            job.advance(state, result=result, error_code=error_code)
            return state, error_code
    except GateUnavailable:
        # Unordered, a completed verdict could follow a cancel, so none is written.
        _withdraw_result(job)
        if state == "completed":
            state, result, error_code = "failed", None, "internal-error"
        job.advance(state, result=result, error_code=error_code)
        return state, error_code


def _withdraw_result(job: LockedJob) -> None:
    if exists_at(job.fd, contract.RESULT_FILE):
        os.unlink(contract.RESULT_FILE, dir_fd=job.fd)
        os.fsync(job.fd)
