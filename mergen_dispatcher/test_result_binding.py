"""The bytes the VPS completes with are the bytes the dispatcher verified.
Run: python -m unittest discover -s mergen_dispatcher -t ."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from mergen_dispatcher import runtime
from mergen_dispatcher.control import CHUNK, ControlClient, ResultChanged
from mergen_dispatcher.test_support import (JOB_ID, DispatcherCase, imaging_result, make_config,
                                            make_runtime, sha256, write_ready)
from mergen_spool.fs import lock_directory


class ReceivingServer(httpx.BaseTransport):
    """Reads the request body chunk by chunk, as a real server does.

    httpx.MockTransport reads the whole body before its handler runs, so it
    cannot show what a withheld final chunk means on the wire.
    """

    def __init__(self, answer):
        self.answer = answer
        self.received: list[tuple[dict, bytes]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = bytearray()
        try:
            for chunk in request.stream:
                body.extend(chunk)
        finally:
            self.received.append((dict(request.headers), bytes(body)))
        return self.answer(bytes(body))


class ResultBinding(DispatcherCase):
    def tamper_after_verification(self, change):
        """Run `change` on result.zip once the digest and archive checks have passed."""
        real = runtime.validate_result_archive
        target = self.root / "jobs" / JOB_ID / "result.zip"

        def validate(source, *args):
            manifest = real(source, *args)
            change(target)
            return manifest

        return patch("mergen_dispatcher.runtime.validate_result_archive", side_effect=validate)

    def test_replacing_the_path_after_verification_changes_nothing_sent(self):
        write_ready(self.root)
        executor = self.start_executor()
        swapped = imaging_result(report=b'{"status":"swapped"}')

        def replace(path):
            temporary = path.with_name(".swap")
            temporary.write_bytes(swapped)
            os.replace(temporary, path)

        with self.tamper_after_verification(replace):
            self.assertEqual(self.dispatcher.run_once(), "published")
        self.assertEqual(self.fake.completed_with, executor.result)
        self.assertNotEqual(self.fake.completed_with, swapped)

    def test_changing_the_verified_file_in_place_never_completes(self):
        write_ready(self.root)
        self.start_executor()

        def overwrite(path):
            with open(path, "r+b") as handle:
                handle.write(b"X" * 16)

        with self.tamper_after_verification(overwrite):
            self.assertEqual(self.dispatcher.run_once(), "failed")
        self.assertIsNone(self.fake.completed_with)
        self.assertEqual(self.fake.upload_attempts, 0, "a complete body reached the VPS")
        self.assertEqual(self.fake.failures, ["internal-error"])

    def test_the_job_directory_stays_locked_during_the_upload(self):
        write_ready(self.root)
        observed = []

        def probe():
            fd = lock_directory(self.root / "jobs" / JOB_ID, blocking=False)
            observed.append(fd is None)
            if fd is not None:
                os.close(fd)

        self.fake.upload_hook = probe
        self.start_executor()
        self.assertEqual(self.dispatcher.run_once(), "published")
        self.assertEqual(observed, [True], "the executor could have changed the job during the upload")


class UploadStream(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-upload-test-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.config = make_config(make_runtime(self.base))

    def client(self, answer) -> ControlClient:
        self.server = ReceivingServer(answer)
        client = ControlClient(self.config, self.server)
        self.addCleanup(client.close)
        return client

    def test_changed_bytes_never_leave_as_a_complete_body(self):
        payload = os.urandom(2 * CHUNK + CHUNK // 2)
        path = self.base / "result.zip"
        path.write_bytes(payload)
        client = self.client(lambda body: httpx.Response(200))
        with open(path, "rb", buffering=0) as handle, self.assertRaises(ResultChanged):
            client.upload(JOB_ID, handle, len(payload), "0" * 64, lambda: True)
        self.assertEqual(len(self.server.received[0][1]), 2 * CHUNK, "the final chunk must be withheld")

    def test_the_declared_digest_travels_with_the_body(self):
        payload = imaging_result()
        path = self.base / "result.zip"
        path.write_bytes(payload)
        client = self.client(lambda body: httpx.Response(
            200, json={"status": "completed", "sha256": sha256(body)}))
        with open(path, "rb", buffering=0) as handle:
            handle.read()  # the caller's position must not matter
            client.upload(JOB_ID, handle, len(payload), sha256(payload), lambda: True)
        headers, body = self.server.received[0]
        self.assertEqual(body, payload)
        self.assertEqual(headers["x-mergen-result-sha256"], sha256(payload))
        self.assertEqual(headers["content-length"], str(len(payload)))


if __name__ == "__main__":
    unittest.main()
