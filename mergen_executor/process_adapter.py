"""Operator-managed manifest + checksummed model runner behind a process boundary."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

from mergen_executor.adapter import AdapterFailure, ImagingAdapter, ImagingJob
from mergen_executor.sandbox import supported

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
# The only verdicts a runner may report for itself (contracts/MODEL_RUNNER.md).
# Anything else it writes is an unreadable response, not a diagnosis.
_RUNNER_CODES = frozenset({"input-invalid", "resource-exhausted"})


class ProcessImagingAdapter(ImagingAdapter):
    def __init__(self, model_root: Path, imaging_venv: Path, *, timeout: float, term_grace: float):
        self.root, self.python = model_root, imaging_venv / "bin/python"
        self.timeout, self.term_grace = timeout, term_grace
        self.model_id = self.model_version = self.module = ""
        try:
            document = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
            self.model_id = document.get("modelId", "")
            self.model_version = document.get("modelVersion", "")
            self.module = document.get("runnerModule", "")
        except (OSError, TypeError, json.JSONDecodeError):
            pass

    def preflight(self) -> None:
        try:
            manifest_path = self.root / "manifest.json"
            if self.root.is_symlink() or manifest_path.is_symlink():
                raise ValueError
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (document["modelId"], document["modelVersion"], document["runnerModule"]) != (
                    self.model_id, self.model_version, self.module):
                raise ValueError
            if document.get("schemaVersion") != 1 or not _MODULE.fullmatch(self.module):
                raise ValueError
            if not self.python.is_file() or not os.access(self.python, os.X_OK) or not supported():
                raise ValueError
            for item in document["checkpoints"]:
                relative = PurePosixPath(item["path"])
                if relative.is_absolute() or ".." in relative.parts or not _SHA.fullmatch(item["sha256"]):
                    raise ValueError
                path = self.root.joinpath(*relative.parts)
                current = self.root
                for component in relative.parts:
                    current /= component
                    if current.is_symlink():
                        raise ValueError
                if not path.is_file() or path.stat().st_size != item["size"]:
                    raise ValueError
                digest = hashlib.sha256()
                with path.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError
            with tempfile.TemporaryDirectory(prefix="mergen-preflight-") as output:
                try:
                    self._invoke({"operation": "preflight", "modelRoot": str(self.root),
                                  "modelId": self.model_id,
                                  "modelVersion": self.model_version}, Path(output), None,
                                 min(max(self.timeout, 30), 300))
                except AdapterFailure:
                    raise ValueError from None
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise AdapterFailure("model-unavailable") from None

    def run(self, job: ImagingJob) -> str:
        request = {"operation": "run", "jobId": job.job_id, "disease": job.disease,
                   "modelRoot": str(self.root), "inputDir": str(job.input_dir),
                   "outputDir": str(job.output_dir),
                   "volumes": {key: str(value) for key, value in job.volumes.items()},
                   "maxResultBytes": job.max_result_bytes,
                   "modelId": self.model_id, "modelVersion": self.model_version}
        return self._invoke(request, job.output_dir, job.cancelled, self.timeout)

    def _invoke(self, request: dict, output: Path, cancelled, timeout: float) -> str:
        response = output / ".adapter-response.json"
        command = [sys.executable, "-P", "-m", "mergen_executor.sandbox", "--output", str(output),
                   "--python", str(self.python), "--module", self.module]
        child_env = {key: value for key, value in os.environ.items()
                     if not key.startswith(("MERGEN_CONTROL_", "MERGEN_WORKER_", "MERGEN_VPS_"))}
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True, text=True,
                                   env=child_env)
        process.stdin.write(json.dumps(request))
        process.stdin.close()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if (cancelled and cancelled()) or time.monotonic() >= deadline:
                self._terminate(process)
                raise AdapterFailure("cancelled" if cancelled and cancelled() else "inference-failed")
            time.sleep(0.05)
        if process.returncode != 0:
            raise AdapterFailure("inference-failed")
        # A runner must not daemonize work past its result. Kill any descendant
        # that stayed in the session after the leader exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            fd = os.open(response, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source:
                raw = source.read(4097)
            if len(raw) > 4096:
                raise ValueError
            payload = json.loads(raw)
            response.unlink()
            if payload.get("error") in _RUNNER_CODES:
                raise AdapterFailure(payload["error"])
            name = payload["result"]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise AdapterFailure("inference-failed") from None
        return name

    def _terminate(self, process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(self.term_grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
