from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mergen_executor.adapter import AdapterFailure, ImagingJob
from mergen_executor.process_adapter import ProcessImagingAdapter
from mergen_executor.sandbox import supported


class ProcessAdapterTest(unittest.TestCase):
    def setUp(self):
        if not supported():
            self.skipTest("Linux Landlock is unavailable")
        tmp = tempfile.TemporaryDirectory(prefix="mergen-g4-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        environment = patch.dict(os.environ, env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.model = self.base / "model"
        self.venv = self.base / "venv"
        self.output = self.base / "job" / "work" / "output"
        self.input = self.base / "job" / "work" / "input"
        self.model.mkdir(); self.output.mkdir(parents=True); self.input.mkdir(parents=True)
        (self.venv / "bin").mkdir(parents=True)
        (self.venv / "bin/python").symlink_to(sys.executable)
        checkpoint = self.model / "weights.bin"
        checkpoint.write_bytes(b"weights")
        self.manifest = {"schemaVersion": 1, "modelId": "isolated-test",
                         "modelVersion": "g4-test", "runnerModule": "mergen_executor.test_model_runner",
                         "checkpoints": [{"path": "weights.bin", "size": checkpoint.stat().st_size,
                                          "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}]}
        self.write_manifest()
        self.adapter = ProcessImagingAdapter(self.model, self.venv, timeout=1, term_grace=.1)

    def write_manifest(self):
        (self.model / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def job(self, cancelled=lambda: False):
        return ImagingJob("e" * 32, "glioma", {}, self.input, self.output, 1024, cancelled)

    def test_preflight_checks_manifest_checkpoint_runner_and_landlock(self):
        self.adapter.preflight()
        self.assertEqual((self.adapter.model_id, self.adapter.model_version), ("isolated-test", "g4-test"))

    def test_wrong_checkpoint_never_becomes_available(self):
        self.manifest["checkpoints"][0]["sha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaisesRegex(AdapterFailure, "model-unavailable"):
            ProcessImagingAdapter(self.model, self.venv, timeout=1, term_grace=.1).preflight()

    def test_a_checkpoint_symlink_never_becomes_available(self):
        real = self.model / "real"
        real.mkdir()
        (real / "weights.bin").write_bytes(b"weights")
        (self.model / "linked").symlink_to(real, target_is_directory=True)
        self.manifest["checkpoints"][0]["path"] = "linked/weights.bin"
        self.write_manifest()
        with self.assertRaisesRegex(AdapterFailure, "model-unavailable"):
            ProcessImagingAdapter(self.model, self.venv, timeout=1, term_grace=.1).preflight()

    def test_runner_can_write_output_but_not_its_sibling(self):
        (self.model / "behavior").write_text("escape")
        self.adapter.preflight()
        self.assertEqual(self.adapter.run(self.job()), "result.zip")
        self.assertTrue((self.output / "result.zip").is_file())
        self.assertFalse((self.output.parent / "escaped").exists())

    def test_cancel_kills_the_whole_process_group(self):
        (self.model / "behavior").write_text("block")
        self.adapter.preflight()
        start = time.monotonic()
        with self.assertRaisesRegex(AdapterFailure, "cancelled"):
            self.adapter.run(self.job(lambda: time.monotonic() - start > .1))
        self.assertLess(time.monotonic() - start, 2)

    def test_control_environment_never_reaches_the_runner(self):
        (self.model / "behavior").write_text("env")
        self.adapter.preflight()
        with patch.dict(os.environ, {"MERGEN_CONTROL_TOKEN": "sentinel-secret"}):
            self.assertEqual(self.adapter.run(self.job()), "result.zip")

    def test_timeout_terminates_a_runner_that_ignores_sigterm(self):
        (self.model / "behavior").write_text("block")
        adapter = ProcessImagingAdapter(self.model, self.venv, timeout=.1, term_grace=.1)
        adapter.preflight()
        with self.assertRaisesRegex(AdapterFailure, "inference-failed"):
            adapter.run(self.job())

    def test_a_successful_runner_cannot_leave_a_descendant(self):
        (self.model / "behavior").write_text("descendant")
        self.adapter.preflight()
        self.assertEqual(self.adapter.run(self.job()), "result.zip")
        pid = int((self.output / "child.pid").read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                state = Path(f"/proc/{pid}/stat").read_text().split()[2]
            except (FileNotFoundError, ProcessLookupError):
                break
            if state == "Z":
                break
            time.sleep(.02)
        else:
            self.fail("the runner left a live descendant")


if __name__ == "__main__":
    unittest.main()
