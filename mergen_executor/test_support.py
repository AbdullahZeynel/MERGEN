"""Test doubles for the executor: a fake imaging adapter, a scripted GPU probe
and a spool laid out as the dispatcher leaves it. No GPU, model weights,
network or subprocess is involved."""
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
from unittest.mock import patch

from mergen_executor import jobdir
from mergen_executor.adapter import AdapterFailure, ImagingAdapter, ImagingJob
from mergen_executor.config import ExecutorConfig
from mergen_executor.gpu import GpuState
from mergen_executor.runtime import Executor
from mergen_spool import contract
from mergen_spool.fs import read_json, write_json_atomic
from mergen_spool.gate import create_gate

JOB_ID = "e" * 32
# Stands in for image content and manifest detail; must never reach a log line.
MARKER = b"PATIENT-VOXELS"
MODALITIES = ("T1", "T1CE", "T2", "FLAIR")
DEFAULT = object()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def zip_bytes(members: list[tuple[zipfile.ZipInfo | str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
    return output.getvalue()


def imaging_manifest(paths: list[str] | None = None) -> dict:
    paths = paths or [f"volumes/{modality.lower()}.nii.gz" for modality in MODALITIES]
    return {"schemaVersion": 1, "module": "imaging", "disease": "glioma",
            "files": [{"path": path, "role": "volume", "modality": modality}
                      for path, modality in zip(paths, MODALITIES)]}


def imaging_input(extra: list[tuple[zipfile.ZipInfo | str, bytes]] | None = None,
                  manifest: dict | None = None) -> bytes:
    manifest = manifest or imaging_manifest()
    volumes = [(item["path"], MARKER + b"-" + item["modality"].encode()) for item in manifest["files"]]
    return zip_bytes([("input.json", json.dumps(manifest).encode()), *volumes, *(extra or [])])


def result_zip(job_id: str = JOB_ID, report: bytes = b'{"status":"synthetic"}') -> bytes:
    assets = {"report.json": (report, "report-json"),
              "prediction.nii.gz": (b"synthetic-mask", "prediction-nifti"),
              "prediction.glb": (b"synthetic-mesh", "prediction-glb")}
    manifest = {"schemaVersion": 1, "jobId": job_id, "module": "imaging", "disease": "glioma",
                "modelId": "fake-imaging", "modelVersion": "g3-test", "hasPrediction": True,
                "hasGroundTruth": False,
                "assets": [{"path": path, "kind": kind, "sha256": sha256(payload), "size": len(payload)}
                           for path, (payload, kind) in assets.items()]}
    return zip_bytes([("manifest.json", json.dumps(manifest).encode()),
                      *[(path, payload) for path, (payload, _) in assets.items()]])


def make_spool(base: Path) -> tuple[Path, Path]:
    """The runtime root (tmpfiles), jobs/ (dispatcher) and the state directory."""
    root, state = base / "runtime", base / "state"
    root.mkdir()
    os.chmod(root, 0o2770)
    (root / contract.JOBS_DIR).mkdir()
    os.chmod(root / contract.JOBS_DIR, contract.JOBS_MODE)
    state.mkdir()
    os.chmod(state, 0o700)
    return root, state


def publish_job(root: Path, job_id: str = JOB_ID, payload: bytes | None = None, **job) -> Path:
    """A job directory exactly as the dispatcher publishes it."""
    payload = imaging_input() if payload is None else payload
    directory = root / contract.JOBS_DIR / job_id
    directory.mkdir()
    os.chmod(directory, contract.JOB_DIRECTORY_MODE)
    create_gate(directory)
    (directory / contract.INPUT_FILE).write_bytes(payload)
    document = {"schemaVersion": 1, "kind": "mergen-spool-job", "jobId": job_id, "module": "imaging",
                "disease": "glioma",
                "input": {"path": "input.zip", "sha256": sha256(payload), "size": len(payload)},
                "maxResultBytes": 1024 * 1024, "publishedAt": 1}
    write_json_atomic(directory / contract.JOB_FILE, {**document, **job})
    return directory


def make_config(root: Path, state: Path, **overrides) -> ExecutorConfig:
    values = dict(runtime_root=root, state_root=state, spool_owner_uid=os.geteuid(),
                  pause_file=state / "pause", gpu_lock_path=state / "gpu.lock",
                  poll_seconds=0.01, gpu_wait_seconds=0.01, max_input_bytes=1024 * 1024,
                  max_expanded_bytes=4 * 1024 * 1024, max_result_bytes=1024 * 1024,
                  ready_refresh_seconds=30.0)
    values.update(overrides)
    return ExecutorConfig(**values)


def status_of(root: Path, job_id: str = JOB_ID) -> dict | None:
    path = root / contract.JOBS_DIR / job_id / contract.STATUS_FILE
    return read_json(path) if path.exists() else None


def ready_of(root: Path) -> dict:
    return read_json(root / contract.READY_FILE)


def recorded_states():
    """Patch the status writer so that it also records each state it writes."""
    states, real = [], jobdir.write_json_atomic_at

    def write(fd, name, document):
        if name == contract.STATUS_FILE:
            states.append(document["state"])
        real(fd, name, document)

    return states, patch("mergen_executor.jobdir.write_json_atomic_at", side_effect=write)


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.002)


class ScriptedGpu:
    def __init__(self, available: bool = True):
        self.available = available

    def check(self) -> GpuState:
        return GpuState(self.available, "free" if self.available else "busy")


class FakeImagingAdapter(ImagingAdapter):
    """Writes a valid result ZIP unless told otherwise. behaviour:
    "complete", "block" (until `release` is set), "wait-cancel" (until
    job.cancelled()), "fail" (AdapterFailure), "raise", "oom"."""

    model_id = "fake-imaging"
    model_version = "g3-test"

    def __init__(self, behaviour: str = "complete", *, code: str = "model-unavailable",
                 payload: bytes | None = None, name: str = "result.zip", link_to: Path | None = None,
                 after_write=None, preflight_error: BaseException | None = None):
        self.behaviour, self.code, self.payload, self.name = behaviour, code, payload, name
        self.link_to, self.after_write, self.preflight_error = link_to, after_write, preflight_error
        self.runs: list[ImagingJob] = []
        self.started, self.release = threading.Event(), threading.Event()

    def preflight(self) -> None:
        if self.preflight_error is not None:
            raise self.preflight_error

    def run(self, job: ImagingJob) -> str:
        self.runs.append(job)
        self.started.set()
        if self.behaviour == "block":
            self.release.wait(5)
        elif self.behaviour == "wait-cancel":
            wait_until(job.cancelled)
        elif self.behaviour == "fail":
            raise AdapterFailure(self.code, f"{MARKER.decode()} in the reason")
        elif self.behaviour == "raise":
            raise RuntimeError(f"{MARKER.decode()} in the message")
        elif self.behaviour == "oom":
            raise MemoryError
        target = job.output_dir / "result.zip"
        if self.link_to is not None:
            target.symlink_to(self.link_to)
        else:
            target.write_bytes(result_zip(job.job_id) if self.payload is None else self.payload)
        if self.after_write is not None:
            self.after_write(job)
        return self.name


class ExecutorCase(unittest.TestCase):
    """An executor over a temporary spool with a fake adapter and GPU probe."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-executor-test-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root, self.state = make_spool(self.base)
        self.adapter = FakeImagingAdapter()
        self.gpu = ScriptedGpu()

    def make_executor(self, adapter=DEFAULT, **overrides) -> Executor:
        adapter = self.adapter if adapter is DEFAULT else adapter
        return Executor(make_config(self.root, self.state, **overrides), adapter, gpu=self.gpu)

    def started(self, adapter=DEFAULT, **overrides) -> Executor:
        executor = self.make_executor(adapter, **overrides)
        executor.start()
        return executor

    def job_dir(self, job_id: str = JOB_ID) -> Path:
        return self.root / contract.JOBS_DIR / job_id
