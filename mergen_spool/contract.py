"""Spool contract v1: the only channel between dispatcher and executor.

The two services share one directory tree and nothing else: no socket, no
token, no VPS address. Each file has exactly one writer, so the processes
never race on the same file:

    <runtime>/executor.json          executor    capabilities and admission
    <runtime>/staging/<id>-<rand>/   dispatcher  assembly area, never read
    <runtime>/jobs/<jobId>/          dispatcher  appears by one atomic rename
        job.json                     dispatcher  written once, before rename
        input.zip                    dispatcher  written once, before rename
        cancel                       dispatcher  empty marker: lease is gone
        status.json                  executor    replaced atomically
        result.zip                   executor    complete before `completed`
    <runtime>/trash/<jobId>-<rand>/  dispatcher  removed once unlocked

The executor holds an exclusive flock on a job directory while it works in
it; the dispatcher deletes a directory only while holding that lock itself.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION = 1

STAGING_DIR = "staging"
JOBS_DIR = "jobs"
TRASH_DIR = "trash"
READY_FILE = "executor.json"

JOB_FILE = "job.json"
INPUT_FILE = "input.zip"
CANCEL_FILE = "cancel"
STATUS_FILE = "status.json"
RESULT_FILE = "result.zip"

JobId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)]
Module = Literal["imaging", "genomics"]
State = Literal["accepted", "running", "completed", "failed"]
# The failure vocabulary of the VPS control API (backend/control.py).
ErrorCode = Literal["input-invalid", "model-unavailable", "inference-failed",
                    "resource-exhausted", "cancelled", "internal-error"]

TERMINAL_STATES = frozenset({"completed", "failed"})
_ORDER = {"accepted": 1, "running": 2, "completed": 3, "failed": 3}


class _Document(BaseModel):
    # Unknown keys and loose types are contract violations, not extensions:
    # a new field needs a new schemaVersion.
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InputRef(_Document):
    path: Literal["input.zip"]
    sha256: Sha256
    size: int = Field(ge=0)


class ResultRef(_Document):
    path: Literal["result.zip"]
    sha256: Sha256
    size: int = Field(ge=1)


class SpoolJob(_Document):
    """job.json: what the executor may run. Written once, before publication."""

    schemaVersion: Literal[1]
    kind: Literal["mergen-spool-job"]
    jobId: JobId
    module: Module
    disease: Slug
    input: InputRef
    maxResultBytes: int = Field(gt=0)
    publishedAt: int = Field(ge=0)


class SpoolStatus(_Document):
    """status.json: the executor's progress. Replaced atomically, never edited."""

    schemaVersion: Literal[1]
    kind: Literal["mergen-spool-status"]
    jobId: JobId
    state: State
    updatedAt: int = Field(ge=0)
    result: ResultRef | None = None
    errorCode: ErrorCode | None = None

    @model_validator(mode="after")
    def terminal_fields_match_the_state(self):
        if (self.state == "completed") != (self.result is not None):
            raise ValueError("result is present exactly when the state is completed")
        if (self.state == "failed") != (self.errorCode is not None):
            raise ValueError("errorCode is present exactly when the state is failed")
        return self


class ExecutorReady(_Document):
    """executor.json: which modules the executor can run and whether it can
    start a job now. Without a fresh one the dispatcher advertises nothing."""

    schemaVersion: Literal[1]
    kind: Literal["mergen-executor-ready"]
    capabilities: list[Module] = Field(max_length=2)
    acceptingJobs: bool
    updatedAt: int = Field(ge=0)

    @model_validator(mode="after")
    def capabilities_are_unique(self):
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("duplicate capability")
        return self


def advances(previous: str | None, current: str) -> bool:
    """True when `current` may follow `previous` as seen by a poller.

    A poller can miss intermediate states, so skipping forward is allowed.
    Moving backwards, or leaving a terminal state, is a contract violation.
    """
    if previous is None:
        return True
    if previous in TERMINAL_STATES:
        return current == previous
    return _ORDER[current] >= _ORDER[previous]
