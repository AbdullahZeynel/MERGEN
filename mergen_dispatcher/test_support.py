"""Test doubles for the dispatcher: the VPS control API behind an
httpx.MockTransport, and the executor side of the spool contract. No network,
no GPU and no real host directory is involved."""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

import httpx

from mergen_dispatcher.config import DispatcherConfig
from mergen_dispatcher.runtime import Dispatcher
from mergen_spool import contract
from mergen_spool.fs import lock_directory, read_json, write_json_atomic

# Fixture identity only; the first literal stays short so it never looks like a credential.
TOKEN = "fake-" + "k" * 40
WORKER_ID = "gpu-test"
CONTROL_URL = "http://control.test"
DISEASE = "glioma"
JOB_ID = "c" * 32


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return output.getvalue()


def imaging_input(marker: bytes = b"volume") -> bytes:
    volumes = {
        "volumes/t1.nii.gz": marker + b"-t1",
        "volumes/t1ce.nii.gz": marker + b"-t1ce",
        "volumes/t2.nii.gz": marker + b"-t2",
        "volumes/flair.nii.gz": marker + b"-flair",
    }
    manifest = {
        "schemaVersion": 1, "module": "imaging", "disease": DISEASE,
        "files": [
            {"path": path, "role": "volume", "modality": modality}
            for path, modality in zip(volumes, ("T1", "T1CE", "T2", "FLAIR"))
        ],
    }
    return zip_bytes({"input.json": json.dumps(manifest).encode(), **volumes})


def imaging_result(job_id: str = JOB_ID, module: str = "imaging",
                   report: bytes = b'{"status":"synthetic-transport"}') -> bytes:
    files = {
        "report.json": report,
        "prediction.nii.gz": b"synthetic-prediction",
        "prediction.glb": b"synthetic-mesh",
    }
    kinds = {"report.json": "report-json", "prediction.nii.gz": "prediction-nifti",
             "prediction.glb": "prediction-glb"}
    manifest = {
        "schemaVersion": 1, "jobId": job_id, "module": module, "disease": DISEASE,
        "modelId": "mergen-imaging", "modelVersion": "test-1", "hasPrediction": True,
        "hasGroundTruth": False,
        "assets": [{"path": path, "kind": kinds[path], "sha256": sha256(payload),
                    "size": len(payload)} for path, payload in files.items()],
    }
    return zip_bytes({"manifest.json": json.dumps(manifest).encode(), **files})


def make_runtime(base: Path) -> Path:
    root = base / "runtime"
    root.mkdir()
    os.chmod(root, 0o2770)
    return root


def make_config(root: Path, **overrides) -> DispatcherConfig:
    values = dict(control_url=CONTROL_URL, token=TOKEN, worker_id=WORKER_ID, runtime_root=root,
                  poll_seconds=0.01, lease_renew_seconds=0.02, request_timeout_seconds=5,
                  max_input_bytes=1024 * 1024, max_expanded_bytes=4 * 1024 * 1024,
                  max_result_bytes=1024 * 1024, heartbeat_seconds=0.0, spool_poll_seconds=0.01,
                  executor_stale_seconds=90, backoff_initial_seconds=0.01,
                  backoff_max_seconds=0.05, transfer_attempts=3)
    values.update(overrides)
    return DispatcherConfig(**values)


def write_ready(root: Path, capabilities=("imaging",), accepting: bool = True,
                updated: float | None = None) -> None:
    write_json_atomic(root / contract.READY_FILE, {
        "schemaVersion": 1, "kind": "mergen-executor-ready", "capabilities": list(capabilities),
        "acceptingJobs": accepting, "updatedAt": int(time.time() if updated is None else updated)})


def publish_job(root: Path, job_id: str = JOB_ID, input_bytes: bytes | None = None) -> Path:
    """A job directory as a dispatcher left it before a restart."""
    payload = imaging_input() if input_bytes is None else input_bytes
    directory = root / contract.JOBS_DIR / job_id
    directory.mkdir(parents=True)
    (directory / contract.INPUT_FILE).write_bytes(payload)
    write_json_atomic(directory / contract.JOB_FILE, {
        "schemaVersion": 1, "kind": "mergen-spool-job", "jobId": job_id, "module": "imaging",
        "disease": DISEASE, "input": {"path": "input.zip", "sha256": sha256(payload), "size": len(payload)},
        "maxResultBytes": 1024 * 1024, "publishedAt": 1})
    return directory


def write_status(directory: Path, state: str, *, result: bytes | None = None,
                 error_code: str | None = None, job_id: str = JOB_ID) -> None:
    document = {"schemaVersion": 1, "kind": "mergen-spool-status", "jobId": job_id,
                "state": state, "updatedAt": int(time.time())}
    if result is not None:
        temporary = directory / ".result.zip.tmp"
        temporary.write_bytes(result)
        os.replace(temporary, directory / contract.RESULT_FILE)
        document["result"] = {"path": "result.zip", "sha256": sha256(result), "size": len(result)}
    if error_code is not None:
        document["errorCode"] = error_code
    write_json_atomic(directory / contract.STATUS_FILE, document)


class FakeControl:
    """The VPS worker control API, as far as the dispatcher can observe it."""

    def __init__(self, input_bytes: bytes | None = None, *, lease_seconds: int = 60):
        self.lock = threading.Lock()
        self.input_bytes = imaging_input() if input_bytes is None else input_bytes
        self.job = {"jobId": JOB_ID, "module": "imaging", "disease": DISEASE,
                    "inputUrl": f"/internal/jobs/{JOB_ID}/input",
                    "inputSha256": sha256(self.input_bytes), "leaseSeconds": lease_seconds}
        self.claimable = True
        self.calls: list[str] = []
        self.bodies: list[dict] = []
        self.renewals = 0
        self.lease_answer = 200
        # The real VPS refuses to renew a completed job; a test may switch that off.
        self.lease_follows_completion = True
        self.outages = 0
        self.download_cut = 0
        self.download_hook = None
        self.served_input: bytes | None = None
        self.content_length: int | None = None
        self.lose_upload_response = False
        self.upload_attempts = 0
        self.upload_hook = None
        self.completed_with: bytes | None = None
        self.failures: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def count(self, call: str) -> int:
        with self.lock:
            return self.calls.count(call)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        with self.lock:
            self.calls.append(f"{request.method} {path}")
            if (request.headers.get("authorization") != f"Bearer {TOKEN}"
                    or request.headers.get("x-mergen-worker") != WORKER_ID):
                return httpx.Response(401)
            if self.outages:
                self.outages -= 1
                raise httpx.ConnectError("simulated outage")
        if path in ("/internal/workers/heartbeat", "/internal/jobs/claim"):
            with self.lock:
                self.bodies.append(json.loads(request.content))
                if path.endswith("heartbeat"):
                    return httpx.Response(200, json={"status": "ready", "heartbeatSeconds": 30})
                job, self.claimable = (self.job if self.claimable else None), False
            return httpx.Response(200, json={"job": job})
        if path == f"/internal/jobs/{JOB_ID}/input":
            return self._input()
        if path == f"/internal/jobs/{JOB_ID}/lease":
            with self.lock:
                self.renewals += 1
                if self.lease_answer != 200 or (self.lease_follows_completion
                                                and self.completed_with is not None):
                    return httpx.Response(409, json={"detail": "Lease is no longer valid"})
            return httpx.Response(200, json={"status": "running", "leaseSeconds": self.job["leaseSeconds"]})
        if path == f"/internal/jobs/{JOB_ID}/result":
            return self._result(request)
        if path == f"/internal/jobs/{JOB_ID}/failure":
            with self.lock:
                if self.lease_answer != 200 or self.completed_with is not None:
                    return httpx.Response(409)
                self.failures.append(json.loads(request.content)["errorCode"])
            return httpx.Response(200, json={"status": "failed"})
        return httpx.Response(404)

    def _input(self) -> httpx.Response:
        if self.download_hook:
            self.download_hook()
        payload = self.input_bytes if self.served_input is None else self.served_input
        headers = {"content-type": "application/zip"}
        if self.content_length is not None:
            headers["content-length"] = str(self.content_length)
        with self.lock:
            cut = self.download_cut > 0
            self.download_cut -= int(cut)

        def stream():
            half = len(payload) // 2
            yield payload[:half]
            if cut:
                raise httpx.ReadError("simulated cut")
            yield payload[half:]

        return httpx.Response(200, headers=headers, content=stream())

    def _result(self, request: httpx.Request) -> httpx.Response:
        if self.upload_hook:
            self.upload_hook()
        # MockTransport has already read the whole body when this runs.
        body = request.read()
        with self.lock:
            self.upload_attempts += 1
            if self.lease_answer != 200 or self.completed_with is not None:
                return httpx.Response(409, json={"detail": "Lease is no longer valid"})
            # As on the VPS: complete only the bytes the worker declared.
            if request.headers.get("x-mergen-result-sha256") != sha256(body):
                return httpx.Response(422, json={"detail": "Result does not match the declared digest"})
            self.completed_with = body
            lose, self.lose_upload_response = self.lose_upload_response, False
        if lose:
            raise httpx.ReadError("simulated lost answer")
        return httpx.Response(200, json={"status": "completed", "sha256": sha256(body)})


class FakeExecutor(threading.Thread):
    """The G3 side of the spool: waits for a published job, holds its directory
    lock and answers through status.json and result.zip.

    verdict: "complete", "fail", "hold" (wait for the cancel marker),
    "backwards" (running, then accepted) or "garbage" (unparseable status).
    """

    def __init__(self, root: Path, *, verdict: str = "complete", result: bytes | None = None,
                 error_code: str = "model-unavailable", work_seconds: float = 0.0,
                 on_running=None):
        super().__init__(daemon=True)
        self.root, self.verdict, self.error_code = root, verdict, error_code
        self.result = imaging_result() if result is None else result
        self.work_seconds, self.on_running = work_seconds, on_running
        self.job: contract.SpoolJob | None = None
        self.saw_cancel = threading.Event()
        self.failure: BaseException | None = None

    def run(self) -> None:
        try:
            directory = self.root / contract.JOBS_DIR / JOB_ID
            deadline = time.monotonic() + 5
            while not directory.is_dir():
                if time.monotonic() > deadline:
                    raise TimeoutError("the job was never published")
                time.sleep(0.002)
            fd = lock_directory(directory, blocking=True)
            try:
                self._answer(directory, fd)
            finally:
                os.close(fd)
        except BaseException as exc:  # surfaced by the test through .failure
            self.failure = exc

    def _answer(self, directory: Path, fd: int) -> None:
        self.job = contract.SpoolJob.model_validate(read_json(directory / contract.JOB_FILE))
        if sha256((directory / contract.INPUT_FILE).read_bytes()) != self.job.input.sha256:
            raise AssertionError("published input does not match job.json")
        write_status(directory, "accepted")
        write_status(directory, "running")
        if self.on_running:
            self.on_running()
        time.sleep(self.work_seconds)
        if self.verdict == "complete":
            write_status(directory, "completed", result=self.result)
        elif self.verdict == "fail":
            write_status(directory, "failed", error_code=self.error_code)
        elif self.verdict == "backwards":
            write_status(directory, "accepted")
        elif self.verdict == "garbage":
            (directory / contract.STATUS_FILE).write_text("{not json", encoding="utf-8")
        elif self.verdict == "hold":
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    os.stat(contract.CANCEL_FILE, dir_fd=fd)
                except FileNotFoundError:
                    time.sleep(0.002)
                    continue
                self.saw_cancel.set()
                return


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


class DispatcherCase(unittest.TestCase):
    """A dispatcher over a temporary spool and a fake control API."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-dispatcher-test-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = make_runtime(self.base)
        self.fake = FakeControl()
        self.dispatcher = self.make_dispatcher()
        self.dispatcher.spool.prepare()

    def make_dispatcher(self, **overrides) -> Dispatcher:
        dispatcher = Dispatcher(make_config(self.root, **overrides), transport=self.fake.transport(),
                                jitter=lambda: 1.0)
        self.addCleanup(dispatcher.close)
        return dispatcher

    def start_executor(self, **kwargs) -> FakeExecutor:
        executor = FakeExecutor(self.root, **kwargs)
        executor.start()
        self.addCleanup(executor.join, 5)
        return executor

    def assertSpoolEmpty(self):
        for name in (contract.STAGING_DIR, contract.JOBS_DIR, contract.TRASH_DIR):
            self.assertEqual(list((self.root / name).iterdir()), [], f"{name}/ is not empty")
