"""Private Tailscale-only API used by authenticated pull workers."""
from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.archive_io import (
    InvalidArchive, UploadTooLarge, file_chunks, sha256_file,
    validate_result_archive, write_stream,
)
from backend.live_contracts import valid_worker_id
from backend.live_store import LiveSettings, LiveStore

app = FastAPI(title="MERGEN private worker control", docs_url=None, redoc_url=None, openapi_url=None)
_store: LiveStore | None = None


async def get_store():
    global _store
    if _store is None:
        _store = LiveStore(LiveSettings.from_env())
    return _store


async def authenticate(authorization: str | None = Header(None)):
    expected = os.environ.get("MERGEN_CONTROL_TOKEN", "")
    if len(expected) < 32 or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Worker authentication required")
    if not secrets.compare_digest(authorization[7:], expected):
        raise HTTPException(401, "Worker authentication required")


async def worker_header(worker_id: str | None = Header(None, alias="X-Mergen-Worker")):
    if not worker_id or not valid_worker_id(worker_id):
        raise HTTPException(400, "Invalid worker identifier")
    return worker_id


class ClaimRequest(BaseModel):
    capabilities: list[str] = Field(min_length=1, max_length=1)

    def normalized(self):
        if len(set(self.capabilities)) != len(self.capabilities):
            raise HTTPException(422, "Duplicate capability")
        if set(self.capabilities) != {"imaging"}:
            raise HTTPException(422, "Unsupported capability")
        return self.capabilities


class FailureRequest(BaseModel):
    errorCode: Literal[
        "input-invalid", "model-unavailable", "inference-failed",
        "resource-exhausted", "cancelled", "internal-error",
    ]


@app.get("/internal/health", dependencies=[Depends(authenticate)])
async def health():
    return {"status": "ready"}


@app.post("/internal/workers/heartbeat", dependencies=[Depends(authenticate)])
async def worker_heartbeat(request: ClaimRequest, worker_id: str = Depends(worker_header),
                           store: LiveStore = Depends(get_store)):
    capabilities = request.normalized()
    store.touch_worker(worker_id, capabilities)
    return {"status": "ready", "heartbeatSeconds": 30}


@app.post("/internal/jobs/claim", dependencies=[Depends(authenticate)])
async def claim(request: ClaimRequest, worker_id: str = Depends(worker_header), store: LiveStore = Depends(get_store)):
    capabilities = request.normalized()
    store.touch_worker(worker_id, capabilities)
    job = store.claim(worker_id, capabilities)
    if not job:
        return {"job": None}
    return {"job": {"jobId": job["id"], "module": job["module"], "disease": job["disease"],
                    "inputUrl": f"/internal/jobs/{job['id']}/input",
                    "inputSha256": job["input_sha256"],
                    "leaseSeconds": store.settings.lease_seconds}}


@app.get("/internal/jobs/{job_id}/input", dependencies=[Depends(authenticate)])
async def input_bundle(job_id: str, worker_id: str = Depends(worker_header), store: LiveStore = Depends(get_store)):
    job = store.worker_job(job_id, worker_id)
    if not job or job["status"] not in {"claimed", "running"} or job["lease_until"] <= store.now():
        raise HTTPException(404, "Claimed job not found")
    path = store.job_directory(job["session_id"], job_id) / "input.zip"
    if not path.is_file() or await asyncio.to_thread(sha256_file, path) != job["input_sha256"]:
        raise HTTPException(503, "Input integrity check failed")
    return StreamingResponse(file_chunks(path), media_type="application/zip",
                             headers={"Cache-Control": "no-store"})


@app.post("/internal/jobs/{job_id}/lease", dependencies=[Depends(authenticate)])
async def lease(job_id: str, worker_id: str = Depends(worker_header), store: LiveStore = Depends(get_store)):
    if not store.renew_lease(job_id, worker_id):
        raise HTTPException(409, "Lease is no longer valid")
    return {"status": "running", "leaseSeconds": store.settings.lease_seconds}


def _validate_result(path: Path, max_expanded: int, job: dict):
    return validate_result_archive(path, max_expanded, job), sha256_file(path)


def _declared_digest(value: str | None) -> str:
    # The worker states the SHA-256 of the ZIP it sends. A job is completed
    # only if the bytes that arrived hash to exactly that value.
    if not value or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise HTTPException(422, "X-Mergen-Result-Sha256 must carry the result's SHA-256")
    return value


@app.post("/internal/jobs/{job_id}/result", dependencies=[Depends(authenticate)])
async def result(job_id: str, request: Request, worker_id: str = Depends(worker_header),
                 store: LiveStore = Depends(get_store),
                 declared: str | None = Header(None, alias="X-Mergen-Result-Sha256")):
    if request.headers.get("content-type", "").split(";", 1)[0].strip() not in {
        "application/zip", "application/x-zip-compressed"
    }:
        raise HTTPException(415, "A ZIP result bundle is required")
    expected = _declared_digest(declared)
    job = store.worker_job(job_id, worker_id)
    if not job or job["status"] not in {"claimed", "running"} or job["lease_until"] <= store.now():
        raise HTTPException(409, "Lease is no longer valid")
    directory = store.job_directory(job["session_id"], job_id)
    staging, destination = directory / "result.part", directory / "result.zip"
    try:
        await write_stream(request.stream(), staging, store.settings.max_result_bytes)
        manifest, checksum = await asyncio.to_thread(
            _validate_result, staging, store.settings.max_expanded_bytes, job
        )
        if not secrets.compare_digest(checksum, expected):
            raise HTTPException(422, "Result does not match the declared digest")
        staging.replace(destination)
        if not store.complete(job_id, worker_id, checksum, manifest.model_dump()):
            destination.unlink(missing_ok=True)
            raise HTTPException(409, "Lease is no longer valid")
        return {"status": "completed", "sha256": checksum}
    except InvalidArchive as exc:
        raise HTTPException(422, str(exc)) from None
    except UploadTooLarge:
        raise HTTPException(413, "Result is too large") from None
    finally:
        staging.unlink(missing_ok=True)


@app.post("/internal/jobs/{job_id}/failure", dependencies=[Depends(authenticate)])
async def failure(job_id: str, request: FailureRequest, worker_id: str = Depends(worker_header),
            store: LiveStore = Depends(get_store)):
    if not store.fail(job_id, worker_id, request.errorCode):
        raise HTTPException(409, "Job is no longer owned by this worker")
    return {"status": "failed"}
