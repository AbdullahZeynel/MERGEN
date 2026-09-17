from __future__ import annotations

import errno
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.archive_io import validate_result_archive
from mergen_imaging.glb import mesh_glb_bytes
from mergen_imaging.runner import (CHANNEL_ORDER, OVERLAP, ROI, THRESHOLD, InputRejected,
                                   ResourceLimit, _checkpoint, _failure_code,
                                   _locked_distributions, _package_result,
                                   _preprocessed_space, _respond, _same_geometry,
                                   _verify_environment)

JOB_ID = "e" * 32


class GlbTests(unittest.TestCase):
    def test_empty_prediction_is_still_a_valid_glb(self):
        payload = mesh_glb_bytes({})
        magic, version, size = struct.unpack_from("<4sII", payload)
        self.assertEqual((magic, version, size), (b"glTF", 2, len(payload)))
        json_size, kind = struct.unpack_from("<I4s", payload, 12)
        document = json.loads(payload[20:20 + json_size])
        self.assertEqual(kind, b"JSON")
        self.assertEqual(document["scenes"], [{"nodes": []}])

    def test_regions_are_indexed_and_invalid_faces_are_rejected(self):
        mesh = {"ET": {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                       "faces": [[0, 1, 2]]}}
        payload = mesh_glb_bytes(mesh)
        json_size = struct.unpack_from("<I", payload, 12)[0]
        document = json.loads(payload[20:20 + json_size])
        self.assertEqual(document["nodes"][0]["name"], "ET")
        with self.assertRaisesRegex(ValueError, "invalid mesh faces"):
            mesh_glb_bytes({"ET": {"vertices": [[0, 0, 0]], "faces": [[0, 1, 0]]}})


class RunnerContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mergen-runner-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.request = {"jobId": JOB_ID, "disease": "glioma",
                        "modelId": "swin-unetr-brats21", "modelVersion": "fold0-f48-ep300",
                        "maxResultBytes": 1024 * 1024}

    def test_reviewed_preprocessing_constants_do_not_drift(self):
        self.assertEqual(CHANNEL_ORDER, ("FLAIR", "T1CE", "T1", "T2"))
        self.assertEqual((ROI, OVERLAP, THRESHOLD), ((128, 128, 128), 0.6, 0.5))

    def test_model_environment_is_exact_and_accepts_a_cuda_local_suffix(self):
        expected = _locked_distributions()
        self.assertGreater(len(expected), 20)

        def installed(name):
            value = expected[name]
            return value + "+cu130" if name == "torch" else value

        with patch("mergen_imaging.runner.importlib.metadata.version", side_effect=installed):
            _verify_environment()
        with patch("mergen_imaging.runner.importlib.metadata.version", return_value="0.0"):
            with self.assertRaisesRegex(RuntimeError, "version mismatch"):
                _verify_environment()

    def test_checkpoint_comes_from_the_single_manifest_entry(self):
        (self.root / "manifest.json").write_text(json.dumps({
            "checkpoints": [{"path": "pretrained/model.pt"}]}))
        self.assertEqual(_checkpoint(self.root), self.root / "pretrained/model.pt")
        (self.root / "manifest.json").write_text('{"checkpoints": []}')
        with self.assertRaisesRegex(ValueError, "exactly one"):
            _checkpoint(self.root)

    def test_only_the_reviewed_voxel_grid_is_accepted(self):
        # The affine every reviewed UCSF-PDGM case carries: 1 mm, LPS.
        reviewed = [[-1, 0, 0, 0], [0, -1, 0, 239], [0, 0, 1, 0], [0, 0, 0, 1]]
        self.assertTrue(_preprocessed_space(reviewed))
        rejected = {
            # 2 mm isotropic: the runner does not resample, so this would be
            # segmented at half scale without a word.
            "rescaled": [[-2, 0, 0, 0], [0, -2, 0, 239], [0, 0, 2, 0], [0, 0, 0, 1]],
            # RAS instead of LPS: two axes flipped under the same voxel indices.
            "reoriented": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            # Axis-aligned no more; nothing downstream would notice.
            "rotated": [[-1, 0.05, 0, 0], [0.05, -1, 0, 239], [0, 0, 1, 0], [0, 0, 0, 1]],
            "malformed": [[-1, 0, 0], [0, -1, 0], [0, 0, 1]],
        }
        for label, affine in rejected.items():
            with self.subTest(space=label):
                self.assertFalse(_preprocessed_space(affine))

    def test_a_rejected_input_keeps_its_contract_code_and_stays_quiet(self):
        self.assertEqual(_failure_code(InputRejected("the volume names a patient")),
                         "input-invalid")
        self.assertEqual(_failure_code(ResourceLimit()), "resource-exhausted")
        self.assertEqual(_failure_code(OSError(errno.ENOSPC, "no space")), "resource-exhausted")
        # Anything else stays an opaque exit: a message could quote the input.
        for opaque in (RuntimeError("cuda: /srv/patient-0004/T1.nii.gz"), ValueError(), OSError()):
            with self.subTest(exception=type(opaque).__name__):
                self.assertIsNone(_failure_code(opaque))

    def test_modalities_must_have_the_same_shape_and_affine(self):
        identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        self.assertTrue(_same_geometry((10, 20, 30), identity, (10, 20, 30), identity))
        self.assertFalse(_same_geometry((10, 20, 31), identity, (10, 20, 30), identity))
        moved = [row[:] for row in identity]
        moved[0][3] = 0.01
        self.assertFalse(_same_geometry((10, 20, 30), moved, (10, 20, 30), identity))

    def test_result_zip_matches_the_live_contract(self):
        files = (("report.json", "report-json"), ("prediction.nii.gz", "prediction-nifti"),
                 ("prediction.glb", "prediction-glb"))
        for name, _ in files:
            (self.root / name).write_bytes(("asset:" + name).encode())
        self.assertEqual(_package_result(self.request, self.root, files), "result.zip")
        manifest = validate_result_archive(self.root / "result.zip", 1024 * 1024,
                                           {"id": JOB_ID, "module": "imaging", "disease": "glioma"})
        self.assertEqual((manifest.modelId, manifest.modelVersion),
                         ("swin-unetr-brats21", "fold0-f48-ep300"))
        with zipfile.ZipFile(self.root / "result.zip") as archive:
            self.assertNotIn("input.json", archive.namelist())

    def test_result_limit_never_leaves_a_publishable_zip(self):
        files = (("report.json", "report-json"), ("prediction.nii.gz", "prediction-nifti"),
                 ("prediction.glb", "prediction-glb"))
        for name, _ in files:
            (self.root / name).write_bytes(b"x" * 100)
        request = {**self.request, "maxResultBytes": 1}
        with self.assertRaises(Exception) as raised:
            _package_result(request, self.root, files)
        self.assertEqual(type(raised.exception).__name__, "ResourceLimit")
        self.assertFalse((self.root / "result.zip").exists())

    def test_response_is_replaced_without_leaving_a_temporary(self):
        _respond(self.root, "result.zip")
        self.assertEqual(json.loads((self.root / ".adapter-response.json").read_text()),
                         {"result": "result.zip"})
        self.assertFalse((self.root / ".adapter-response.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
