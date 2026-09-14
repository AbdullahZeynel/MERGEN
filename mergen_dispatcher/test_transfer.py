"""Claim, transfer, delivery and publication.
Run: python -m unittest discover -s mergen_dispatcher -t ."""
import io
import logging
import os
import time
import unittest
from unittest.mock import patch

from mergen_dispatcher.control import ControlUnavailable
from mergen_dispatcher.logs import quiet_third_party
from mergen_dispatcher.test_support import (JOB_ID, TOKEN, DispatcherCase, genomics_input,
                                            genomics_result, sha256, write_ready)

INPUT = f"GET /internal/jobs/{JOB_ID}/input"


class HeartbeatAndClaim(DispatcherCase):
    def test_nothing_is_advertised_without_a_fresh_valid_executor(self):
        self.assertEqual(self.dispatcher.run_once(), "idle")
        write_ready(self.root, updated=time.time() - 600)
        self.assertEqual(self.dispatcher.run_once(), "idle")
        (self.root / "executor.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.dispatcher.run_once(), "idle")
        self.assertEqual(self.fake.calls, [])

    def test_heartbeat_then_claim_with_the_executor_capabilities(self):
        write_ready(self.root, capabilities=("genomics",))
        self.fake.claimable = False
        self.assertEqual(self.dispatcher.run_once(), "idle")
        self.assertEqual(self.fake.calls, ["POST /internal/workers/heartbeat", "POST /internal/jobs/claim"])
        self.assertEqual(self.fake.bodies, [{"capabilities": ["genomics"]}] * 2)

    def test_a_busy_executor_stays_visible_but_nothing_is_claimed(self):
        write_ready(self.root, accepting=False)
        self.assertEqual(self.dispatcher.run_once(), "busy")
        self.assertEqual(self.fake.calls, ["POST /internal/workers/heartbeat"])


class Delivery(DispatcherCase):
    def test_verified_input_reaches_the_executor_and_the_result_is_published(self):
        write_ready(self.root)
        executor = self.start_executor()
        self.assertEqual(self.dispatcher.run_once(), "published")
        executor.join(5)
        self.assertIsNone(executor.failure)
        self.assertEqual(executor.job.input.sha256, sha256(self.fake.input_bytes))
        self.assertEqual(self.fake.completed_with, executor.result)
        self.assertEqual(self.fake.failures, [])

    def test_successful_upload_removes_every_local_copy(self):
        write_ready(self.root)
        executor = self.start_executor()
        self.assertEqual(self.dispatcher.run_once(), "published")
        executor.join(5)
        self.dispatcher.spool.sweep_trash()
        self.assertSpoolEmpty()

    def test_wrong_checksum_is_reported_and_never_delivered(self):
        write_ready(self.root)
        self.fake.served_input = genomics_input(gene="OTHER1")
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertEqual(self.fake.failures, ["input-invalid"])
        self.assertSpoolEmpty()

    def test_size_limit_applies_to_the_declared_length_and_to_the_stream(self):
        write_ready(self.root)
        self.fake.content_length = 10 * 1024 * 1024
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.fake.claimable, self.fake.content_length = True, None
        self.assertEqual(self.make_dispatcher(max_input_bytes=64).run_once(), "failed")
        self.assertEqual(self.fake.failures, ["input-invalid", "input-invalid"])
        self.assertSpoolEmpty()

    def test_an_interrupted_download_is_retried_and_never_delivered_partially(self):
        write_ready(self.root)
        seen = []
        self.fake.download_cut = 1
        self.fake.download_hook = lambda: seen.append(sorted(os.listdir(self.root / "jobs")))
        self.start_executor()
        self.assertEqual(self.dispatcher.run_once(), "published")
        self.assertEqual(self.fake.count(INPUT), 2)
        self.assertEqual(seen, [[], []], "the executor could see the job before it was complete")

    def test_a_download_that_keeps_failing_is_reported_after_the_last_attempt(self):
        write_ready(self.root)
        self.fake.download_cut = 99
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertEqual(self.fake.count(INPUT), 3)
        self.assertEqual(self.fake.failures, ["internal-error"])
        self.assertSpoolEmpty()

    def test_publication_is_one_rename_after_files_and_directories_are_synced(self):
        write_ready(self.root)
        events, real_fsync, real_rename = [], os.fsync, os.rename

        def fsync(fd):
            events.append(("fsync", os.readlink(f"/proc/self/fd/{fd}")))
            real_fsync(fd)

        def rename(source, target):
            source = str(source)
            events.append(("rename", source, sorted(os.listdir(source)) if os.path.isdir(source) else None))
            real_rename(source, target)

        self.start_executor()
        with patch("os.fsync", side_effect=fsync), patch("os.rename", side_effect=rename):
            self.assertEqual(self.dispatcher.run_once(), "published")
        staging = f"{self.root}/staging/{JOB_ID}-"
        publish = next(index for index, event in enumerate(events)
                       if event[0] == "rename" and event[1].startswith(staging))
        self.assertEqual(events[publish][2], ["input.zip", "job.json"])
        before = [event[1] for event in events[:publish] if event[0] == "fsync"]
        self.assertTrue(any(path.startswith(staging) and path.endswith("/input.zip") for path in before))
        self.assertTrue(any(path.startswith(staging) and "job.json" in path for path in before))
        self.assertTrue(any(path.startswith(staging) and path.count("/") == staging.count("/")
                            for path in before), "the staging directory was not synced")
        self.assertIn(("fsync", f"{self.root}/jobs"), events[publish:])


class ExecutorVerdicts(DispatcherCase):
    def test_an_executor_failure_is_reported_with_its_code(self):
        write_ready(self.root)
        self.start_executor(verdict="fail", error_code="model-unavailable")
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertEqual(self.fake.failures, ["model-unavailable"])
        self.assertIsNone(self.fake.completed_with)

    def test_an_unreadable_status_is_never_success(self):
        write_ready(self.root)
        self.start_executor(verdict="garbage")
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertEqual(self.fake.failures, ["internal-error"])
        self.assertEqual(self.fake.upload_attempts, 0)

    def test_a_status_that_moves_backwards_is_never_success(self):
        write_ready(self.root)
        self.start_executor(verdict="backwards", work_seconds=0.1)
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertEqual(self.fake.failures, ["internal-error"])
        self.assertEqual(self.fake.upload_attempts, 0)

    def test_a_result_for_another_job_is_not_uploaded(self):
        write_ready(self.root)
        self.start_executor(result=genomics_result(job_id="d" * 32))
        self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertEqual(self.fake.failures, ["inference-failed"])
        self.assertEqual(self.fake.upload_attempts, 0)


class Logging(DispatcherCase):
    def test_logs_carry_no_token_address_payload_or_full_job_id(self):
        capture = io.StringIO()
        handler = logging.StreamHandler(capture)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        quiet_third_party()  # as in production
        self.addCleanup(root.setLevel, previous)
        self.addCleanup(root.removeHandler, handler)

        write_ready(self.root)
        self.fake.outages, self.fake.download_cut = 1, 1
        self.start_executor()
        with self.assertRaises(ControlUnavailable):
            self.dispatcher.run_once()
        self.assertEqual(self.dispatcher.run_once(), "published")

        text = capture.getvalue()
        self.assertIn(JOB_ID[:8], text, "the flow did not log at all")
        for needle in (TOKEN, "Bearer", "control.test", "http://", JOB_ID, "TEST1", "ACDEFGHIK"):
            self.assertFalse(needle in text, "a log line leaked a value it must not carry")


if __name__ == "__main__":
    unittest.main()
