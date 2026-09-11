"""
UCSF-PDGM evaluation of the UWCSE pipeline.

Selects safe cases (those NOT in BraTS 2021 training cohort), splits them
into validation and test partitions with a fixed seed, runs nnU-Net + Swin
UNETR inference, fits class-specific ensemble weights on the validation
set, then reports per-variant Dice on the test set with mean ± std.

Outputs (under results_eval/):
  split.json             — which case ids landed in val vs test
  optimal_weights.json   — per-case val weights + averaged final weights
  test_metrics.json      — per-case, per-variant, per-region Dice
  summary.json           — mean / std / median for every variant
"""
import os
import json
import re
import time
from pathlib import Path

import numpy as np
import nibabel as nib
import pandas as pd
import torch

from monai.networks.nets import SwinUNETR
from monai.inferers import sliding_window_inference
from monai.transforms import NormalizeIntensity

from nnunet_predictor import NNUNetBraTSPredictor
import uwcse_ensemble as ue


BASE_DIR = Path(__file__).parent.resolve()
UCSF_DIR = BASE_DIR / "UCSF-PDGM" / "UCSF-PDGM-v5"
METADATA = BASE_DIR / "UCSF-PDGM" / "UCSF-PDGM-metadata_v5.csv"
SWIN_PATH = (
    BASE_DIR / "SwinUNETR_BRATS21" / "pretrained_models"
    / "fold0_f48_ep300_4gpu_dice0_8854" / "model.pt"
)
RESULTS_DIR = BASE_DIR / "results_eval"

# ── Evaluation configuration ──────────────────────────────────────────
N_VAL = 10            # cases used to tune CSW weights
N_TEST = 20           # cases used for final reporting
SEED = 42             # split reproducibility


# ── Dataset helpers ───────────────────────────────────────────────────
def pad_case_id(cid: str) -> str:
    """'UCSF-PDGM-5' or 'UCSF-PDGM-005' -> 'UCSF-PDGM-0005'."""
    prefix, num = cid.rsplit("-", 1)
    return f"{prefix}-{int(num):04d}"


def resolve_nii(case_dir: Path, name: str) -> Path:
    """UCSF-PDGM-v5 wraps each *.nii inside a folder of the same name, so the
    actual file lives at <case_dir>/<name>/<name>. We resolve both layouts."""
    flat = case_dir / name
    nested = case_dir / name / name
    if flat.is_file():
        return flat
    if nested.is_file():
        return nested
    return flat   # let nibabel raise the readable error


def discover_safe_cases() -> list[str]:
    """Return UCSF-PDGM case ids NOT in the BraTS 2021 segmentation cohort
    (neither Training nor Validation), with all required files on disk."""
    df = pd.read_csv(METADATA)
    cohort = df["BraTS21 Segmentation Cohort"].fillna("NOT_IN_BRATS21")
    safe_meta = df[cohort == "NOT_IN_BRATS21"]
    # Drop follow-up scans (e.g., 'UCSF-PDGM-0391_FU016d') — keep primary acquisitions only.
    primary = safe_meta[~safe_meta["ID"].str.contains("_", na=False)]
    candidates = [pad_case_id(c) for c in primary["ID"].tolist()]

    available = []
    for cid in candidates:
        folder = UCSF_DIR / f"{cid}_nifti"
        if not folder.is_dir():
            continue
        req = [f"{cid}_FLAIR.nii", f"{cid}_T1.nii", f"{cid}_T1c.nii",
               f"{cid}_T2.nii", f"{cid}_tumor_segmentation.nii"]
        if all(resolve_nii(folder, f).is_file() for f in req):
            available.append(cid)
    return sorted(available)


def build_case(case_id: str) -> dict:
    return {
        "name": case_id,
        "dir": f"{case_id}_nifti",
        "flair": f"{case_id}_FLAIR.nii",
        "t1": f"{case_id}_T1.nii",
        "t1c": f"{case_id}_T1c.nii",
        "t2": f"{case_id}_T2.nii",
        "label": f"{case_id}_tumor_segmentation.nii",
    }


def load_mri(case: dict, channel_order: list[str]) -> np.ndarray:
    mod_map = {"FLAIR": case["flair"], "T1": case["t1"],
               "T1c": case["t1c"], "T2": case["t2"]}
    vols = []
    case_dir = UCSF_DIR / case["dir"]
    for mod in channel_order:
        path = resolve_nii(case_dir, mod_map[mod])
        vols.append(nib.load(str(path)).get_fdata().astype(np.float32))
    return np.stack(vols, axis=0)


def load_label(case: dict) -> tuple[np.ndarray, np.ndarray]:
    case_dir = UCSF_DIR / case["dir"]
    path = resolve_nii(case_dir, case["label"])
    lab = nib.load(str(path)).get_fdata().astype(np.float32)
    tc = ((lab == 1) | (lab == 4)).astype(np.uint8)
    wt = ((lab == 1) | (lab == 2) | (lab == 4)).astype(np.uint8)
    et = (lab == 4).astype(np.uint8)
    return np.stack([tc, wt, et], axis=0), lab.astype(np.uint8)


def normalize(arr: np.ndarray) -> torch.Tensor:
    return NormalizeIntensity(nonzero=True, channel_wise=True)(torch.from_numpy(arr))


# ── Main pipeline ─────────────────────────────────────────────────────
def run():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    RESULTS_DIR.mkdir(exist_ok=True)

    # ── Case selection + split ────────────────────────────────────────
    print("\nDiscovering safe (BraTS21-out-of-cohort) cases ...")
    safe_ids = discover_safe_cases()
    print(f"  Found {len(safe_ids)} safe cases on disk.")
    n_needed = N_VAL + N_TEST
    assert len(safe_ids) >= n_needed, (
        f"Need at least {n_needed} safe cases; only {len(safe_ids)} available."
    )

    rng = np.random.RandomState(SEED)
    chosen = list(safe_ids)
    rng.shuffle(chosen)
    val_ids = chosen[:N_VAL]
    test_ids = chosen[N_VAL:N_VAL + N_TEST]

    split = {"seed": SEED, "n_safe": len(safe_ids),
             "val": val_ids, "test": test_ids}
    (RESULTS_DIR / "split.json").write_text(json.dumps(split, indent=2))
    print(f"  Validation cases ({len(val_ids)}): {val_ids}")
    print(f"  Test cases ({len(test_ids)}): {test_ids}")

    # ── PHASE 1: Inference (val + test), probs streamed to disk ──────
    print(f"\n{'='*60}\nPHASE 1: Inference\n{'='*60}")
    PROBS_DIR = RESULTS_DIR / "_probs_cache"
    PROBS_DIR.mkdir(exist_ok=True)
    print("Loading nnU-Net (BraTS21, fold_0) ...")
    nn_predictor = NNUNetBraTSPredictor(folds=(0,), device=device)

    case_index: dict[str, str] = {}      # case_id -> split label
    all_cases = [(cid, "VAL") for cid in val_ids] + [(cid, "TEST") for cid in test_ids]
    t_start = time.time()

    for idx, (cid, split_name) in enumerate(all_cases, start=1):
        case = build_case(cid)
        elapsed = time.time() - t_start
        print(f"\n[{idx}/{len(all_cases)}] [{split_name}] {cid}  (elapsed {elapsed:.0f}s)")
        try:
            gt_mc, gt_lab = load_label(case)

            prob_nn = nn_predictor.predict(case, str(UCSF_DIR))
            torch.cuda.empty_cache()

            mdl = SwinUNETR(in_channels=4, out_channels=3, feature_size=48,
                            drop_rate=0.0, attn_drop_rate=0.0,
                            dropout_path_rate=0.0, use_checkpoint=True)
            mdl.load_state_dict(torch.load(
                str(SWIN_PATH), map_location="cpu", weights_only=False
            )["state_dict"])
            mdl.eval().to(device)
            img = normalize(load_mri(case, ["FLAIR", "T1c", "T1", "T2"])).unsqueeze(0).to(device)
            with torch.no_grad(), torch.amp.autocast("cuda"):
                p = sliding_window_inference(img, [128, 128, 128], 1, mdl, overlap=0.6)
                prob_sw = torch.sigmoid(p)[0].cpu().numpy()
            del mdl, img, p
            torch.cuda.empty_cache()

            # Save probs to disk as float16 (probability data is smooth, compresses well)
            np.savez_compressed(
                PROBS_DIR / f"{cid}.npz",
                prob_nn=prob_nn.astype(np.float16),
                prob_sw=prob_sw.astype(np.float16),
                gt_mc=gt_mc,
            )
            del prob_nn, prob_sw, gt_mc, gt_lab
            case_index[cid] = split_name
        except Exception as exc:
            print(f"  ERROR: {exc}")
            continue

    nn_predictor.unload()
    print(f"\nPhase 1 done in {time.time() - t_start:.0f}s. "
          f"Cached probs: {len(case_index)} cases.")

    def _load_probs(cid: str) -> dict:
        z = np.load(PROBS_DIR / f"{cid}.npz")
        return {
            "prob_nn": z["prob_nn"].astype(np.float32),
            "prob_sw": z["prob_sw"].astype(np.float32),
            "gt_mc": z["gt_mc"],
        }

    # ── PHASE 2a: Validation-based weight optimization ───────────────
    print(f"\n{'='*60}\nPHASE 2a: Weight optimization on val set\n{'='*60}")
    val_ids_loaded = [c for c, s in case_index.items() if s == "VAL"]
    test_ids_loaded = [c for c, s in case_index.items() if s == "TEST"]

    per_case_w = []
    for cid in val_ids_loaded:
        d = _load_probs(cid)
        w = ue.find_optimal_weights(d["prob_nn"], d["prob_sw"], d["gt_mc"])
        per_case_w.append((cid, w))
        print(f"  [{cid}]  TC={w[0]:.2f}  WT={w[1]:.2f}  ET={w[2]:.2f}")
        del d
    weights_arr = np.array([w for _, w in per_case_w])
    optimal_w = weights_arr.mean(axis=0).tolist()
    print(f"\n  Optimal averaged weights (nnU-Net):")
    print(f"    TC = {optimal_w[0]:.3f}")
    print(f"    WT = {optimal_w[1]:.3f}")
    print(f"    ET = {optimal_w[2]:.3f}")
    weights_log = {
        "averaged": {"TC": optimal_w[0], "WT": optimal_w[1], "ET": optimal_w[2]},
        "per_val_case": {cid: {"TC": w[0], "WT": w[1], "ET": w[2]}
                         for cid, w in per_case_w},
    }
    (RESULTS_DIR / "optimal_weights.json").write_text(json.dumps(weights_log, indent=2))

    # ── PHASE 2b: Ablation on test set ───────────────────────────────
    print(f"\n{'='*60}\nPHASE 2b: Test-set ablation\n{'='*60}")
    test_metrics: dict[str, dict] = {}
    variant_names = ["nnUNet", "SwinUNETR",
                     "V0_Naive", "V1_CSW", "V2_CSW+UNC", "V3_CSW+PP", "V4_UWCSE_Full"]

    for i, cid in enumerate(test_ids_loaded, start=1):
        d = _load_probs(cid)
        prob_nn, prob_sw, gt_mc = d["prob_nn"], d["prob_sw"], d["gt_mc"]

        p_v0 = ue.vote_naive(prob_nn, prob_sw, 0.5)
        brats_v0 = ue.mc_to_brats((p_v0 > 0.5).astype(np.uint8))
        p_v1 = ue.vote_class_specific(prob_nn, prob_sw, optimal_w)
        brats_v1 = ue.mc_to_brats((p_v1 > 0.5).astype(np.uint8))
        p_v2 = ue.vote_uwcse(prob_nn, prob_sw, optimal_w)
        brats_v2 = ue.mc_to_brats((p_v2 > 0.5).astype(np.uint8))
        brats_v3 = ue.postprocess_brats(brats_v1)
        brats_v4 = ue.postprocess_brats(brats_v2)
        brats_nn = ue.mc_to_brats((prob_nn > 0.5).astype(np.uint8))
        brats_sw = ue.mc_to_brats((prob_sw > 0.5).astype(np.uint8))

        per_variant = {
            "nnUNet": brats_nn, "SwinUNETR": brats_sw,
            "V0_Naive": brats_v0, "V1_CSW": brats_v1, "V2_CSW+UNC": brats_v2,
            "V3_CSW+PP": brats_v3, "V4_UWCSE_Full": brats_v4,
        }
        rows = {}
        for name in variant_names:
            seg = ue.brats_to_regions(per_variant[name])
            d_dice = ue.dice_regions(seg, gt_mc)
            d_dice["Mean"] = round((d_dice["TC"] + d_dice["WT"] + d_dice["ET"]) / 3, 4)
            rows[name] = d_dice
        test_metrics[cid] = rows
        print(f"  [{i}/{len(test_ids_loaded)}] {cid}  "
              f"nnU-Net={rows['nnUNet']['Mean']}  UWCSE={rows['V4_UWCSE_Full']['Mean']}")
        del d, prob_nn, prob_sw, gt_mc

    (RESULTS_DIR / "test_metrics.json").write_text(json.dumps({
        "optimal_weights": {"TC": optimal_w[0], "WT": optimal_w[1], "ET": optimal_w[2]},
        "per_case": test_metrics,
    }, indent=2))

    # ── Summary statistics ────────────────────────────────────────────
    print(f"\n{'='*60}\nTest-set summary (n={len(test_ids_loaded)})\n{'='*60}")
    summary = {}
    print(f"  {'Variant':<18s} {'TC':<14} {'WT':<14} {'ET':<14} {'Mean':<14}")
    for v in variant_names:
        row = {}
        for r in ["TC", "WT", "ET", "Mean"]:
            vals = np.array([test_metrics[c][v][r] for c in test_metrics])
            row[r] = {"mean": float(vals.mean()), "std": float(vals.std()),
                      "median": float(np.median(vals))}
        summary[v] = row
        marker = " *" if v == "V4_UWCSE_Full" else ""
        print(f"  {v:<18s} "
              f"{row['TC']['mean']:.4f}±{row['TC']['std']:.3f}  "
              f"{row['WT']['mean']:.4f}±{row['WT']['std']:.3f}  "
              f"{row['ET']['mean']:.4f}±{row['ET']['std']:.3f}  "
              f"{row['Mean']['mean']:.4f}±{row['Mean']['std']:.3f}{marker}")

    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nResults -> {RESULTS_DIR}")


if __name__ == "__main__":
    run()
