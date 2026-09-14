"""Lease renewal and loss, outages, restart recovery and single publication.
Run: python -m unittest discover -s mergen_dispatcher -t ."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from mergen_dispatcher.control import ControlUnavailable, LeaseLost
from mergen_dispatcher.lease import Backoff, LeaseKeeper
from mergen_dispatcher.spool import Spool, SpoolLayoutError
from mergen_dispatcher.test_support import (JOB_ID, DispatcherCase, genomics_result, publish_job,
                                            wait_until, write_ready, write_status)


class Keeper(unittest.TestCase):
    def keeper(self, renew, lease=60, clock=time.monotonic, started=None):
        keeper = LeaseKeeper(renew, JOB_ID, lease, started=clock() if started is None else started,
                             renew_every=0.01, backoff=Backoff(0.01, 0.02, jitter=lambda: 1.0),
                             clock=clock)
        self.addCleanup(keeper.stop)
        return keeper.start()

    def test_renews_on_schedule_while_valid(self):
        calls = []
        keeper = self.keeper(lambda job_id: calls.append(job_id) or 60)
        wait_until(lambda: len(calls) >= 3)
        self.assertTrue(keeper.valid())
        self.assertEqual(set(calls), {JOB_ID})

    def test_a_refused_renewal_loses_the_lease(self):
        def refuse(job_id):
            raise LeaseLost("refused")

        keeper = self.keeper(refuse)
        wait_until(keeper.lost)
        self.assertFalse(keeper.valid())

    def test_an_outage_cannot_stretch_the_lease_past_its_deadline(self):
        now = [0.0]

        def unavailable(job_id):
            raise ControlUnavailable("down")

        keeper = self.keeper(unavailable, lease=30, clock=lambda: now[0], started=0.0)
        self.assertTrue(keeper.valid())
        now[0] = 28.0  # inside the safety margin: too late to start publishing
        self.assertFalse(keeper.valid())
        self.assertFalse(keeper.lost())
        now[0] = 31.0
        wait_until(keeper.lost)

    def test_backoff_doubles_to_a_ceiling_and_resets(self):
        backoff = Backoff(1, 8, jitter=lambda: 1.0)
        self.assertEqual([backoff.next() for _ in range(6)], [1, 2, 4, 8, 8, 8])
        backoff.reset()
        self.assertEqual(backoff.next(), 1)
        self.assertEqual(Backoff(1, 8, jitter=lambda: 0.0).next(), 0.5)


class LeaseDuringJobs(DispatcherCase):
    def test_the_lease_is_renewed_while_the_executor_works(self):
        write_ready(self.root)
        self.start_executor(work_seconds=0.2)
        self.assertEqual(self.dispatcher.run_once(), "published")
        self.assertGreaterEqual(self.fake.renewals, 3)

    def test_a_lost_lease_cancels_the_job_and_nothing_is_published(self):
        write_ready(self.root)
        executor = self.start_executor(verdict="hold",
                                       on_running=lambda: setattr(self.fake, "lease_answer", 409))
        self.assertEqual(self.dispatcher.run_once(), "lease-lost")
        executor.join(5)
        self.assertIsNone(executor.failure)
        self.assertTrue(executor.saw_cancel.is_set(), "the executor was never told")
        self.assertEqual(self.fake.upload_attempts, 0)
        self.assertEqual(self.fake.failures, [])
        self.dispatcher.spool.sweep_trash()
        self.assertSpoolEmpty()

    def test_a_retry_after_a_lost_answer_is_refused_and_not_published_twice(self):
        # The retry reaches the VPS, which refuses a second result for the job.
        write_ready(self.root)
        self.fake.lose_upload_response = True
        self.fake.lease_follows_completion = False
        executor = self.start_executor()
        self.assertEqual(self.dispatcher.run_once(), "lease-lost")
        self.assertEqual(self.fake.upload_attempts, 2)
        self.assertEqual(self.fake.completed_with, executor.result)
        self.assertEqual(self.fake.failures, [], "a failure was reported after a possible publication")

    def test_a_refused_renewal_after_a_lost_answer_stops_the_retry(self):
        # As on the real VPS: a completed job no longer renews, so the lease
        # keeper may stop the retry before a second upload is even sent.
        write_ready(self.root)
        self.fake.lose_upload_response = True
        executor = self.start_executor()
        self.assertEqual(self.dispatcher.run_once(), "lease-lost")
        self.assertIn(self.fake.upload_attempts, (1, 2))
        self.assertEqual(self.fake.completed_with, executor.result)
        self.assertEqual(self.fake.failures, [], "a failure was reported after a possible publication")


class Outages(DispatcherCase):
    def test_control_outages_back_off_exponentially_then_reset(self):
        write_ready(self.root)
        self.fake.claimable = False
        self.fake.outages = 4
        delays = []

        def sleep(seconds):
            delays.append(round(seconds, 4))
            if len(delays) >= 6:
                self.dispatcher.stop()
            return self.dispatcher._stop.is_set()

        self.dispatcher._sleep = sleep
        self.dispatcher.run()
        self.assertEqual(delays, [0.01, 0.02, 0.04, 0.05, 0.01, 0.01])
        self.assertEqual(self.fake.count("POST /internal/jobs/claim"), 2)


class Restart(DispatcherCase):
    def run_until_idle(self, dispatcher):
        def sleep(seconds):
            dispatcher.stop()
            return True

        dispatcher._sleep = sleep
        dispatcher.run()

    def test_half_built_staging_is_removed_at_start(self):
        partial = self.root / "staging" / f"{JOB_ID}-deadbeef"
        partial.mkdir()
        (partial / "input.zip").write_bytes(b"partial")
        self.run_until_idle(self.dispatcher)
        self.assertSpoolEmpty()
        self.assertEqual(self.fake.calls, [])

    def test_a_published_job_without_a_lease_is_discarded_unpublished(self):
        directory = publish_job(self.root)
        write_status(directory, "completed", result=genomics_result())
        self.fake.lease_answer = 409
        self.run_until_idle(self.dispatcher)
        self.assertEqual(self.fake.calls, [f"POST /internal/jobs/{JOB_ID}/lease"])
        self.assertEqual(self.fake.upload_attempts, 0)
        self.assertSpoolEmpty()

    def test_a_published_job_with_a_live_lease_is_resumed_and_published_once(self):
        directory = publish_job(self.root)
        result = genomics_result()
        write_status(directory, "completed", result=result)
        self.run_until_idle(self.dispatcher)
        self.assertEqual(self.fake.completed_with, result)
        self.run_until_idle(self.make_dispatcher())  # another restart
        self.assertEqual(self.fake.upload_attempts, 1)
        self.assertSpoolEmpty()

    def test_unrecognised_entries_are_discarded_without_following_links(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"x")
        (self.root / "jobs" / "not-a-job").mkdir()
        (self.root / "jobs" / ("d" * 32)).symlink_to(outside)
        self.run_until_idle(self.dispatcher)
        self.assertTrue((outside / "keep").exists())
        self.assertSpoolEmpty()


class Layout(unittest.TestCase):
    def test_an_unsafe_runtime_root_stops_the_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wide, plain, real = base / "wide", base / "plain", base / "real"
            for path, mode in ((wide, 0o2777), (plain, 0o770), (real, 0o2770)):
                path.mkdir()
                os.chmod(path, mode)
            (base / "link").symlink_to(real)
            cases = ((base / "missing", "does not exist"), (wide, "other users"),
                     (plain, "setgid"), (base / "link", "real directory"))
            for path, message in cases:
                with self.subTest(case=path.name), self.assertRaisesRegex(SpoolLayoutError, message):
                    Spool(path, 1024).prepare()
            Spool(real, 1024).prepare()
            self.assertEqual(sorted(entry.name for entry in real.iterdir()), ["jobs", "staging", "trash"])


if __name__ == "__main__":
    unittest.main()
