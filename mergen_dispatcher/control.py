"""The dispatcher's only network surface: the VPS worker control API."""
from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import httpx

from mergen_dispatcher.config import DispatcherConfig

CHUNK = 1024 * 1024
JOB_ID = re.compile(r"^[a-f0-9]{32}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ControlUnavailable(Exception):
    """Transport failure or a retryable answer. Back off and try again."""


class LeaseLost(Exception):
    """The VPS no longer lets this worker own the job. Never retried."""


class InputRejected(Exception):
    """The input cannot be delivered: size limit or checksum mismatch."""


class ProtocolError(Exception):
    """The VPS answered outside the contract; nothing is guessed from it."""


class ResultRejected(Exception):
    """A definite 4xx for an uploaded result; the job was not completed."""

    def __init__(self, error_code: str):
        super().__init__(f"result rejected ({error_code})")
        self.error_code = error_code


class ResultChanged(Exception):
    """The result bytes differ from the verified ones; no complete body was sent."""


@dataclass(frozen=True)
class ClaimedJob:
    job_id: str
    module: str
    disease: str
    input_sha256: str
    lease_seconds: int
    claimed_at: float  # monotonic time the claim request was sent

    @property
    def tag(self) -> str:
        # Enough to correlate log lines, not the full identifier.
        return self.job_id[:8]


class ControlClient:
    def __init__(self, config: DispatcherConfig, transport: httpx.BaseTransport | None = None):
        # trust_env=False: no proxy variable or .netrc may reroute the token.
        self._client = httpx.Client(
            base_url=config.control_url,
            headers={"Authorization": f"Bearer {config.token}", "X-Mergen-Worker": config.worker_id},
            timeout=httpx.Timeout(config.request_timeout_seconds),
            transport=transport, follow_redirects=False, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, **kwargs) -> httpx.Response:
        try:
            return self._client.post(path, **kwargs)
        except httpx.TransportError:
            # `from None`: httpx messages carry the URL, which is an address.
            raise ControlUnavailable("control API unreachable") from None

    @staticmethod
    def _unexpected(response: httpx.Response, what: str) -> Exception:
        if response.status_code >= 500 or response.status_code in (401, 403, 429):
            return ControlUnavailable(f"{what} answered {response.status_code}")
        return ProtocolError(f"{what} answered {response.status_code}")

    def heartbeat(self, capabilities: list[str]) -> None:
        response = self._post("/internal/workers/heartbeat", json={"capabilities": capabilities})
        if response.status_code != 200:
            raise self._unexpected(response, "heartbeat")

    def claim(self, capabilities: list[str], clock: Callable[[], float]) -> ClaimedJob | None:
        started = clock()
        response = self._post("/internal/jobs/claim", json={"capabilities": capabilities})
        if response.status_code != 200:
            raise self._unexpected(response, "claim")
        try:
            job = response.json()["job"]
        except (ValueError, KeyError, TypeError):
            raise ProtocolError("claim answer is not the documented JSON") from None
        return None if job is None else _claimed_job(job, capabilities, started)

    def download(self, job: ClaimedJob, destination: Path, limit: int,
                 still_valid: Callable[[], bool]) -> int:
        """Stream the input to `destination`, hashing and counting as it arrives."""
        digest, size = hashlib.sha256(), 0
        try:
            with self._client.stream("GET", f"/internal/jobs/{job.job_id}/input") as response:
                if response.status_code == 404:
                    raise LeaseLost("the VPS no longer offers this input")
                if response.status_code != 200:
                    raise self._unexpected(response, "input download")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > limit):
                    raise InputRejected("input exceeds the size limit")
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660)
                with os.fdopen(fd, "wb") as output:
                    for chunk in response.iter_bytes(CHUNK):
                        size += len(chunk)
                        if size > limit:
                            raise InputRejected("input exceeds the size limit")
                        if not still_valid():
                            raise LeaseLost("the lease ended during the download")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
        except httpx.TransportError:
            raise ControlUnavailable("the input download was interrupted") from None
        if digest.hexdigest() != job.input_sha256:
            raise InputRejected("input checksum does not match the claim")
        return size

    def renew(self, job_id: str) -> int:
        response = self._post(f"/internal/jobs/{job_id}/lease")
        if response.status_code == 409:
            raise LeaseLost("lease renewal was refused")
        if response.status_code != 200:
            raise self._unexpected(response, "lease renewal")
        try:
            seconds = response.json()["leaseSeconds"]
        except (ValueError, KeyError, TypeError):
            raise ProtocolError("lease answer is not the documented JSON") from None
        if type(seconds) is not int or not 30 <= seconds <= 3600:
            raise ProtocolError("lease answer is out of range")
        return seconds

    def upload(self, job_id: str, handle: BinaryIO, size: int, digest: str,
               still_valid: Callable[[], bool]) -> None:
        """Stream the verified result from the descriptor the caller holds.

        The digest is computed again while sending and the final chunk is held
        back until it matches, so bytes changed after verification never reach
        the VPS as a complete body. The VPS itself completes the job only if the
        body hashes to the declared X-Mergen-Result-Sha256.
        """
        handle.seek(0)

        def body():
            hasher, read, pending = hashlib.sha256(), 0, None
            while chunk := handle.read(CHUNK):
                if not still_valid():
                    raise LeaseLost("the lease ended during the upload")
                read += len(chunk)
                if read > size:
                    raise ResultChanged("the result grew after verification")
                hasher.update(chunk)
                if pending is not None:
                    yield pending
                pending = chunk
            if read != size or hasher.hexdigest() != digest:
                raise ResultChanged("the result changed after verification")
            if pending is not None:
                yield pending

        try:
            response = self._client.post(
                f"/internal/jobs/{job_id}/result", content=body(),
                headers={"Content-Type": "application/zip", "Content-Length": str(size),
                         "X-Mergen-Result-Sha256": digest})
        except httpx.TransportError:
            raise ControlUnavailable("the result upload was interrupted") from None
        if response.status_code == 409:
            raise LeaseLost("the VPS refused the result for this lease")
        if response.status_code in (413, 422):
            raise ResultRejected("resource-exhausted" if response.status_code == 413 else "inference-failed")
        if response.status_code != 200:
            raise self._unexpected(response, "result upload")
        try:
            answer = response.json()
        except ValueError:
            raise ProtocolError("upload answer is not JSON") from None
        if not isinstance(answer, dict) or answer.get("status") != "completed" or answer.get("sha256") != digest:
            raise ProtocolError("the VPS acknowledged a different result")

    def fail(self, job_id: str, error_code: str) -> None:
        response = self._post(f"/internal/jobs/{job_id}/failure", json={"errorCode": error_code})
        if response.status_code == 409:
            raise LeaseLost("the job is no longer owned by this worker")
        if response.status_code != 200:
            raise self._unexpected(response, "failure report")


def _claimed_job(job: object, capabilities: list[str], started: float) -> ClaimedJob:
    try:
        job_id, module, disease = job["jobId"], job["module"], job["disease"]
        digest, lease, url = job["inputSha256"], job["leaseSeconds"], job["inputUrl"]
    except (KeyError, TypeError):
        raise ProtocolError("claimed job misses a documented field") from None
    valid = (isinstance(job_id, str) and JOB_ID.fullmatch(job_id) and module in capabilities
             and isinstance(disease, str) and SLUG.fullmatch(disease)
             and isinstance(digest, str) and SHA256.fullmatch(digest)
             and type(lease) is int and 30 <= lease <= 3600
             # Only the documented path: an answer never redirects the download.
             and url == f"/internal/jobs/{job_id}/input")
    if not valid:
        raise ProtocolError("claimed job does not match the contract")
    return ClaimedJob(job_id, module, disease, digest, lease, started)
