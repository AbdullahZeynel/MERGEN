"""Readiness: what executor.json says, and when.
Run: python -m unittest discover -s mergen_executor -t ."""
import os
import stat
import threading
import time
import unittest
from unittest.mock import patch

from mergen_executor.adapter import AdapterFailure
from mergen_executor.test_support import (ExecutorCase, FakeImagingAdapter, publish_job, ready_of,
                                          status_of)
from mergen_spool.fs import write_json_atomic


class Readiness(ExecutorCase):
    def test_only_the_imaging_capability_is_advertised(self):
        executor = self.started()
        self.assertEqual(ready_of(self.root)["capabilities"], ["imaging"])
        self.assertEqual(executor.tick(), "idle")
        ready = ready_of(self.root)
        self.assertEqual((ready["capabilities"], ready["acceptingJobs"]), (["imaging"], True))

    def test_without_a_working_adapter_nothing_is_advertised(self):
        adapters = {"none": None,
                    "preflight failure": FakeImagingAdapter(
                        preflight_error=AdapterFailure("model-unavailable")),
                    "preflight exception": FakeImagingAdapter(preflight_error=RuntimeError("weights"))}
        for label, adapter in adapters.items():
            with self.subTest(adapter=label):
                publish_job(self.root, job_id=f"{len(label):032x}")
                executor = self.started(adapter=adapter)
                self.assertEqual(executor.tick(), "no-adapter")
                ready = ready_of(self.root)
                self.assertEqual((ready["capabilities"], ready["acceptingJobs"]), ([], False))
        self.assertEqual(self.adapter.runs, [])

    def test_a_stale_accepting_document_is_withdrawn_at_start(self):
        write_json_atomic(self.root / "executor.json", {
            "schemaVersion": 1, "kind": "mergen-executor-ready", "capabilities": ["imaging"],
            "acceptingJobs": True, "updatedAt": 1})
        leftover = self.root / ".executor.json.0badc0de.tmp"
        leftover.write_text("{", encoding="utf-8")
        self.started()
        ready = ready_of(self.root)
        self.assertFalse(ready["acceptingJobs"])
        self.assertGreater(ready["updatedAt"], 1)
        self.assertFalse(leftover.exists())

    def test_readiness_is_written_atomically(self):
        executor = self.started()
        events, real_fsync, real_replace = [], os.fsync, os.replace

        def fsync(fd):
            events.append(("fsync", "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"))
            real_fsync(fd)

        def replace(source, target, *args, **kwargs):
            events.append(("replace", os.path.basename(target)))
            real_replace(source, target, *args, **kwargs)

        with patch("os.fsync", side_effect=fsync), patch("os.replace", side_effect=replace):
            executor.publish_ready(accepting=True, force=True)
        self.assertEqual(events, [("fsync", "file"), ("replace", "executor.json"), ("fsync", "directory")])
        self.assertEqual([path.name for path in self.root.iterdir() if path.name.startswith(".")], [])

    def test_pause_withdraws_acceptance_and_resume_restores_it(self):
        publish_job(self.root)
        executor = self.started()
        (self.state / "pause").touch()
        self.assertEqual(executor.tick(), "paused")
        self.assertFalse(ready_of(self.root)["acceptingJobs"])
        self.assertIsNone(status_of(self.root))
        (self.state / "pause").unlink()
        self.assertEqual(executor.tick(), "completed")
        self.assertEqual(len(self.adapter.runs), 1)

    def test_a_busy_gpu_withdraws_acceptance_and_starts_nothing(self):
        publish_job(self.root)
        executor = self.started()
        self.gpu.available = False
        self.assertEqual(executor.tick(), "gpu-busy")
        self.assertFalse(ready_of(self.root)["acceptingJobs"])
        self.assertIsNone(status_of(self.root))
        self.assertEqual(self.adapter.runs, [])
        self.gpu.available = True
        self.assertEqual(executor.tick(), "completed")

    def test_readiness_stays_fresh_but_closed_while_a_long_job_runs(self):
        publish_job(self.root)
        adapter = FakeImagingAdapter("block")
        executor = self.started(adapter=adapter, ready_refresh_seconds=0.02)
        worker = threading.Thread(target=executor.tick)
        worker.start()
        self.addCleanup(worker.join, 5)
        self.assertTrue(adapter.started.wait(5))
        inodes, deadline = set(), time.monotonic() + 0.3
        while time.monotonic() < deadline:
            inodes.add(os.stat(self.root / "executor.json").st_ino)
            self.assertFalse(ready_of(self.root)["acceptingJobs"])
            time.sleep(0.01)
        adapter.release.set()
        worker.join(5)
        self.assertGreaterEqual(len(inodes), 3, "executor.json was not refreshed during the job")
        self.assertEqual(status_of(self.root)["state"], "completed")


if __name__ == "__main__":
    unittest.main()
