"""
Uncertainty-Weighted Class-Specific Ensemble (UWCSE)
====================================================

Three orthogonal mechanisms layered on top of standard soft voting:

1) Class-Specific Weights (CSW)
   For each BraTS region (TC, WT, ET) a separate scalar weight balances
   nnU-Net vs Swin UNETR. Weights are tuned via Leave-One-Out CV (LOOCV)
   over the available cases so each test case is scored with weights it
   has not seen.

2) Voxel-Level Uncertainty Weighting (UWV)
   For every voxel and every region, the model that is more confident
   (probability further from 0.5) gets a larger effective weight. This
   prevents a model from dragging the ensemble down in regions where it
   is unsure. Confidence = 1 - H(p) where H is binary entropy.

3) BraTS Post-Processing (PP)
   - Remove small connected components (< MIN_CC_SIZE voxels) — false-positive
     cleanup that mirrors the official BraTS evaluation pipeline.
   - ET threshold rule: if total ET voxels < ET_MIN, relabel them as NCR
     (this is the canonical BraTS 2021 trick that prevents the
     "false ET" penalty when the model produces a handful of stray voxels).

Bibliographic anchors:
  - Class-specific ensemble: Kamnitsas et al., BraTS 2017 winner.
  - Voxel uncertainty fusion: Wang et al. 2019; Kendall & Gal 2017.
  - BraTS post-processing: Isensee et al. nnU-Net BraTS papers.
"""

import numpy as np
from skimage.measure import label as cc_label

EPS = 1e-7
MIN_CC_SIZE = 50      # min connected-component size (voxels)
ET_MIN = 100          # min ET voxels before applying relabel rule
TC_MIN = 250          # min tumour-core voxels before the core is dropped to edema
CORE_REVIEW_ET_MAX = 500   # a core claimed on a barely-enhancing tumour is flagged for review
# Constrained grid: keep nnUNet weight in [0.2, 0.8] so the ensemble cannot
# collapse to a single model. This regularises the per-region search on small
# validation sets (defensible per BraTS ensemble best-practices).
W_GRID = np.arange(0.20, 0.8001, 0.05)


# ── helpers ───────────────────────────────────────────────────────────
def _binary_entropy(p):
    p = np.clip(p, EPS, 1.0 - EPS)
    return -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))


def confidence(p):
    """Voxel-wise confidence in [0,1] from a sigmoid prob: 1 when p is 0 or 1, 0 at 0.5."""
    return 1.0 - _binary_entropy(p)


def _dice(a, b):
    inter = float((a * b).sum())
    return (2.0 * inter + EPS) / (float(a.sum()) + float(b.sum()) + EPS)


# ── ensemble variants ─────────────────────────────────────────────────
def vote_naive(prob_nn, prob_sw, w=0.5):
    """Baseline: equal-weight soft voting (current state-of-the-art-of-this-pipeline)."""
    return w * prob_nn + (1.0 - w) * prob_sw


def vote_class_specific(prob_nn, prob_sw, w_nn_per_region):
    """Class-specific Soft Voting. w_nn_per_region: array of 3 weights for [TC,WT,ET]."""
    w = np.asarray(w_nn_per_region, dtype=np.float32).reshape(3, 1, 1, 1)
    return w * prob_nn + (1.0 - w) * prob_sw


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


# ── post-processing on BraTS-labelled volume ──────────────────────────
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


# ── BraTS conversion helper (kept here so the module is self-contained) ────
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


# ── weight search ─────────────────────────────────────────────────────
def find_optimal_weights(prob_nn, prob_sw, gt_mc, grid=W_GRID):
    """
    Per-region grid search for the nnUNet weight on a single training case.
    Returns [w_TC, w_WT, w_ET], each in [0,1].
    Regions are independent (separate sigmoid channels), so we search one at a time.
    """
    best = [0.5, 0.5, 0.5]
    for r in range(3):
        best_d = -1.0
        for w in grid:
            p = w * prob_nn[r] + (1.0 - w) * prob_sw[r]
            seg = (p > 0.5).astype(np.float32)
            d = _dice(seg, gt_mc[r])
            if d > best_d:
                best_d = d
                best[r] = float(w)
    return best


def loocv_weights(case_data, target_case):
    """
    Leave-One-Out CV: average per-region optimal weights from every case
    except the target one. Falls back to [0.5, 0.5, 0.5] if there are no others.
    """
    train_cases = [c for c in case_data if c != target_case]
    if not train_cases:
        return [0.5, 0.5, 0.5]
    per_case = []
    for c in train_cases:
        cd = case_data[c]
        per_case.append(find_optimal_weights(cd["prob_nn"], cd["prob_sw"], cd["gt_mc"]))
    return np.mean(per_case, axis=0).tolist()


def average_val_weights(val_data):
    """
    Train/Test paradigm: find per-region optimal nnUNet weight for every
    validation case independently, then return the mean across val cases.
    val_data: dict[case_id -> {prob_nn, prob_sw, gt_mc, ...}]
    Returns: ([w_TC, w_WT, w_ET], list of per-case weight tuples)
    """
    per_case = []
    for cid, cd in val_data.items():
        w = find_optimal_weights(cd["prob_nn"], cd["prob_sw"], cd["gt_mc"])
        per_case.append((cid, w))
    weights_arr = np.array([w for _, w in per_case])
    avg = weights_arr.mean(axis=0).tolist()
    return avg, per_case


# ── dice across regions, accepting either probs (binary mask after thr) or label vol ──
def dice_regions(seg_regions, gt_mc):
    """Compute Dice for each of [TC, WT, ET] given 3-channel binary masks."""
    return {
        "TC": round(_dice(seg_regions[0], gt_mc[0]), 4),
        "WT": round(_dice(seg_regions[1], gt_mc[1]), 4),
        "ET": round(_dice(seg_regions[2], gt_mc[2]), 4),
    }
