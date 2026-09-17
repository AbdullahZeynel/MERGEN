"""The live runner's product rule must be this pipeline's product path.

`mergen_imaging/uwcse.py` ships inside the isolated model virtualenv so the live
runner does not import this tree; that copy only earns its place while it
behaves identically. These tests run both implementations on the same volumes —
including the cases where the volume rules actually fire — and compare what they
produce. A rewritten `uwcse_ensemble.py` (the file is regenerated from the GPU
host's workflow) therefore fails the build instead of silently changing what the
live path does.

Run: cd models/imaging && python -m unittest discover -p 'test_*.py'
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import uwcse_ensemble as research  # noqa: E402

from mergen_imaging import PRODUCT_WEIGHTS  # noqa: E402
from mergen_imaging import uwcse as live  # noqa: E402

SHAPE = (28, 28, 28)


def _blob(shape, centre, radius, value, base=None):
    field = np.zeros(shape, dtype=np.float32) if base is None else base
    grid = np.ogrid[tuple(slice(0, size) for size in shape)]
    distance = sum((axis - position) ** 2 for axis, position in zip(grid, centre))
    field[distance <= radius ** 2] = value
    return field


def _scenarios():
    """Probability pairs that exercise each rule, not just the average case."""
    rng = np.random.default_rng(20260918)
    noise = (rng.random((3,) + SHAPE, dtype=np.float32) * 0.9 + 0.05,
             rng.random((3,) + SHAPE, dtype=np.float32) * 0.9 + 0.05)
    # A tumour large enough to keep its core: TC_MIN and ET_MIN leave it alone.
    large = np.full((3,) + SHAPE, 0.02, dtype=np.float32)
    large[0] = _blob(SHAPE, (14, 14, 14), 7, 0.95)
    large[1] = _blob(SHAPE, (14, 14, 14), 9, 0.95)
    large[2] = _blob(SHAPE, (14, 14, 14), 6, 0.95)
    # A non-enhancing tumour with a core too small to be credible: the TC_MIN
    # rule demotes it and the review flag fires.
    small = np.full((3,) + SHAPE, 0.02, dtype=np.float32)
    small[0] = _blob(SHAPE, (10, 10, 10), 2, 0.95)
    small[1] = _blob(SHAPE, (10, 10, 10), 8, 0.95)
    # Speckle: a scatter of tiny components the size rule has to clear.
    speckle = np.full((3,) + SHAPE, 0.02, dtype=np.float32)
    speckle[1] = np.where(rng.random(SHAPE) > 0.98, 0.95, 0.02).astype(np.float32)
    return {
        "noise": noise,
        "large tumour": (large, large * 0.9 + 0.05),
        "small non-enhancing core": (small, small * 0.9 + 0.05),
        "speckle": (speckle, speckle * 0.9 + 0.05),
    }


def _labels(module, prob_nn, prob_sw):
    fused = module.vote_uwcse(prob_nn, prob_sw, PRODUCT_WEIGHTS)
    return module.postprocess_brats(module.mc_to_brats((fused > 0.5).astype(np.uint8)))


class ProductRuleTests(unittest.TestCase):
    def test_both_implementations_label_the_same_voxels(self):
        for name, (prob_nn, prob_sw) in _scenarios().items():
            with self.subTest(case=name):
                expected = _labels(research, prob_nn, prob_sw)
                np.testing.assert_array_equal(_labels(live, prob_nn, prob_sw), expected)

    def test_the_rules_actually_fire_in_these_scenarios(self):
        # Without this the comparison above could pass on four no-ops.
        scenarios = _scenarios()
        small = _labels(live, *scenarios["small non-enhancing core"])
        self.assertEqual(int((small == 1).sum()) + int((small == 4).sum()), 0)
        self.assertGreater(int((small == 2).sum()), 0)
        large = _labels(live, *scenarios["large tumour"])
        self.assertGreater(int((large == 1).sum()) + int((large == 4).sum()), research.TC_MIN)
        speckle_before = research.mc_to_brats(
            (live.vote_uwcse(*scenarios["speckle"], PRODUCT_WEIGHTS) > 0.5).astype(np.uint8))
        speckle_after = _labels(live, *scenarios["speckle"])
        self.assertGreater(int((speckle_before > 0).sum()), int((speckle_after > 0).sum()))

    def test_both_implementations_raise_the_same_flag(self):
        for name, (prob_nn, prob_sw) in _scenarios().items():
            with self.subTest(case=name):
                labels = _labels(live, prob_nn, prob_sw)
                self.assertEqual(live.review_flags(labels), research.review_flags(labels))
        # And the flag does fire on a core with no enhancement behind it.
        flagged = np.zeros(SHAPE, dtype=np.uint8)
        flagged[10:14, 10:14, 10:14] = 1
        self.assertEqual([flag["reason"] for flag in live.review_flags(flagged)],
                         ["non_enhancing_tumor"])

    def test_the_volume_rules_carry_the_same_numbers(self):
        for name in ("EPS", "MIN_CC_SIZE", "ET_MIN", "TC_MIN", "CORE_REVIEW_ET_MAX"):
            with self.subTest(constant=name):
                self.assertEqual(getattr(live, name), getattr(research, name))

    def test_region_volumes_are_the_regions_the_figures_report(self):
        labels = _labels(live, *_scenarios()["large tumour"])
        regions = research.brats_to_regions(labels)
        self.assertEqual(live.region_volumes(labels),
                         {"TC": int(regions[0].sum()), "WT": int(regions[1].sum()),
                          "ET": int(regions[2].sum())})

    def test_the_frozen_weights_are_the_registry_weights(self):
        # The live path cannot fit weights; it carries the ones that were fitted
        # on the validation cases and read out once on the locked test split.
        measured = json.loads(
            (REPO / "models/registry/mergen-uwcse/uwcse_v3/segmentation_metrics.json")
            .read_text(encoding="utf-8"))["fitted_weights"]
        self.assertEqual(dict(zip(("TC", "WT", "ET"), PRODUCT_WEIGHTS)), measured)


if __name__ == "__main__":
    unittest.main()
