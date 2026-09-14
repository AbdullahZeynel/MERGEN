"""Spool contract v1. Run: python -m unittest discover -s mergen_spool -t ."""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from mergen_spool import contract
from mergen_spool.fs import create_marker, lock_directory, read_json, remove_unlocked, write_json_atomic

REPO = Path(__file__).resolve().parents[1]
JOB_ID = "a" * 32
DIGEST = "b" * 64


def job_document(**overrides):
    document = {
        "schemaVersion": 1, "kind": "mergen-spool-job", "jobId": JOB_ID,
        "module": "imaging", "disease": "glioma",
        "input": {"path": "input.zip", "sha256": DIGEST, "size": 10},
        "maxResultBytes": 1024, "publishedAt": 1,
    }
    return {**document, **overrides}


def status_document(state, **overrides):
    document = {"schemaVersion": 1, "kind": "mergen-spool-status", "jobId": JOB_ID,
                "state": state, "updatedAt": 1}
    if state == "completed":
        document["result"] = {"path": "result.zip", "sha256": DIGEST, "size": 5}
    if state == "failed":
        document["errorCode"] = "inference-failed"
    return {**document, **overrides}


def ready_document(**overrides):
    document = {"schemaVersion": 1, "kind": "mergen-executor-ready",
                "capabilities": ["imaging"], "acceptingJobs": True, "updatedAt": 1}
    return {**document, **overrides}


class Documents(unittest.TestCase):
    def test_valid_documents_parse(self):
        contract.SpoolJob.model_validate(job_document())
        for state in ("accepted", "running", "completed", "failed"):
            contract.SpoolStatus.model_validate(status_document(state))
        contract.ExecutorReady.model_validate(ready_document())

    def test_unknown_keys_and_loose_types_are_rejected(self):
        for overrides in ({"extra": True}, {"schemaVersion": 2}, {"maxResultBytes": "1024"},
                          {"publishedAt": 1.0}, {"jobId": "A" * 32}, {"module": "radiology"},
                          {"input": {"path": "../input.zip", "sha256": DIGEST, "size": 1}}):
            with self.subTest(overrides=sorted(overrides)), self.assertRaises(ValidationError):
                contract.SpoolJob.model_validate(job_document(**overrides))

    def test_terminal_fields_must_match_the_state(self):
        result = {"path": "result.zip", "sha256": DIGEST, "size": 5}
        for document in (status_document("completed", result=None),
                         status_document("running", result=result),
                         status_document("failed", errorCode=None),
                         status_document("failed", errorCode="gpu-melted"),
                         status_document("accepted", errorCode="internal-error"),
                         status_document("completed", result={**result, "path": "other.zip"}),
                         status_document("finished")):
            with self.subTest(state=document["state"]), self.assertRaises(ValidationError):
                contract.SpoolStatus.model_validate(document)

    def test_executor_capabilities_are_known_unique_and_typed(self):
        for overrides in ({"capabilities": ["imaging", "imaging"]},
                          {"capabilities": ["radiology"]}, {"acceptingJobs": "true"},
                          {"acceptingJobs": 1}):
            with self.subTest(overrides=sorted(overrides)), self.assertRaises(ValidationError):
                contract.ExecutorReady.model_validate(ready_document(**overrides))

    def test_a_poller_may_skip_forward_but_never_go_back(self):
        self.assertTrue(contract.advances(None, "completed"))
        self.assertTrue(contract.advances("accepted", "completed"))
        self.assertTrue(contract.advances("running", "running"))
        self.assertTrue(contract.advances("failed", "failed"))
        self.assertFalse(contract.advances("running", "accepted"))
        self.assertFalse(contract.advances("completed", "failed"))
        self.assertFalse(contract.advances("failed", "running"))

    def test_documented_examples_match_the_contract(self):
        examples = REPO / "docs" / "contracts"
        contract.SpoolJob.model_validate_json((examples / "gpu-spool-job.v1.example.json").read_bytes())
        contract.SpoolStatus.model_validate_json(
            (examples / "gpu-spool-status.v1.example.json").read_bytes())
        contract.ExecutorReady.model_validate_json(
            (examples / "gpu-executor-ready.v1.example.json").read_bytes())


class FileSystem(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-spool-test-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.target = self.dir / "status.json"

    def test_atomic_write_replaces_without_leaving_temporaries(self):
        write_json_atomic(self.target, {"a": 1})
        write_json_atomic(self.target, {"a": 2})
        self.assertEqual(read_json(self.target), {"a": 2})
        self.assertEqual([path.name for path in self.dir.iterdir()], ["status.json"])
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode) & 0o007, 0)

    def test_file_is_fsynced_before_the_rename_and_the_directory_after(self):
        events, real_fsync, real_replace = [], os.fsync, os.replace

        def fsync(fd):
            events.append("fsync-dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync-file")
            real_fsync(fd)

        def replace(source, target):
            events.append("rename")
            real_replace(source, target)

        with patch("os.fsync", side_effect=fsync), patch("os.replace", side_effect=replace):
            write_json_atomic(self.target, {"a": 1})
        self.assertEqual(events, ["fsync-file", "rename", "fsync-dir"])

    def test_failed_rename_keeps_the_old_file_and_removes_the_temporary(self):
        write_json_atomic(self.target, {"a": 1})
        with patch("os.replace", side_effect=OSError("simulated")), self.assertRaises(OSError):
            write_json_atomic(self.target, {"a": 2})
        self.assertEqual(read_json(self.target), {"a": 1})
        self.assertEqual([path.name for path in self.dir.iterdir()], ["status.json"])

    def test_read_refuses_symlinks_fifos_and_oversized_files(self):
        write_json_atomic(self.target, {"a": 1})
        (self.dir / "link.json").symlink_to(self.target)
        with self.assertRaises(OSError):
            read_json(self.dir / "link.json")
        os.mkfifo(self.dir / "fifo.json")
        with self.assertRaises(ValueError):
            read_json(self.dir / "fifo.json")
        (self.dir / "big.json").write_text("[" + "0," * 40000 + "0]", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_json(self.dir / "big.json")

    def test_marker_is_created_once(self):
        self.assertTrue(create_marker(self.dir / "cancel"))
        self.assertFalse(create_marker(self.dir / "cancel"))

    def test_a_locked_directory_is_not_removed(self):
        job = self.dir / "job"
        job.mkdir()
        (job / "input.zip").write_bytes(b"x")
        holder = lock_directory(job, blocking=False)
        try:
            self.assertFalse(remove_unlocked(job))
            self.assertTrue((job / "input.zip").exists())
        finally:
            os.close(holder)
        self.assertTrue(remove_unlocked(job))
        self.assertFalse(job.exists())

    def test_a_symlinked_job_directory_is_never_followed(self):
        real = self.dir / "real"
        real.mkdir()
        (real / "keep").write_bytes(b"x")
        (self.dir / "link").symlink_to(real)
        with self.assertRaises(OSError):
            remove_unlocked(self.dir / "link")
        self.assertTrue((real / "keep").exists())


if __name__ == "__main__":
    unittest.main()
