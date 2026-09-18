"""The UWCSE v3 product rule, in the isolated runner package.

The research pipeline in `models/imaging/uwcse_ensemble.py` carries the weight
search, the ablations and the metrics; only the path that ships is here, so the
model virtualenv does not have to import that tree. The two implementations are
held together by `models/imaging/test_live_product_rule.py`, which runs both on
the same volumes and fails when they disagree — a rewritten research module
therefore breaks the build instead of quietly changing what the live path does.

Product path: vote_uwcse(prob_nn, prob_sw, weights) > 0.5 → mc_to_brats →
postprocess_brats → review_flags.
"""
from __future__ import annotations

import numpy as np
from skimage.measure import label as cc_label

EPS = 1e-7
MIN_CC_SIZE = 50           # min connected-component size (voxels)
ET_MIN = 100               # min ET voxels before applying relabel rule
TC_MIN = 250               # min tumour-core voxels before the core is dropped to edema
CORE_REVIEW_ET_MAX = 500   # a core claimed on a barely-enhancing tumour is flagged for review


def _binary_entropy(p):
    p = np.clip(p, EPS, 1.0 - EPS)
    return -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))


def confidence(p):
    """Voxel-wise confidence in [0,1] from a sigmoid prob: 1 when p is 0 or 1, 0 at 0.5."""
    return 1.0 - _binary_entropy(p)


def vote_uwcse(prob_nn, prob_sw, w_nn_per_region):
    """
    Voxel-level uncertainty-weighted class-specific fusion.
    Effective weight per voxel = (region prior) * (model confidence at that voxel).
    """
    w = np.asarray(w_nn_per_region, dtype=np.float32).reshape(3, 1, 1, 1)
    conf_nn = confidence(prob_nn)
    conf_sw = confidence(prob_sw)
    w_nn_eff = w * conf_nn
    w_sw_eff = (1.0 - w) * conf_sw
    denom = w_nn_eff + w_sw_eff + EPS
    return (w_nn_eff * prob_nn + w_sw_eff * prob_sw) / denom


def mc_to_brats(seg3):
    """3-channel binary (TC,WT,ET) → single BraTS-label volume (0,1,2,4)."""
    out = np.zeros_like(seg3[0], dtype=np.uint8)
    out[seg3[1] == 1] = 2   # ED
    out[seg3[0] == 1] = 1   # NCR
    out[seg3[2] == 1] = 4   # ET
    return out


def brats_to_regions(seg_lab):
    """Inverse of mc_to_brats: BraTS labels → 3-channel binary (TC,WT,ET)."""
    tc = ((seg_lab == 1) | (seg_lab == 4)).astype(np.uint8)
    wt = ((seg_lab == 1) | (seg_lab == 2) | (seg_lab == 4)).astype(np.uint8)
    et = (seg_lab == 4).astype(np.uint8)
    return np.stack([tc, wt, et], axis=0)


def postprocess_brats(seg_lab, min_cc_size=MIN_CC_SIZE, et_min=ET_MIN, tc_min=TC_MIN):
    """
    Apply the cleanup rules to a label volume (0,1,2,4):
      1) drop connected components of the WT mask that are smaller than min_cc_size
      2) if total ET voxel count < et_min, demote ET (4) to NCR (1)
      3) if the whole tumour core (NCR + ET) is smaller than tc_min, demote it to edema (2)

    Rule 3 is ours, and it exists because BraTS21-trained networks mark a tumour core on
    non-enhancing low-grade gliomas that have none. It is the same shape of rule as the
    standard ET one: below a volume the finding is not credible, so it is demoted rather
    than deleted — the tissue stays inside WT, only the "there is a core here" claim goes.
    Chosen on 102 held-out cases and read out once on a separate 100-case test set:
    silence on cores that do not exist 69% -> 83%, Dice where a core does exist -0.005,
    WT and ET untouched. Pass tc_min=0 to disable.
    """
    out = seg_lab.copy()
    wt_mask = (out > 0).astype(np.uint8)
    if wt_mask.any():
        labels = cc_label(wt_mask, connectivity=2)
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        small = np.where(sizes < min_cc_size)[0]
        if len(small):
            small_mask = np.isin(labels, small)
            out[small_mask] = 0
    et_count = int((out == 4).sum())
    if 0 < et_count < et_min:
        out[out == 4] = 1
    if tc_min:
        core = (out == 1) | (out == 4)
        if 0 < int(core.sum()) < tc_min:
            out[core] = 2
    return out


def review_flags(seg_lab, et_max=CORE_REVIEW_ET_MAX) -> list[dict]:
    """Findings in this segmentation that a reader should not take at face value.

    BraTS-trained networks mark a tumour core on non-enhancing gliomas that have none, and
    the volume rule in ``postprocess_brats`` only removes the small ones. What separates the
    survivors is enhancement: a core claimed on a tumour with almost no enhancing component
    is the unreliable kind. Measured on 102 held-out cases and read out once on a separate
    100-case test set: the flag catches 5 of the 6 cores that should not be there, and
    wrongly questions 2 of 60 real ones.

    Returns a list of flags, each with the finding, why it is doubted, and the numbers behind
    it, so the interface can show the reason rather than an unexplained warning icon.
    """
    regions = brats_to_regions(seg_lab)
    tc, et = int(regions[0].sum()), int(regions[2].sum())
    flags = []
    if tc > 0 and et <= et_max:
        flags.append({
            "finding": "tumor_core",
            "severity": "low_confidence",
            "reason": "non_enhancing_tumor",
            "message": ("Tümör kontrast tutmuyor ama model bir tümör çekirdeği işaretledi. "
                        "Bu kombinasyonda bulgu güvenilir değil; çekirdeği doğrulamadan kullanmayın."),
            "evidence": {"tumor_core_voxels": tc, "enhancing_voxels": et, "enhancing_threshold": et_max},
        })
    return flags


def region_volumes(seg_lab) -> dict:
    """Voxel counts of the three reported regions, the way the figures report them."""
    regions = brats_to_regions(seg_lab)
    return {name: int(regions[index].sum()) for index, name in enumerate(("TC", "WT", "ET"))}
