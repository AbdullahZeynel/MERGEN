"""
Ensemble Brain Tumor Segmentation Pipeline
-------------------------------------------
nnU-Net (BraTS21) + Swin UNETR (BraTS21) → Soft Voting Ensemble
Both models trained on the same BraTS 2021 dataset for consistency.
Runs inference on example_dataset, calculates Dice scores,
generates 3D meshes and saves all results for the web dashboard.
"""

import os
import sys
import json
import time
import numpy as np
import torch
import nibabel as nib
from functools import partial
from skimage.measure import marching_cubes

from monai.networks.nets import SwinUNETR
from monai.inferers import sliding_window_inference
from monai.transforms import NormalizeIntensity

from nnunet_predictor import NNUNetBraTSPredictor
import uwcse_ensemble as ue

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "example_dataset")
SWIN_MODEL_PATH = os.path.join(
    BASE_DIR, "SwinUNETR_BRATS21", "pretrained_models",
    "fold0_f48_ep300_4gpu_dice0_8854", "model.pt",
)
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# ── Case definitions ──────────────────────────────────────────────────
CASES = [
    {
        "name": "UCSF-PDGM-0004",
        "dir": "1",
        "flair": "UCSF-PDGM-0004_FLAIR.nii",
        "t1": "UCSF-PDGM-0004_T1.nii",
        "t1c": "UCSF-PDGM-0004_T1c.nii",
        "t2": "UCSF-PDGM-0004_T2.nii",
        "label": "UCSF-PDGM-0004_tumor_segmentation.nii",
    },
    {
        "name": "UCSF-PDGM-0007",
        "dir": "2",
        "flair": "UCSF-PDGM-0007_FLAIR.nii",
        "t1": "UCSF-PDGM-0007_T1.nii",
        "t1c": "UCSF-PDGM-0007_T1c.nii",
        "t2": "UCSF-PDGM-0007_T2.nii",
        "label": "UCSF-PDGM-0007_tumor_segmentation.nii",
    },
]


# ── Helper functions ──────────────────────────────────────────────────
def load_mri(case, channel_order):
    """Load MRI volumes and stack them in the requested channel order."""
    mod_map = {"FLAIR": case["flair"], "T1": case["t1"],
               "T1c": case["t1c"], "T2": case["t2"]}
    vols = []
    for mod in channel_order:
        path = os.path.join(DATASET_DIR, case["dir"], mod_map[mod])
        vols.append(nib.load(path).get_fdata().astype(np.float32))
    return np.stack(vols, axis=0)            # (C, H, W, D)


def load_label(case):
    """Load ground-truth and convert to multi-channel BraTS format."""
    path = os.path.join(DATASET_DIR, case["dir"], case["label"])
    img = nib.load(path)
    lab = img.get_fdata().astype(np.float32)
    tc = ((lab == 1) | (lab == 4)).astype(np.float32)
    wt = ((lab == 1) | (lab == 2) | (lab == 4)).astype(np.float32)
    et = (lab == 4).astype(np.float32)
    return np.stack([tc, wt, et], axis=0), lab, img.affine


def normalize(image_np):
    norm = NormalizeIntensity(nonzero=True, channel_wise=True)
    return norm(torch.from_numpy(image_np))


def dice(pred, gt, eps=1e-5):
    inter = np.sum(pred * gt)
    return float((2.0 * inter + eps) / (np.sum(pred) + np.sum(gt) + eps))


def mc_to_brats(seg3):
    """3-channel binary (TC,WT,ET) → single BraTS-label volume."""
    out = np.zeros_like(seg3[0])
    out[seg3[1] == 1] = 2   # ED
    out[seg3[0] == 1] = 1   # NCR
    out[seg3[2] == 1] = 4   # ET
    return out


def make_mesh(volume, label_val, step=2):
    """Marching-cubes mesh from a label volume; returns dict or None."""
    binary = (volume == label_val).astype(np.float32)
    if binary.sum() < 10:
        return None
    try:
        v, f, _, _ = marching_cubes(binary, level=0.5, step_size=step)
        if len(v) > 50000:
            v, f, _, _ = marching_cubes(binary, level=0.5, step_size=4)
        return {"vertices": v.tolist(), "faces": f.tolist()}
    except Exception as e:
        print(f"    mesh error: {e}")
        return None


# ── Main pipeline ─────────────────────────────────────────────────────
def run():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # ── PHASE 1: Per-case inference (collect probabilities for all cases) ──
    print(f"\n{'='*60}\nPHASE 1: Inference\n{'='*60}")
    print("Loading nnU-Net (BraTS21, fold_0) ...")
    nn_predictor = NNUNetBraTSPredictor(folds=(0,), device=device)
    print("nnU-Net ready.")

    case_data = {}
    for case in CASES:
        cn = case["name"]
        cd_dir = os.path.join(RESULTS_DIR, cn)
        os.makedirs(cd_dir, exist_ok=True)
        print(f"\n[{cn}] inference ...")

        gt_mc, gt_lab, affine = load_label(case)
        flair = nib.load(os.path.join(DATASET_DIR, case["dir"], case["flair"])).get_fdata().astype(np.float32)
        np.savez_compressed(os.path.join(cd_dir, "flair.npz"), data=flair)
        np.savez_compressed(os.path.join(cd_dir, "gt_label.npz"), data=gt_lab)

        print("  nnU-Net ...")
        prob_nn = nn_predictor.predict(case, DATASET_DIR)
        torch.cuda.empty_cache()

        print("  Swin UNETR ...")
        mdl = SwinUNETR(in_channels=4, out_channels=3, feature_size=48,
                        drop_rate=0.0, attn_drop_rate=0.0,
                        dropout_path_rate=0.0, use_checkpoint=True)
        mdl.load_state_dict(
            torch.load(SWIN_MODEL_PATH, map_location="cpu",
                       weights_only=False)["state_dict"])
        mdl.eval().to(device)
        img = normalize(load_mri(case, ["FLAIR","T1c","T1","T2"])).unsqueeze(0).to(device)
        with torch.no_grad(), torch.amp.autocast("cuda"):
            p = sliding_window_inference(img, [128,128,128], 1, mdl, overlap=0.6)
            prob_sw = torch.sigmoid(p)[0].cpu().numpy()
        del mdl, img, p; torch.cuda.empty_cache()

        case_data[cn] = {
            "case": case, "dir": cd_dir,
            "prob_nn": prob_nn.astype(np.float32),
            "prob_sw": prob_sw.astype(np.float32),
            "gt_mc": gt_mc, "gt_lab": gt_lab, "affine": affine,
        }

    nn_predictor.unload()

    # ── PHASE 2: UWCSE ablation (CSW + UNC + PP) per case via LOOCV ──
    print(f"\n{'='*60}\nPHASE 2: UWCSE Ablation\n{'='*60}")
    ablation_metrics = {}
    legacy_metrics = {}

    for cn, cd in case_data.items():
        case = cd["case"]
        cd_dir = cd["dir"]
        prob_nn, prob_sw = cd["prob_nn"], cd["prob_sw"]
        gt_mc, gt_lab, affine = cd["gt_mc"], cd["gt_lab"], cd["affine"]
        print(f"\n[{cn}]")

        # LOOCV: optimize per-region weights using all OTHER cases
        loocv_w = ue.loocv_weights(case_data, cn)
        print(f"  LOOCV nnUNet weights -> TC={loocv_w[0]:.2f}  WT={loocv_w[1]:.2f}  ET={loocv_w[2]:.2f}")

        # ── ensemble variants ────────────────────────────────────────
        # V0: Naive (baseline 0.5/0.5)
        p_v0 = ue.vote_naive(prob_nn, prob_sw, 0.5)
        brats_v0 = ue.mc_to_brats((p_v0 > 0.5).astype(np.uint8))
        # V1: CSW (class-specific weights)
        p_v1 = ue.vote_class_specific(prob_nn, prob_sw, loocv_w)
        brats_v1 = ue.mc_to_brats((p_v1 > 0.5).astype(np.uint8))
        # V2: CSW + UNC (+ voxel uncertainty)
        p_v2 = ue.vote_uwcse(prob_nn, prob_sw, loocv_w)
        brats_v2 = ue.mc_to_brats((p_v2 > 0.5).astype(np.uint8))
        # V3: CSW + PP (class-specific + post-processing)
        brats_v3 = ue.postprocess_brats(brats_v1)
        # V4: UWCSE Full (CSW + UNC + PP)
        brats_v4 = ue.postprocess_brats(brats_v2)

        # Individuals
        brats_nn = ue.mc_to_brats((prob_nn > 0.5).astype(np.uint8))
        brats_sw = ue.mc_to_brats((prob_sw > 0.5).astype(np.uint8))

        variants = [
            ("nnUNet",         brats_nn),
            ("SwinUNETR",      brats_sw),
            ("V0_Naive",       brats_v0),
            ("V1_CSW",         brats_v1),
            ("V2_CSW+UNC",     brats_v2),
            ("V3_CSW+PP",      brats_v3),
            ("V4_UWCSE_Full",  brats_v4),
        ]

        # Dice scores
        rows = {}
        for name, brats in variants:
            seg_reg = ue.brats_to_regions(brats)
            d = ue.dice_regions(seg_reg, gt_mc)
            d["Mean"] = round((d["TC"] + d["WT"] + d["ET"]) / 3, 4)
            rows[name] = d
            print(f"  {name:18s} TC={d['TC']}  WT={d['WT']}  ET={d['ET']}  Mean={d['Mean']}")
        rows["_loocv_weights"] = {
            "TC": round(loocv_w[0], 3), "WT": round(loocv_w[1], 3), "ET": round(loocv_w[2], 3)
        }
        ablation_metrics[cn] = rows
        legacy_metrics[cn] = {
            "nnUNet":    rows["nnUNet"],
            "SwinUNETR": rows["SwinUNETR"],
            "Ensemble":  rows["V4_UWCSE_Full"],   # dashboard sees UWCSE Full
        }

        # NIfTI + npz + meshes (UWCSE Full as the displayed "ensemble")
        for tag, brats in [("nnunet", brats_nn), ("swin", brats_sw), ("ensemble", brats_v4)]:
            nib.save(nib.Nifti1Image(brats.astype(np.uint8), affine),
                     os.path.join(cd_dir, f"seg_{tag}.nii.gz"))

        print("  meshes ...")
        colors = {"ET":"#ff4757", "TC_NCR":"#2ed573", "ED":"#1e90ff"}
        for tag, bseg in [("nnunet", brats_nn), ("swin", brats_sw),
                          ("ensemble", brats_v4), ("gt", gt_lab)]:
            meshes = {}
            for region, lv in [("ET", 4), ("TC_NCR", 1), ("ED", 2)]:
                m = make_mesh(bseg, lv)
                if m:
                    m["color"] = colors[region]
                    meshes[region] = m
            with open(os.path.join(cd_dir, f"mesh_{tag}.json"), "w") as f:
                json.dump(meshes, f)

        np.savez_compressed(os.path.join(cd_dir, "seg_volumes.npz"),
                            nnunet=brats_nn, swin=brats_sw,
                            ensemble=brats_v4, gt=gt_lab)

    # ── Save metrics ──────────────────────────────────────────────────
    with open(os.path.join(RESULTS_DIR, "metrics.json"), "w") as f:
        json.dump(legacy_metrics, f, indent=2)
    with open(os.path.join(RESULTS_DIR, "ablation_metrics.json"), "w") as f:
        json.dump(ablation_metrics, f, indent=2)

    # ── Aggregate summary across cases ────────────────────────────────
    print(f"\n{'='*60}\nAblation summary ({len(case_data)} cases, mean Dice)\n{'='*60}")
    variant_order = ["nnUNet","SwinUNETR","V0_Naive","V1_CSW","V2_CSW+UNC","V3_CSW+PP","V4_UWCSE_Full"]
    for v in variant_order:
        m = float(np.mean([ablation_metrics[c][v]["Mean"] for c in ablation_metrics]))
        marker = " *" if v == "V4_UWCSE_Full" else ""
        print(f"  {v:18s} Mean = {m:.4f}{marker}")
    print(f"\nResults -> {RESULTS_DIR}")
    print("  metrics.json           (dashboard-compatible 3-model)")
    print("  ablation_metrics.json  (full UWCSE ablation table)")


if __name__ == "__main__":
    run()
