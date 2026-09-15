"""Cancellation, the single-inference rule, restart recovery, atomic
publication, log hygiene and package isolation.
Run: python -m unittest discover -s mergen_executor -t ."""
import ast
import io
import logging
import os
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from mergen_executor import jobdir
from mergen_executor.jobdir import LockedJob
from mergen_executor.test_support import (JOB_ID, MARKER, ExecutorCase, FakeImagingAdapter, imaging_input,
                                          publish_job, ready_of, result_zip, status_of)
from mergen_spool.fs import create_marker, lock_directory

PACKAGE = Path(__file__).resolve().parent


class Cancellation(ExecutorCase):
    def test_a_job_cancelled_before_it_starts_is_left_alone(self):
        directory = publish_job(self.root)
        create_marker(directory / "cancel")
        executor = self.started()
        self.assertEqual(executor.tick(), "idle")
        self.assertIsNone(status_of(self.root))
        self.assertEqual(executor.tick(), "idle")
        self.assertEqual(self.adapter.runs, [])

    def test_a_cancel_during_the_run_publishes_nothing(self):
        directory = publish_job(self.root)
        adapter = FakeImagingAdapter("wait-cancel")
        executor = self.started(adapter=adapter)
        outcomes = []
        worker = threading.Thread(target=lambda: outcomes.append(executor.tick()))
        worker.start()
        self.addCleanup(worker.join, 5)
        self.assertTrue(adapter.started.wait(5))
        create_marker(directory / "cancel")
        worker.join(5)
        self.assertEqual(outcomes, ["cancelled"])
        status = status_of(self.root)
        self.assertEqual((status["state"], status["errorCode"]), ("failed", "cancelled"))
        self.assertEqual(sorted(os.listdir(directory)), ["cancel", "input.zip", "job.json", "status.json"])

    def test_a_cancel_racing_the_publication_publishes_nothing(self):
        directory = publish_job(self.root)
        real = jobdir.validate_result_archive

        def validate(*args):
            manifest = real(*args)  # the result is valid; the cancel arrives now
            create_marker(directory / "cancel")
            return manifest

        with patch("mergen_executor.jobdir.validate_result_archive", side_effect=validate):
            self.assertEqual(self.started().tick(), "cancelled")
        self.assertEqual(sorted(os.listdir(directory)), ["cancel", "input.zip", "job.json", "status.json"])


class SingleInference(ExecutorCase):
    def test_two_executors_never_run_inference_at_the_same_time(self):
        publish_job(self.root, job_id="1" * 32)
        publish_job(self.root, job_id="2" * 32)
        blocking, other = FakeImagingAdapter("block"), FakeImagingAdapter()
        first, second = self.started(adapter=blocking), self.started(adapter=other)
        worker = threading.Thread(target=first.tick)
        worker.start()
        self.addCleanup(worker.join, 5)
        self.assertTrue(blocking.started.wait(5))
        self.assertEqual(second.tick(), "gpu-locked")
        self.assertEqual(other.runs, [])
        self.assertFalse(ready_of(self.root)["acceptingJobs"])
        blocking.release.set()
        worker.join(5)
        self.assertEqual(second.tick(), "completed")
        self.assertEqual((len(blocking.runs), len(other.runs)), (1, 1))
        self.assertEqual({blocking.runs[0].job_id, other.runs[0].job_id}, {"1" * 32, "2" * 32})

    def test_a_job_directory_locked_elsewhere_is_not_touched(self):
        directory = publish_job(self.root)
        holder = lock_directory(directory, blocking=False)  # e.g. the dispatcher verifying
        executor = self.started()
        try:
            self.assertEqual(executor.tick(), "idle")
            self.assertIsNone(status_of(self.root))
        finally:
            os.close(holder)
        self.assertEqual(executor.tick(), "completed")


class Recovery(ExecutorCase):
    def test_an_interrupted_run_is_failed_and_a_half_result_never_counts(self):
        directory = publish_job(self.root)
        job = LockedJob.acquire(self.root / "jobs", JOB_ID)
        job.advance("accepted")
        job.advance("running")
        job.close()
        (directory / "work" / "output").mkdir(parents=True)
        (directory / "work" / "output" / "result.zip").write_bytes(result_zip())
        (directory / "result.zip").write_bytes(result_zip()[:100])
        (directory / ".result.zip.0badc0de.tmp").write_bytes(b"partial")
        (directory / ".status.json.0badc0de.tmp").write_bytes(b"{")
        executor = self.started()
        status = status_of(self.root)
        self.assertEqual((status["state"], status["errorCode"]), ("failed", "internal-error"))
        self.assertEqual(sorted(os.listdir(directory)), ["input.zip", "job.json", "status.json"])
        self.assertEqual(executor.tick(), "idle")
        self.assertEqual(self.adapter.runs, [])

    def test_a_completed_result_stays_and_an_unreadable_status_is_left_alone(self):
        done = publish_job(self.root, job_id="1" * 32)
        self.assertEqual(self.started().tick(), "completed")
        (done / "work").mkdir()
        odd = publish_job(self.root, job_id="2" * 32)
        (odd / "status.json").write_text("{not json", encoding="utf-8")
        restarted = self.started()
        self.assertTrue((done / "result.zip").exists())
        self.assertFalse((done / "work").exists())
        self.assertEqual((odd / "status.json").read_text(encoding="utf-8"), "{not json")
        self.assertEqual(restarted.tick(), "idle")
        self.assertEqual(len(self.adapter.runs), 1)


class AtomicPublication(ExecutorCase):
    def test_the_result_is_synced_and_renamed_before_completed_is_written(self):
        publish_job(self.root)
        executor = self.started()
        events, real_fsync, real_rename, real_replace = [], os.fsync, os.rename, os.replace

        def fsync(fd):
            events.append(("fsync", os.path.basename(os.readlink(f"/proc/self/fd/{fd}"))))
            real_fsync(fd)

        def rename(source, target, *args, **kwargs):
            events.append(("rename", os.fspath(source), os.fspath(target)))
            real_rename(source, target, *args, **kwargs)

        def replace(source, target, *args, **kwargs):
            events.append(("replace", os.fspath(target)))
            real_replace(source, target, *args, **kwargs)

        with patch("os.fsync", side_effect=fsync), patch("os.rename", side_effect=rename), \
                patch("os.replace", side_effect=replace):
            self.assertEqual(executor.tick(), "completed")
        publish = next(index for index, event in enumerate(events)
                       if event[0] == "rename" and event[2] == "result.zip")
        temporary = events[publish][1]
        self.assertRegex(temporary, r"^\.result\.zip\.[0-9a-f]{8}\.tmp$")
        self.assertIn(("fsync", temporary), events[:publish], "the result was not synced before the rename")
        self.assertEqual(events[publish + 1], ("fsync", JOB_ID), "the directory was not synced after it")
        last_status = max(index for index, event in enumerate(events) if event == ("replace", "status.json"))
        self.assertGreater(last_status, publish, "completed was written before the result existed")


class LogHygiene(ExecutorCase):
    def test_logs_carry_no_content_manifest_detail_or_full_job_id(self):
        capture = io.StringIO()
        handler = logging.StreamHandler(capture)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.setLevel, previous)
        self.addCleanup(root.removeHandler, handler)

        publish_job(self.root, job_id="1" * 32)
        publish_job(self.root, job_id="2" * 32, payload=imaging_input(extra=[("../escape.nii.gz", MARKER)]))
        publish_job(self.root, job_id="3" * 32)
        executor = self.started()
        self.assertEqual(executor.tick(), "completed")
        self.assertEqual(executor.tick(), "failed")
        self.adapter.behaviour = "raise"
        self.assertEqual(executor.tick(), "failed")

        text = capture.getvalue()
        self.assertIn("11111111", text, "the flow did not log at all")
        self.assertIn("RuntimeError", text)
        for needle in (MARKER.decode(), "volumes/", ".nii", "input.json", "escape", "1" * 32, "2" * 32,
                       "3" * 32, str(self.base)):
            self.assertFalse(needle in text, "a log line carried something it must not")


class Isolation(unittest.TestCase):
    FORBIDDEN = {"httpx", "requests", "urllib", "http", "socket", "ssl", "subprocess",
                 "multiprocessing", "mergen_dispatcher", "torch", "monai", "nnunetv2"}

    def test_the_package_imports_no_network_process_or_model_code(self):
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                else:
                    continue
                for module in modules:
                    with self.subTest(file=path.name, module=module):
                        self.assertNotIn(module.split(".")[0], self.FORBIDDEN)

    def test_the_package_never_names_a_vps_setting(self):
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            for name in ("MERGEN_CONTROL_URL", "MERGEN_WORKER_TOKEN", "MERGEN_WORKER_ID", "dispatcher.env"):
                with self.subTest(file=path.name, name=name):
                    self.assertNotIn(name, text)


if __name__ == "__main__":
    unittest.main()
