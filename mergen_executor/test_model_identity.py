"""A result must name the model its adapter declared, and an adapter whose
declared model no result could carry is never advertised.
Run: python -m unittest discover -s mergen_executor -t ."""
import os
import unittest

from mergen_executor.adapter import ImagingAdapter
from mergen_executor.test_support import (JOB_ID, ExecutorCase, FakeImagingAdapter, publish_job, ready_of,
                                          result_zip, status_of)


class ResultNamesTheDeclaredModel(ExecutorCase):
    def publish_with(self, **model) -> tuple[str, dict, list[str]]:
        directory = publish_job(self.root)
        adapter = FakeImagingAdapter(payload=result_zip(JOB_ID, **model))
        outcome = self.started(adapter=adapter).tick()
        return outcome, status_of(self.root), sorted(os.listdir(directory))

    def assert_refused(self, outcome: str, status: dict, listing: list[str]) -> None:
        self.assertEqual(outcome, "failed")
        self.assertEqual((status["state"], status["errorCode"]), ("failed", "inference-failed"))
        self.assertEqual(listing, ["gate", "input.zip", "job.json", "status.json"])

    def test_a_result_with_another_model_id_is_refused(self):
        self.assert_refused(*self.publish_with(model_id="another-model"))

    def test_a_result_with_another_model_version_is_refused(self):
        self.assert_refused(*self.publish_with(model_version="g3-other"))

    def test_a_result_with_the_declared_model_completes(self):
        outcome, status, _ = self.publish_with(model_id="fake-imaging", model_version="g3-test")
        self.assertEqual((outcome, status["state"]), ("completed", "completed"))


class DeclaredModel(ExecutorCase):
    def test_an_adapter_with_an_invalid_model_identity_advertises_nothing(self):
        class Undeclared(ImagingAdapter):
            def run(self, job):
                raise AssertionError("an undeclared model never runs")

        cases = {"no identity": Undeclared()}
        for label, model_id, model_version in (
                ("empty id", "", "g3-test"), ("upper-case id", "Fake-imaging", "g3-test"),
                ("underscore in id", "fake_imaging", "g3-test"), ("id not a string", 7, "g3-test"),
                ("empty version", "fake-imaging", ""), ("space in version", "fake-imaging", "g3 test"),
                ("version starts with a dot", "fake-imaging", ".g3"),
                ("version too long", "fake-imaging", "v" * 65), ("version not a string", "fake-imaging", 3)):
            adapter = FakeImagingAdapter()
            adapter.model_id, adapter.model_version = model_id, model_version
            cases[label] = adapter
        publish_job(self.root)
        for label, adapter in cases.items():
            with self.subTest(case=label):
                executor = self.started(adapter=adapter)
                self.assertEqual(executor.capabilities, [])
                ready = ready_of(self.root)
                self.assertEqual((ready["capabilities"], ready["acceptingJobs"]), ([], False))
                self.assertEqual(executor.tick(), "no-adapter")
                self.assertEqual(getattr(adapter, "runs", []), [])
        self.assertIsNone(status_of(self.root))

    def test_a_valid_model_identity_is_advertised_and_bound(self):
        adapter = FakeImagingAdapter()
        adapter.model_id, adapter.model_version = "other-imaging", "2026.09+cu124"
        publish_job(self.root)
        executor = self.started(adapter=adapter)
        self.assertEqual(executor.capabilities, ["imaging"])
        self.assertEqual(executor.tick(), "completed")


if __name__ == "__main__":
    unittest.main()
