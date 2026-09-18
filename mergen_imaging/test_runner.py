from __future__ import annotations

import errno
import json
import re
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.archive_io import validate_result_archive
from mergen_imaging.glb import COLORS, REGIONS, mesh_glb_bytes
from mergen_imaging import (MODEL_ID, MODEL_VERSION, NNUNET_FOLDS, NNUNET_MEMBER,
                             PRODUCT_WEIGHTS, SWIN_MEMBER)
from mergen_imaging.runner import (CHANNEL_ORDER, NNUNET_CHANNEL_ORDER, OVERLAP, ROI, THRESHOLD,
                                   InputRejected, ResourceLimit, _failure_code,
                                   _locked_distributions, _member_records, _members,
                                   _package_result, _preprocessed_space, _respond,
                                   _same_geometry, _verify_environment)

JOB_ID = "e" * 32
TRAINER = "nnUNetTrainer__nnUNetPlans__3d_fullres"


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


class RegionTableTests(unittest.TestCase):
    """The viewer keeps its own copy of the region table; hold it to this one.

    Nothing at runtime connects the two, so a colour or a name changed on one
    side would simply draw a live result and a prepared demo differently.
    """

    REPO = Path(__file__).resolve().parent.parent

    def test_the_viewer_lists_the_same_regions(self):
        source = (self.REPO / "frontend/src/data/mesh.ts").read_text(encoding="utf-8")
        listed = re.search(r"export const regions = \[(.*?)\]", source, re.S)
        self.assertIsNotNone(listed, "regions listesi bulunamadı")
        names = tuple(re.findall(r"'([A-Z_]+)'", listed.group(1)))
        self.assertEqual(names, REGIONS)

    def test_the_viewer_draws_them_in_the_same_colours(self):
        source = (self.REPO / "frontend/src/components/VolumeViewer.tsx").read_text(
            encoding="utf-8")
        declared = re.search(r"const colors = \{(.*?)\}", source, re.S)
        self.assertIsNotNone(declared, "colors tablosu bulunamadı")
        hexes = dict(re.findall(r"(\w+): 0x([0-9a-fA-F]{6})", declared.group(1)))
        self.assertEqual(set(hexes), set(REGIONS))
        for region, value in hexes.items():
            channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            for drawn, packaged in zip(channels, COLORS[region][:3]):
                # Arayüz 8 bit, paket üç ondalık; fark bir adımdan küçük olmalı.
                self.assertAlmostEqual(drawn, packaged, delta=1 / 255, msg=region)


class RunnerContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mergen-runner-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.request = {"jobId": JOB_ID, "disease": "glioma",
                        "modelId": MODEL_ID, "modelVersion": MODEL_VERSION,
                        "maxResultBytes": 1024 * 1024}

    def test_reviewed_preprocessing_constants_do_not_drift(self):
        self.assertEqual(CHANNEL_ORDER, ("FLAIR", "T1CE", "T1", "T2"))
        # nnU-Net trained on its own channel order; the reference wrapper feeds
        # it T1, T1c, T2, FLAIR and the live path must not reorder them.
        self.assertEqual(NNUNET_CHANNEL_ORDER, ("T1", "T1CE", "T2", "FLAIR"))
        self.assertEqual((ROI, OVERLAP, THRESHOLD), ((128, 128, 128), 0.6, 0.5))

    def test_the_result_names_the_product_and_the_networks_behind_it(self):
        # The live path answers as the configuration that was measured, and the
        # report still says which networks produced it.
        self.assertEqual((MODEL_ID, MODEL_VERSION), ("mergen-uwcse", "v3"))
        self.assertEqual(_member_records(), [
            {"modelId": NNUNET_MEMBER[0], "modelVersion": NNUNET_MEMBER[1],
             "folds": [0, 1, 2, 3, 4]},
            {"modelId": SWIN_MEMBER[0], "modelVersion": SWIN_MEMBER[1]}])
        self.assertEqual(len(PRODUCT_WEIGHTS), 3)

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

    def write_manifest(self, checkpoints) -> None:
        (self.root / "manifest.json").write_text(json.dumps({"checkpoints": checkpoints}))

    @staticmethod
    def product_checkpoints(**changes):
        """The manifest the operator writes for the measured ensemble."""
        folds = [{"role": "nnunet-fold", "fold": fold,
                  "path": f"nnunet/Dataset002_BRATS19/{TRAINER}/fold_{fold}/checkpoint_final.pth"}
                 for fold in NNUNET_FOLDS]
        plans = [{"role": "nnunet-plan", "path": f"nnunet/Dataset002_BRATS19/{TRAINER}/{name}"}
                 for name in ("dataset.json", "plans.json")]
        swin = [{"role": "swin", "path": "swin/model.pt"}]
        return {"folds": folds, "plans": plans, "swin": swin} | changes

    def test_the_manifest_has_to_describe_the_measured_ensemble(self):
        parts = self.product_checkpoints()
        self.write_manifest(parts["folds"] + parts["plans"] + parts["swin"])
        members = _members(self.root)
        self.assertEqual(members.nnunet_dir,
                         self.root / "nnunet/Dataset002_BRATS19" / TRAINER)
        self.assertEqual(members.nnunet_checkpoint, "checkpoint_final.pth")
        self.assertEqual(members.swin, self.root / "swin/model.pt")

    def test_an_ensemble_that_is_not_the_measured_one_is_refused(self):
        # Each of these would run, and would be scored under the same name as
        # the configuration the locked-test numbers belong to.
        parts = self.product_checkpoints()
        folds, plans, swin = parts["folds"], parts["plans"], parts["swin"]
        renamed = [dict(item) for item in folds]
        renamed[2]["path"] = renamed[2]["path"].replace("checkpoint_final", "checkpoint_best")
        moved = [dict(item) for item in folds]
        moved[1]["path"] = moved[1]["path"].replace("Dataset002_BRATS19", "Dataset003_OTHER")
        mislabelled = [dict(item) for item in folds]
        mislabelled[0]["fold"] = 1
        for label, checkpoints, message in (
                ("a missing fold", folds[:-1] + swin, "every nnU-Net fold"),
                ("a repeated fold", folds + folds[:1] + swin, "declared once"),
                ("a fold number outside the set", folds[:-1] + swin + [
                    {"role": "nnunet-fold", "fold": 7,
                     "path": f"nnunet/Dataset002_BRATS19/{TRAINER}/fold_7/checkpoint_final.pth"}],
                 "every nnU-Net fold"),
                ("a fold whose directory disagrees", mislabelled + swin, "directory"),
                ("folds with different file names", renamed + swin, "different checkpoint names"),
                ("folds in two model folders", moved + swin, "one trained model folder"),
                ("no swin checkpoint", folds, "swin checkpoint is missing"),
                ("two swin checkpoints", folds + swin + swin, "exactly one swin"),
                ("an unknown role", folds + swin + [{"role": "genomics", "path": "x.pt"}],
                 "known roles"),
                ("a plan outside the model folder", folds + swin + [
                    {"role": "nnunet-plan", "path": "nnunet/plans.json"}],
                 "outside the trained model folder"),
                ("nothing at all", [], "lists no checkpoints")):
            with self.subTest(manifest=label):
                self.write_manifest(checkpoints)
                with self.assertRaisesRegex(ValueError, message):
                    _members(self.root)
        # The plans are optional; the ensemble is the five folds and Swin.
        self.write_manifest(folds + swin)
        self.assertEqual(_members(self.root).nnunet_checkpoint, "checkpoint_final.pth")

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
        self.assertEqual((manifest.modelId, manifest.modelVersion), (MODEL_ID, MODEL_VERSION))
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
