"""After a lost lease nothing reaches the VPS, and a cancel is ordered against
the executor's verdict through the job's gate.
Run: python -m unittest discover -s mergen_dispatcher -t ."""
import os
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from mergen_dispatcher.control import CHUNK, ControlClient, LeaseLost
from mergen_dispatcher.lease import LeaseKeeper
from mergen_dispatcher.test_result_binding import ReceivingServer
from mergen_dispatcher.test_support import (JOB_ID, DispatcherCase, FakeExecutor, make_config, publish_job,
                                            sha256, wait_until, write_ready)
from mergen_spool.gate import finalization_gate


class LingeringExecutor(FakeExecutor):
    """Completes, then keeps the job lock until released, as a slow executor
    would; the test decides when the dispatcher may try to publish."""

    def __init__(self, root, *, on_complete, release, **kwargs):
        super().__init__(root, **kwargs)
        self.on_complete, self.release = on_complete, release

    def _answer(self, directory, fd):
        super()._answer(directory, fd)
        self.on_complete()
        self.release.wait(5)


class NothingAfterLeaseLoss(DispatcherCase):
    def test_a_completed_result_is_not_uploaded_once_the_lease_is_lost(self):
        write_ready(self.root)
        keepers, real_start = [], LeaseKeeper.start

        def record(keeper):
            keepers.append(keeper)
            return real_start(keeper)

        release = threading.Event()
        executor = LingeringExecutor(self.root, release=release,
                                     on_complete=lambda: setattr(self.fake, "lease_answer", 409))
        executor.start()
        self.addCleanup(executor.join, 5)
        outcome = []
        with patch.object(LeaseKeeper, "start", record):
            worker = threading.Thread(target=lambda: outcome.append(self.dispatcher.run_once()))
            worker.start()
            self.addCleanup(worker.join, 5)
            wait_until(lambda: keepers and keepers[0].lost())
            release.set()  # completed is on disk, the lease is already gone
            worker.join(5)
        self.assertEqual(outcome, ["lease-lost"])
        self.assertEqual(self.fake.upload_attempts, 0, "a result was sent after the lease was lost")
        self.assertIsNone(self.fake.completed_with)
        self.assertEqual(self.fake.failures, [])

    def test_the_upload_stops_the_moment_the_lease_is_lost(self):
        payload = os.urandom(3 * CHUNK)
        path = self.base / "result.zip"
        path.write_bytes(payload)
        server = ReceivingServer(lambda body: httpx.Response(
            200, json={"status": "completed", "sha256": sha256(body)}))
        client = ControlClient(make_config(self.root), server)
        self.addCleanup(client.close)
        answers = iter([True])  # valid for the first chunk only
        with open(path, "rb", buffering=0) as handle, self.assertRaises(LeaseLost):
            client.upload(JOB_ID, handle, len(payload), sha256(payload), lambda: next(answers, False))
        self.assertLess(len(server.received[0][1]), len(payload), "a complete body left after the loss")


class CancelUnderTheGate(DispatcherCase):
    def hold_gate(self, directory):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        return finalization_gate(fd, timeout=1)

    def test_the_marker_waits_while_the_executor_writes_its_verdict(self):
        directory = publish_job(self.root)
        written = []
        with self.hold_gate(directory):
            worker = threading.Thread(target=lambda: written.append(self.dispatcher.spool.cancel(directory)))
            worker.start()
            self.addCleanup(worker.join, 5)
            time.sleep(0.1)
            self.assertFalse((directory / "cancel").exists(), "cancel landed inside the executor's step")
        worker.join(5)
        self.assertEqual(written, [True])
        self.assertTrue((directory / "cancel").exists())

    def test_a_gate_that_stays_busy_skips_the_marker_and_uploads_nothing(self):
        directory = publish_job(self.root)
        with self.hold_gate(directory), self.assertLogs("mergen.dispatcher", level="WARNING"):
            self.assertFalse(self.dispatcher.spool.cancel(directory, wait=0.05))
        self.assertFalse((directory / "cancel").exists())
        self.assertEqual(self.fake.upload_attempts, 0)

    def test_a_job_without_a_gate_is_still_cancelled(self):
        directory = publish_job(self.root)
        (directory / "gate").unlink()
        self.assertTrue(self.dispatcher.spool.cancel(directory))
        self.assertTrue((directory / "cancel").exists())


if __name__ == "__main__":
    unittest.main()
