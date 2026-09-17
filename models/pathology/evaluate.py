#!/usr/bin/env python3
"""Evaluate a trained checkpoint on the locked val or test split.

Writes ``<run_dir>/eval_<split>.json`` (metrics + bootstrap 95% CI), a per-patient
prediction CSV and a confusion-matrix PNG. The test split should be evaluated once,
with the checkpoint chosen on validation, and reported as-is.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import CLASSES, FeatureBagDataset, apply_qc, collate_single, load_cohort, load_split  # noqa: E402
from metrics import bootstrap_ci, compute_metrics  # noqa: E402
from model import GatedAttentionMIL  # noqa: E402


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--checkpoint", default="best.pt")
    p.add_argument("--split-name", default="val", choices=["val", "test", "train"])
    p.add_argument("--split", default=str(data_root() / "pathology/splits/splits_v1.json"))
    p.add_argument("--cohort", default=str(data_root() / "pathology/datasets/tcga_glioma/manifests/cohort.tsv"))
    p.add_argument("--features-dir", default=str(data_root() / "pathology/features/dinov2_vitb14_224_0.5mpp"))
    p.add_argument("--patients", nargs="*", default=None)
    p.add_argument("--n-boot", type=int, default=1000)
    p.add_argument("--min-tiles", type=int, default=100, help="QC: same exclusion rule as training")
    args = p.parse_args()
    run_dir = Path(args.run_dir).expanduser()
    ck = torch.load(run_dir / args.checkpoint, map_location="cpu", weights_only=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = GatedAttentionMIL(**ck["model_config"]).to(device)
    model.load_state_dict(ck["model"])
    model.eval()
    cohort = load_cohort(Path(args.cohort))
    labels = {pid: cohort[pid]["class"] for pid in cohort}
    ids = args.patients or load_split(Path(args.split))["splits"][args.split_name]
    ids, excluded = apply_qc(Path(args.features_dir), ids, args.min_tiles)
    if excluded:
        print(f"QC excluded {len(excluded)} slides: " + ", ".join(f"{k} [{v}]" for k, v in excluded.items()))
    ds = FeatureBagDataset(Path(args.features_dir), ids, labels, bag_size=None, train=False)
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=2, collate_fn=collate_single)
    probs, y, pids, n_tiles = [], [], [], []
    with torch.inference_mode():
        for feats, label, pid in loader:
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, _ = model(feats.to(device))
            probs.append(torch.softmax(logits.float(), 1)[0].cpu().numpy())
            y.append(label)
            pids.append(pid)
            n_tiles.append(int(feats.shape[0]))
    probs = np.stack(probs)
    y = np.array(y)
    metrics = compute_metrics(y, probs)
    ci = bootstrap_ci(y, probs, n_boot=args.n_boot) if len(y) >= 10 else {}
    payload = {"run_dir": str(run_dir), "checkpoint": args.checkpoint, "checkpoint_epoch": ck.get("epoch"), "split": args.split_name, "n": len(y), "metrics": metrics, "bootstrap_ci95": ci, "classes": CLASSES, "qc_min_tiles": args.min_tiles, "qc_excluded": excluded}
    (run_dir / f"eval_{args.split_name}.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (run_dir / f"predictions_{args.split_name}.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["patient_id", "label", "pred", "p_A", "p_O", "p_G", "n_tiles"])
        for pid, lab, pr, nt in zip(pids, y, probs, n_tiles):
            w.writerow([pid, CLASSES[lab], CLASSES[int(pr.argmax())], *[f"{v:.4f}" for v in pr], nt])
    try:
        import matplotlib  # noqa: PLC0415

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415

        cm = np.array(metrics["confusion_matrix"])
        fig, ax = plt.subplots(figsize=(4.2, 3.8))
        ax.imshow(cm, cmap="Blues")
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center", color="black" if cm[i, j] < cm.max() / 2 else "white")
        ax.set_xticks(range(3), CLASSES)
        ax.set_yticks(range(3), CLASSES)
        ax.set_xlabel("tahmin")
        ax.set_ylabel("gerçek")
        ax.set_title(f"{args.split_name}: macro-F1 {metrics['macro_f1']:.3f}, BA {metrics['balanced_accuracy']:.3f}, AUROC {metrics['auroc_macro_ovr']:.3f}", fontsize=9)
        fig.tight_layout()
        fig.savefig(run_dir / f"confusion_{args.split_name}.png", dpi=150)
    except Exception as exc:  # noqa: BLE001
        print("plot skipped:", exc)
    print(json.dumps({k: v for k, v in metrics.items() if k != "confusion_matrix"}, indent=1))
    print("confusion (rows=true A,O,G):", metrics["confusion_matrix"])
    print("bootstrap:", json.dumps(ci))


if __name__ == "__main__":
    main()
