"""Browser-facing live-session routes. No model code runs in this process."""
from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import os
import secrets
import zipfile
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from backend.archive_io import (
    InvalidArchive, UploadTooLarge, file_chunks, sha256_file,
    validate_input_archive, write_stream,
)
from backend.live_store import CapacityError, LiveSettings, LiveStore
from backend.live_contracts import LIVE_PROFILES

SESSION_COOKIE = "mergen_session"
CSRF_COOKIE = "mergen_csrf"
router = APIRouter(prefix="/api/live", tags=["live"])
LOG = logging.getLogger("mergen.live")
_store: LiveStore | None = None


async def get_live_store() -> LiveStore:
    global _store
    if _store is None:
        try:
            settings = LiveSettings.from_env()
        except ValueError as exc:
            # Only the live layer refuses; the demo routes do not depend on it.
            LOG.error("live session layer disabled: %s", exc)
            raise HTTPException(503, "Live sessions are not configured") from None
        _store = LiveStore(settings)
    return _store


async def current_session(
    token: str | None = Cookie(None, alias=SESSION_COOKIE),
    store: LiveStore = Depends(get_live_store),
):
    session = store.get_session(token)
    if not session:
        raise HTTPException(401, "Live session is missing or expired")
    return session


async def mutation_session(
    session: dict = Depends(current_session),
    csrf_cookie: str | None = Cookie(None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(None, alias="X-Mergen-CSRF"),
    store: LiveStore = Depends(get_live_store),
):
    if not store.validate_csrf(session, csrf_cookie, csrf_header):
        raise HTTPException(403, "Invalid CSRF token")
    return session


def _set_cookies(response: Response, session: dict, secure: bool):
    common = {"secure": secure, "samesite": "strict", "path": "/api/live",
              "max_age": session["absolute_expires"] - session["created_at"]}
    response.set_cookie(SESSION_COOKIE, session["token"], httponly=True, **common)
    csrf_common = dict(common)
    csrf_common["path"] = "/"
    response.set_cookie(CSRF_COOKIE, session["csrf"], httponly=False, **csrf_common)


@router.get("/profiles")
async def profiles(response: Response):
    response.headers["Cache-Control"] = "public, max-age=300"
    return LIVE_PROFILES


@router.post("/session", status_code=201)
async def create_session(
    response: Response,
    token: str | None = Cookie(None, alias=SESSION_COOKIE),
    csrf_cookie: str | None = Cookie(None, alias=CSRF_COOKIE),
    access_code: str | None = Header(None, alias="X-Mergen-Live-Access"),
    store: LiveStore = Depends(get_live_store),
):
    response.headers["Cache-Control"] = "no-store"
    existing = store.get_session(token)
    if existing:
        if not store.validate_csrf(existing, csrf_cookie, csrf_cookie):
            raise HTTPException(409, "Existing live session cannot be resumed")
        if store.heartbeat(existing["id"]) is not None:
            return {"status": "active", "csrfToken": csrf_cookie,
                    "idleTimeoutSeconds": store.settings.idle_seconds,
                    "absoluteExpiresAt": existing["absolute_expires"]}
    expected_access = os.environ.get("MERGEN_LIVE_ACCESS_HASH", "")
    if len(expected_access) != 64:
        raise HTTPException(503, "Live sessions are not configured")
    supplied_hash = hashlib.sha256((access_code or "").encode()).hexdigest()
    if not secrets.compare_digest(supplied_hash, expected_access):
        raise HTTPException(401, "Live access code is invalid")
    await asyncio.to_thread(store.cleanup)
    try:
        session = store.create_session()
    except CapacityError:
        raise HTTPException(429, "Live session capacity reached", headers={"Retry-After": "60"}) from None
    _set_cookies(response, session, store.settings.cookie_secure)
    return {"status": "active", "csrfToken": session["csrf"],
            "idleTimeoutSeconds": store.settings.idle_seconds,
            "absoluteExpiresAt": session["absolute_expires"]}


@router.get("/session")
async def session_status(response: Response, session: dict = Depends(current_session), store: LiveStore = Depends(get_live_store)):
    response.headers["Cache-Control"] = "no-store"
    return {"status": "active", "idleTimeoutSeconds": store.settings.idle_seconds,
            "absoluteExpiresAt": session["absolute_expires"]}


@router.post("/session/heartbeat")
async def heartbeat(response: Response, session: dict = Depends(mutation_session), store: LiveStore = Depends(get_live_store)):
    response.headers["Cache-Control"] = "no-store"
    last_seen = store.heartbeat(session["id"])
    if last_seen is None:
        raise HTTPException(401, "Live session is missing or expired")
    return {"status": "active", "lastSeen": last_seen}


@router.delete("/session", status_code=204)
async def close_session(response: Response, session: dict = Depends(mutation_session),
                  store: LiveStore = Depends(get_live_store)):
    await asyncio.to_thread(store.delete_session, session["id"])
    response.delete_cookie(SESSION_COOKIE, path="/api/live")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def _zip_chunks(path: Path, member: str):
    with zipfile.ZipFile(path) as archive, archive.open(member) as handle:
        while chunk := handle.read(1024 * 1024):
            yield chunk


def _asset_matches(path: Path, member: str, expected_size: int, expected_sha256: str) -> bool:
    try:
        size, digest = 0, hashlib.sha256()
        with zipfile.ZipFile(path) as archive:
            if archive.getinfo(member).file_size != expected_size:
                return False
            with archive.open(member) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
        return size == expected_size and secrets.compare_digest(digest.hexdigest(), expected_sha256)
    except (OSError, KeyError, zipfile.BadZipFile):
        return False


def _validate_input(path: Path, max_expanded: int):
    return validate_input_archive(path, max_expanded), sha256_file(path)


@router.post("/jobs", status_code=202)
async def create_job(
    request: Request,
    response: Response,
    session: dict = Depends(mutation_session),
    store: LiveStore = Depends(get_live_store),
):
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("content-type", "").split(";", 1)[0].strip() not in {
        "application/zip", "application/x-zip-compressed"
    }:
        raise HTTPException(415, "A ZIP input bundle is required")
    staging = store.session_directory(session["id"]) / f"upload-{secrets.token_hex(8)}.part"
    try:
        await write_stream(request.stream(), staging, store.settings.max_upload_bytes)
        manifest, checksum = await asyncio.to_thread(
            _validate_input, staging, store.settings.max_expanded_bytes
        )
        job_id = secrets.token_hex(16)
        try:
            await asyncio.to_thread(
                store.publish_job_input,
                session["id"], manifest.module, manifest.disease, checksum, staging, job_id
            )
        except CapacityError:
            raise HTTPException(409, "This session already has an active job") from None
        return {"jobId": job_id, "status": "queued", "module": manifest.module,
                "disease": manifest.disease}
    except InvalidArchive as exc:
        raise HTTPException(422, str(exc)) from None
    except UploadTooLarge:
        raise HTTPException(413, "Upload is too large") from None
    finally:
        staging.unlink(missing_ok=True)


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, response: Response, session: dict = Depends(current_session),
               store: LiveStore = Depends(get_live_store)):
    response.headers["Cache-Control"] = "no-store"
    job = store.job_for_session(job_id, session["id"])
    if not job:
        raise HTTPException(404, "Job not found")
    result = {"jobId": job["id"], "module": job["module"], "disease": job["disease"],
              "status": job["status"], "createdAt": job["created_at"], "updatedAt": job["updated_at"]}
    if job["status"] == "completed":
        result["result"] = json.loads(job["result_manifest"])
        result["downloadUrl"] = f"/api/live/jobs/{job_id}/download"
        result["assetUrls"] = {
            asset["path"]: f"/api/live/jobs/{job_id}/assets/{asset['path']}"
            for asset in result["result"]["assets"]
        }
    elif job["status"] == "failed":
        result["errorCode"] = job["error_code"]
    return result


@router.get("/jobs/{job_id}/download")
async def download(job_id: str, session: dict = Depends(current_session),
             store: LiveStore = Depends(get_live_store)):
    job = store.job_for_session(job_id, session["id"])
    if not job or job["status"] != "completed":
        raise HTTPException(404, "Completed result not found")
    path = store.job_directory(session["id"], job_id) / "result.zip"
    if not path.is_file() or await asyncio.to_thread(sha256_file, path) != job["result_sha256"]:
        raise HTTPException(503, "Result integrity check failed")
    return StreamingResponse(
        file_chunks(path), media_type="application/zip",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": f'attachment; filename="MERGEN-{job_id}.zip"'},
    )


@router.get("/jobs/{job_id}/assets/{asset_path:path}")
async def result_asset(job_id: str, asset_path: str, session: dict = Depends(current_session),
                       store: LiveStore = Depends(get_live_store)):
    job = store.job_for_session(job_id, session["id"])
    if not job or job["status"] != "completed":
        raise HTTPException(404, "Completed result not found")
    manifest = json.loads(job["result_manifest"])
    asset = next((item for item in manifest["assets"] if item["path"] == asset_path), None)
    if not asset:
        raise HTTPException(404, "Result asset not found")
    path = store.job_directory(session["id"], job_id) / "result.zip"
    if not path.is_file() or not await asyncio.to_thread(
        _asset_matches, path, asset_path, asset["size"], asset["sha256"]
    ):
        raise HTTPException(503, "Result integrity check failed")
    mime = {
        "report-json": "application/json",
        "report-pdf": "application/pdf",
        "prediction-nifti": "application/gzip",
        "prediction-glb": "model/gltf-binary",
        "slice": "image/png",
        "overlay": "image/png",
    }[asset["kind"]]
    return StreamingResponse(_zip_chunks(path, asset_path), media_type=mime,
                             headers={"Cache-Control": "no-store",
                                      "X-Content-Type-Options": "nosniff"})
