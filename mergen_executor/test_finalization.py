"""The finalization gate from the executor's side: a cancel and the verdict are
ordered whichever comes first, and the gate is free while an adapter runs. The
cancels here are the dispatcher's own (mergen_dispatcher.spool.Spool.cancel),
so both halves of the protocol run together.
Run: python -m unittest discover -s mergen_executor -t ."""
import fcntl
import os
import threading
import unittest
from unittest.mock import patch

from mergen_dispatcher.spool import Spool
from mergen_executor import runtime
from mergen_executor.jobdir import LockedJob
from mergen_executor.test_support import (JOB_ID, ExecutorCase, FakeImagingAdapter, publish_job,
                                          recorded_states, status_of)
from mergen_spool import contract

WITHDRAWN = ["cancel", "gate", "input.zip", "job.json", "status.json"]


class GateCase(ExecutorCase):
    def setUp(self):
        super().setUp()
        self.directory = publish_job(self.root)
        self.dispatcher = Spool(self.root, max_result_bytes=1024 * 1024)

    def cancel(self, wait: float = 1.0) -> bool:
        """What the dispatcher does once it will not upload this job's result."""
        return self.dispatcher.cancel(self.directory, wait=wait)

    def assert_cancelled_without_a_result(self) -> None:
        status = status_of(self.root)
        self.assertEqual((status["state"], status.get("errorCode"), status.get("result")),
                         ("failed", "cancelled", None))
        self.assertEqual(sorted(os.listdir(self.directory)), WITHDRAWN)


class CancelFirst(GateCase):
    def test_a_cancel_after_the_result_is_renamed_withdraws_it(self):
        # The reproduced race: result.zip is in place, `completed` is not written
        # yet. Another look for cancel would only narrow this window; the gate
        # is what makes a cancel from here on visible to the verdict.
        real = LockedJob.publish_result

        def publish_then_cancel(job, *args, **kwargs):
            result = real(job, *args, **kwargs)
            self.assertTrue((self.directory / contract.RESULT_FILE).exists())
            self.assertTrue(self.cancel())
            return result

        states, recorder = recorded_states()
        with recorder, patch.object(LockedJob, "publish_result", autospec=True,
                                    side_effect=publish_then_cancel):
            self.assertEqual(self.started().tick(), "cancelled")
        self.assertEqual(states, ["accepted", "running", "failed"])
        self.assert_cancelled_without_a_result()

    def test_a_cancel_just_before_the_verdict_is_seen_by_it(self):
        real = runtime.finalize

        def cancel_then_finalize(job, state, **fields):
            self.assertTrue(self.cancel())
            return real(job, state, **fields)

        with patch("mergen_executor.runtime.finalize", side_effect=cancel_then_finalize):
            self.assertEqual(self.started().tick(), "cancelled")
        self.assert_cancelled_without_a_result()

    def test_an_interrupted_run_that_was_cancelled_is_recorded_as_cancelled(self):
        job = LockedJob.acquire(self.root / contract.JOBS_DIR, JOB_ID)
        job.advance("accepted")
        job.advance("running")
        job.close()
        (self.directory / contract.RESULT_FILE).write_bytes(b"never announced")
        self.assertTrue(self.cancel())
        self.started()
        self.assert_cancelled_without_a_result()


class VerdictFirst(GateCase):
    def test_a_cancel_cannot_land_between_the_last_check_and_the_verdict(self):
        real, attempts = LockedJob.advance, []

        def advance(job, state, **fields):
            if state == "completed":
                # The executor has made its last check and holds the gate.
                with self.assertLogs("mergen.dispatcher", "WARNING"):
                    attempts.append(self.cancel(wait=0.05))
                self.assertFalse((self.directory / contract.CANCEL_FILE).exists())
            return real(job, state, **fields)

        with patch.object(LockedJob, "advance", autospec=True, side_effect=advance):
            self.assertEqual(self.started().tick(), "completed")
        self.assertEqual(attempts, [False])
        self.assertEqual(status_of(self.root)["state"], "completed")

    def test_a_cancel_after_the_verdict_leaves_it_standing(self):
        # The dispatcher cancels only a job whose result it will not upload and
        # then discards it (mergen_dispatcher/test_lease_loss.py); here the late
        # marker must not turn a written verdict into another one.
        executor = self.started()
        self.assertEqual(executor.tick(), "completed")
        before = (self.directory / contract.STATUS_FILE).read_bytes()
        self.assertTrue(self.cancel())
        self.assertEqual(executor.tick(), "idle")
        self.assertEqual(self.started().tick(), "idle")
        self.assertEqual((self.directory / contract.STATUS_FILE).read_bytes(), before)
        self.assertTrue((self.directory / contract.RESULT_FILE).exists())


class GateAndAdapter(GateCase):
    def test_the_gate_is_free_while_the_adapter_runs(self):
        adapter = FakeImagingAdapter("wait-cancel")
        executor = self.started(adapter=adapter)
        outcomes = []
        worker = threading.Thread(target=lambda: outcomes.append(executor.tick()))
        worker.start()
        self.addCleanup(worker.join, 5)
        self.assertTrue(adapter.started.wait(5))
        # One attempt without waiting: a gate held during the run would refuse it.
        self.assertTrue(self.cancel(wait=0), "the gate was held while the adapter ran")
        worker.join(5)
        self.assertEqual(outcomes, ["cancelled"])
        self.assert_cancelled_without_a_result()


class UnusableGate(ExecutorCase):
    def test_a_job_without_a_usable_gate_fails_before_it_runs(self):
        valid = self.base / "valid-gate"
        valid.write_bytes(contract.GATE_CONTENT)

        def missing(gate):
            gate.unlink()

        def linked(gate):
            gate.unlink()
            gate.symlink_to(valid)

        def another_version(gate):
            gate.write_bytes(b"mergen-spool-gate 2\n")

        def a_directory(gate):
            gate.unlink()
            gate.mkdir()

        executor = self.started()
        for number, spoil in enumerate((missing, linked, another_version, a_directory), start=1):
            with self.subTest(case=spoil.__name__):
                job_id = f"{number:032x}"
                spoil(publish_job(self.root, job_id=job_id) / contract.GATE_FILE)
                self.assertEqual(executor.tick(), "failed")
                status = status_of(self.root, job_id)
                self.assertEqual((status["state"], status["errorCode"]), ("failed", "internal-error"))
        self.assertEqual(self.adapter.runs, [])

    def test_a_gate_held_past_the_wait_fails_the_job_instead_of_completing_it(self):
        directory = publish_job(self.root)
        holder = os.open(directory / contract.GATE_FILE, os.O_RDONLY)
        try:
            fcntl.flock(holder, fcntl.LOCK_EX)
            with patch("mergen_executor.finalize.GATE_WAIT_SECONDS", 0.05):
                self.assertEqual(self.started().tick(), "failed")
        finally:
            os.close(holder)
        status = status_of(self.root)
        self.assertEqual((status["state"], status["errorCode"]), ("failed", "internal-error"))
        self.assertEqual(sorted(os.listdir(directory)), ["gate", "input.zip", "job.json", "status.json"])
        self.assertEqual(len(self.adapter.runs), 1)


if __name__ == "__main__":
    unittest.main()
