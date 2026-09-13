from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from materialize_eval_cases import find_volume


class VolumeDiscoveryTests(unittest.TestCase):
    def test_reads_tcia_nested_nifti_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "UCSF-PDGM-0001_nifti/UCSF-PDGM-0001_FLAIR_bias.nii"
            folder.mkdir(parents=True)
            expected = folder / "volume.nii"
            expected.write_bytes(b"transport-fixture")
            self.assertEqual(find_volume(root, "UCSF-PDGM-0001", "FLAIR_bias"), expected)

    def test_rejects_ambiguous_nested_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "UCSF-PDGM-0001_nifti/UCSF-PDGM-0001_FLAIR_bias.nii"
            folder.mkdir(parents=True)
            (folder / "one.nii").write_bytes(b"one")
            (folder / "two.nii.gz").write_bytes(b"two")
            with self.assertRaisesRegex(ValueError, "Expected one file"):
                find_volume(root, "UCSF-PDGM-0001", "FLAIR_bias")


if __name__ == "__main__":
    unittest.main()
