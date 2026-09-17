"""UWCSE ürün kuralının davranışı: TC_MIN, review_flags ve füzyon.

Bu sayılar (250, 500) rastgele değil: 102 vakalık keşif havuzunda seçildi, ayrı
100 vakalık testte bir kez okundu (models/registry/mergen-uwcse/sampling_sweep/).
Testler bir ağırlık ya da GPU istemez; yalnız kural modülünü sınar.

    cd models/imaging && python3 -m unittest test_uwcse_rules
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uwcse_ensemble as ue  # noqa: E402


def volume_with(core: int = 0, edema: int = 0, enhancing: int = 0, shape=(24, 24, 24)) -> np.ndarray:
    """Tek bir bağlantılı kütle: önce ödem (2), içinde NCR (1), onun içinde ET (4)."""
    lab = np.zeros(shape, dtype=np.uint8)
    flat = lab.reshape(-1)
    flat[: edema + core + enhancing] = 2
    flat[: core + enhancing] = 1
    flat[:enhancing] = 4
    return lab


class PostProcessing(unittest.TestCase):
    def test_a_core_below_tc_min_is_demoted_to_edema_not_deleted(self):
        lab = volume_with(core=ue.TC_MIN - 1, edema=2000)
        out = ue.postprocess_brats(lab)
        self.assertEqual(int(((out == 1) | (out == 4)).sum()), 0, "çekirdek kaldı")
        # Doku WT içinde kalır: yalnız "burada çekirdek var" iddiası gider.
        self.assertEqual(int((out > 0).sum()), int((lab > 0).sum()))

    def test_a_core_at_tc_min_is_kept(self):
        lab = volume_with(core=ue.TC_MIN, edema=2000)
        out = ue.postprocess_brats(lab)
        self.assertEqual(int(((out == 1) | (out == 4)).sum()), ue.TC_MIN)

    def test_tc_min_zero_disables_the_rule(self):
        lab = volume_with(core=10, edema=2000)
        out = ue.postprocess_brats(lab, tc_min=0)
        self.assertEqual(int(((out == 1) | (out == 4)).sum()), 10)

    def test_the_standard_et_rule_still_applies_first(self):
        # ET_MIN altındaki ET NCR'ye iner; çekirdek TC_MIN üstündeyse kalır.
        lab = volume_with(core=ue.TC_MIN + 100, enhancing=ue.ET_MIN - 1, edema=2000)
        out = ue.postprocess_brats(lab)
        self.assertEqual(int((out == 4).sum()), 0)
        self.assertGreaterEqual(int((out == 1).sum()), ue.TC_MIN)

    def test_small_components_are_removed_before_the_core_rule(self):
        lab = volume_with(core=ue.TC_MIN + 50, edema=2000)
        lab[20, 20, 20] = 2  # tek voxel'lik ayrık parça
        out = ue.postprocess_brats(lab)
        self.assertEqual(int(out[20, 20, 20]), 0)


class ReviewFlags(unittest.TestCase):
    def test_a_core_on_a_barely_enhancing_tumour_is_flagged_with_its_evidence(self):
        lab = volume_with(core=3000, enhancing=ue.CORE_REVIEW_ET_MAX, edema=5000)
        flags = ue.review_flags(lab)
        self.assertEqual(len(flags), 1)
        flag = flags[0]
        self.assertEqual((flag["finding"], flag["severity"], flag["reason"]),
                         ("tumor_core", "low_confidence", "non_enhancing_tumor"))
        self.assertEqual(flag["evidence"]["enhancing_voxels"], ue.CORE_REVIEW_ET_MAX)
        self.assertEqual(flag["evidence"]["tumor_core_voxels"], 3000 + ue.CORE_REVIEW_ET_MAX)
        self.assertEqual(flag["evidence"]["enhancing_threshold"], ue.CORE_REVIEW_ET_MAX)
        # Bayrak bulguyu silmez: gerekçe metni arayüzde gösterilecek, boş olamaz.
        self.assertTrue(flag["message"].strip())

    def test_enough_enhancement_lifts_the_doubt(self):
        lab = volume_with(core=3000, enhancing=ue.CORE_REVIEW_ET_MAX + 1, edema=5000)
        self.assertEqual(ue.review_flags(lab), [])

    def test_no_core_means_nothing_to_doubt(self):
        lab = volume_with(edema=5000)
        self.assertEqual(ue.review_flags(lab), [])

    def test_the_flag_is_computed_after_the_volume_rule_would_run(self):
        # Kural ve bayrak birlikte kullanılır: kural küçük çekirdeği kaldırır,
        # bayrak kalan büyük ama kontrastsız çekirdeği işaretler.
        lab = ue.postprocess_brats(volume_with(core=3000, enhancing=10, edema=5000))
        self.assertEqual(int((lab == 4).sum()), 0, "ET_MIN altı ET NCR'ye inmeli")
        self.assertEqual(len(ue.review_flags(lab)), 1)


class Fusion(unittest.TestCase):
    def test_label_round_trip(self):
        lab = volume_with(core=300, enhancing=200, edema=1000)
        regions = ue.brats_to_regions(lab)
        np.testing.assert_array_equal(ue.mc_to_brats(regions), lab)

    def test_an_uncertain_model_gets_almost_no_say(self):
        # Voxel'de 0,5 veren model güvensizdir; kararı emin olan model verir.
        nn = np.full((3, 2, 2, 2), 0.5, dtype=np.float32)
        sw = np.full((3, 2, 2, 2), 0.95, dtype=np.float32)
        fused = ue.vote_uwcse(nn, sw, [0.5, 0.5, 0.5])
        self.assertTrue(np.all(fused > 0.9))

    def test_equal_confidence_reduces_to_the_class_weight(self):
        nn = np.full((3, 2, 2, 2), 0.9, dtype=np.float32)
        sw = np.full((3, 2, 2, 2), 0.1, dtype=np.float32)
        fused = ue.vote_uwcse(nn, sw, [0.425, 0.697, 0.447])
        # Aynı güvende ağırlık bölge katsayısıdır: w*0.9 + (1-w)*0.1.
        for r, w in enumerate((0.425, 0.697, 0.447)):
            self.assertAlmostEqual(float(fused[r, 0, 0, 0]), w * 0.9 + (1 - w) * 0.1, places=3)


if __name__ == "__main__":
    unittest.main()
