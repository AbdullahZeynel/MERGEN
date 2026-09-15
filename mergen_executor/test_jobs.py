"""One job from acceptance to verdict: validation, transitions and error codes.
Run: python -m unittest discover -s mergen_executor -t ."""
import json
import os
import stat
import unittest
import warnings
import zipfile
from unittest.mock import patch

from mergen_executor import jobdir
from mergen_executor.jobdir import LockedJob, StatusProblem
from mergen_executor.test_support import (JOB_ID, MARKER, ExecutorCase, FakeImagingAdapter, imaging_input,
                                          imaging_manifest, publish_job, result_zip, sha256, status_of,
                                          zip_bytes)
from mergen_spool import contract

OWNED_BY_DISPATCHER = ("job.json", "input.zip")


def recorded_states():
    """Patch the status writer so that it also records each state it writes."""
    states, real = [], jobdir.write_json_atomic_at

    def write(fd, name, document):
        if name == contract.STATUS_FILE:
            states.append(document["state"])
        real(fd, name, document)

    return states, patch("mergen_executor.jobdir.write_json_atomic_at", side_effect=write)


def job_id(number: int) -> str:
    return f"{number:032x}"


class HappyPath(ExecutorCase):
    def test_a_valid_job_moves_accepted_running_completed(self):
        directory = publish_job(self.root)
        before = {name: (sha256((directory / name).read_bytes()), os.stat(directory / name).st_mtime_ns)
                  for name in OWNED_BY_DISPATCHER}
        states, recorder = recorded_states()
        executor = self.started()
        with recorder:
            self.assertEqual(executor.tick(), "completed")
        self.assertEqual(states, ["accepted", "running", "completed"])
        result = (directory / "result.zip").read_bytes()
        self.assertEqual(status_of(self.root)["result"],
                         {"path": "result.zip", "sha256": sha256(result), "size": len(result)})
        self.assertEqual(sorted(os.listdir(directory)), ["input.zip", "job.json", "result.zip", "status.json"])
        after = {name: (sha256((directory / name).read_bytes()), os.stat(directory / name).st_mtime_ns)
                 for name in OWNED_BY_DISPATCHER}
        self.assertEqual(before, after, "the executor changed a file the dispatcher owns")

    def test_the_adapter_gets_only_job_specific_directories(self):
        publish_job(self.root)
        self.started().tick()
        job, work = self.adapter.runs[0], self.job_dir() / "work"
        self.assertEqual((job.input_dir, job.output_dir), (work / "input", work / "output"))
        self.assertEqual(set(job.volumes), {"T1", "T1CE", "T2", "FLAIR"})
        self.assertTrue(all(path.is_relative_to(job.input_dir) for path in job.volumes.values()))
        self.assertEqual((job.job_id, job.disease, job.max_result_bytes), (JOB_ID, "glioma", 1024 * 1024))
        self.assertFalse(work.exists(), "work/ outlived the verdict")


class Rejections(ExecutorCase):
    def verdicts(self, jobs: dict[str, dict], **config) -> dict[str, tuple[str, str]]:
        executor = self.started(**config)
        for _ in jobs:
            executor.tick()
        found = {}
        for label, identifier in jobs.items():
            status = status_of(self.root, identifier["id"])
            found[label] = (status["state"], status.get("errorCode"))
        return found

    def test_an_invalid_job_document_fails_without_running(self):
        cases = {"unknown key": {"extra": 1}, "wrong kind": {"kind": "other"},
                 "another job": {"jobId": "f" * 32}, "another disease": {"disease": "meningioma"}}
        jobs = {}
        for number, (label, overrides) in enumerate(cases.items(), start=1):
            publish_job(self.root, job_id=job_id(number), **overrides)
            jobs[label] = {"id": job_id(number)}
        broken = publish_job(self.root, job_id=job_id(9))
        (broken / "job.json").write_text("{not json", encoding="utf-8")
        jobs["not json"] = {"id": job_id(9)}
        found = self.verdicts(jobs)
        expected = {label: ("failed", "internal-error") for label in jobs}
        expected["another disease"] = ("failed", "input-invalid")
        self.assertEqual(found, expected)
        self.assertEqual(self.adapter.runs, [])

    def test_the_input_is_checked_against_job_json(self):
        payload = imaging_input()
        publish_job(self.root, job_id=job_id(1),
                    input={"path": "input.zip", "sha256": "0" * 64, "size": len(payload)})
        publish_job(self.root, job_id=job_id(2),
                    input={"path": "input.zip", "sha256": sha256(payload), "size": len(payload) + 1})
        found = self.verdicts({"checksum": {"id": job_id(1)}, "size": {"id": job_id(2)}})
        self.assertEqual(found, {"checksum": ("failed", "internal-error"),
                                 "size": ("failed", "internal-error")})
        self.assertEqual(self.adapter.runs, [])

    def test_an_input_over_the_executor_limit_is_refused(self):
        publish_job(self.root)
        found = self.verdicts({"large": {"id": JOB_ID}}, max_input_bytes=64)
        self.assertEqual(found, {"large": ("failed", "input-invalid")})
        self.assertEqual(self.adapter.runs, [])

    def test_hostile_archives_are_refused_and_nothing_is_extracted(self):
        manifest = json.dumps(imaging_manifest()).encode()
        link = zipfile.ZipInfo("volumes/t1.nii.gz")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        rest = [(f"volumes/{name}.nii.gz", MARKER) for name in ("t1ce", "t2", "flair")]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile warns about the duplicate name on purpose
            cases = {"traversal": imaging_input(extra=[("../escape.nii.gz", MARKER)]),
                     "absolute": imaging_input(extra=[("/escape.nii.gz", MARKER)]),
                     "symlink": zip_bytes([("input.json", manifest), (link, b"/etc/passwd"), *rest]),
                     "duplicate": imaging_input(extra=[("volumes/t1.nii.gz", MARKER)]),
                     "undeclared": imaging_input(extra=[("notes.txt", MARKER)]),
                     "declared but missing": zip_bytes([("input.json", manifest), *rest])}
        jobs = {}
        for number, (label, payload) in enumerate(cases.items(), start=1):
            publish_job(self.root, job_id=job_id(number), payload=payload)
            jobs[label] = {"id": job_id(number)}
        found = self.verdicts(jobs)
        self.assertEqual(found, {label: ("failed", "input-invalid") for label in cases})
        self.assertEqual(self.adapter.runs, [])
        self.assertEqual(list(self.base.rglob("escape*")), [])
        self.assertEqual(list(self.base.rglob("work")), [])


class AdapterVerdicts(ExecutorCase):
    def test_adapter_failures_become_contract_error_codes(self):
        outside = self.base / "outside.zip"
        outside.write_bytes(result_zip())
        cases = [("explicit code", FakeImagingAdapter("fail", code="model-unavailable"), "model-unavailable"),
                 ("unknown code", FakeImagingAdapter("fail", code="gpu-melted"), "internal-error"),
                 ("exception", FakeImagingAdapter("raise"), "inference-failed"),
                 ("out of memory", FakeImagingAdapter("oom"), "resource-exhausted"),
                 ("another job's result", FakeImagingAdapter(payload=result_zip(job_id="d" * 32)),
                  "inference-failed"),
                 ("not a zip", FakeImagingAdapter(payload=b"not a zip"), "inference-failed"),
                 ("escaping name", FakeImagingAdapter(name="../result.zip"), "inference-failed"),
                 ("missing result", FakeImagingAdapter(name="missing.zip"), "inference-failed"),
                 ("linked result", FakeImagingAdapter(link_to=outside), "inference-failed")]
        for number, (label, adapter, code) in enumerate(cases, start=1):
            with self.subTest(case=label):
                directory = publish_job(self.root, job_id=job_id(number))
                self.assertEqual(self.started(adapter=adapter).tick(), "failed")
                status = status_of(self.root, job_id(number))
                self.assertEqual((status["state"], status["errorCode"]), ("failed", code))
                self.assertEqual(sorted(os.listdir(directory)), ["input.zip", "job.json", "status.json"])
        self.assertEqual(outside.read_bytes(), result_zip(), "a linked result was written through")

    def test_a_result_over_its_size_limit_is_refused(self):
        publish_job(self.root)
        self.assertEqual(self.started(max_result_bytes=200).tick(), "failed")
        self.assertEqual(status_of(self.root)["errorCode"], "resource-exhausted")
        self.assertFalse((self.job_dir() / "result.zip").exists())


class TerminalStates(ExecutorCase):
    def test_a_terminal_status_is_never_rewritten(self):
        directory = publish_job(self.root)
        self.assertEqual(self.started().tick(), "completed")
        before = (directory / "status.json").read_bytes()
        job = LockedJob.acquire(self.root / "jobs", JOB_ID)
        try:
            for state, fields in (("failed", {"error_code": "internal-error"}), ("running", {}),
                                  ("accepted", {})):
                with self.subTest(state=state), self.assertRaises(StatusProblem):
                    job.advance(state, **fields)
        finally:
            job.close()
        self.assertEqual(self.started().tick(), "idle")
        self.assertEqual((directory / "status.json").read_bytes(), before)
        self.assertEqual(len(self.adapter.runs), 1)

    def test_a_status_never_moves_backwards_or_repeats(self):
        publish_job(self.root)
        job = LockedJob.acquire(self.root / "jobs", JOB_ID)
        try:
            job.advance("accepted")
            job.advance("running")
            for state in ("accepted", "running"):
                with self.subTest(state=state), self.assertRaises(StatusProblem):
                    job.advance(state)
            job.advance("failed", error_code="cancelled")
        finally:
            job.close()
        self.assertEqual(status_of(self.root)["state"], "failed")


if __name__ == "__main__":
    unittest.main()
