#!/usr/bin/env python3
"""Evaluate an ensemble of Attention-MIL checkpoints (mean of per-model probabilities).

Typical use: the seed models of ``cv_train.py --mode fixed`` on val, or the K fold models
of ``--mode kfold`` on test only. **kfold models are trained on the train+val pool, so they
have seen every locked-val patient: evaluating them on val is leakage and is refused here.**
Evaluating on the locked test split requires ``--confirm-final``:
mil_v1 already opened the test once; a second look is acceptable only for the final,
frozen ensemble and must be reported together with the first result.
Optional ``--calibration calibration.json`` applies the fitted temperature and the
abstention threshold (coverage/accuracy of the kept cases are reported).
"""

from __future__ import annotations

import argparse
import csv
import glob
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


def training_overlap(paths: list[str], split: dict, eval_ids: set[str]) -> dict:
    """For each checkpoint, which of the evaluated patients were in its training set.

    train.py writes the resolved argument list to ``config.json`` next to the checkpoint;
    ``train_patients`` is null when the run used the split file's train list.
    """
    out = {}
    for path in paths:
        cfg = Path(path).parent / "config.json"
        if not cfg.is_file():
            out[path] = {"n_overlap": None, "note": "config.json missing; training set unknown"}
            continue
        a = json.loads(cfg.read_text())["args"]
        train_ids = set(a.get("train_patients") or split["splits"]["train"])
        hit = sorted(train_ids & eval_ids)
        out[path] = {"n_train": len(train_ids), "n_overlap": len(hit), "examples": hit[:5]}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoints", nargs="+", required=True, help="paths or globs, e.g. runs/cv_v1/seed1/fold*/best.pt")
    p.add_argument("--split-name", default="val", choices=["val", "test"])
    p.add_argument("--confirm-final", action="store_true", help="required for the test split")
    p.add_argument("--allow-train-overlap", action="store_true", help="evaluate anyway when a model was trained on the evaluated patients; the result is marked invalid")
    p.add_argument("--calibration", default=None)
    p.add_argument("--split", default=str(data_root() / "pathology/splits/splits_v1.json"))
    p.add_argument("--cohort", default=str(data_root() / "pathology/datasets/tcga_glioma/manifests/cohort.tsv"))
    p.add_argument("--features-dir", default=str(data_root() / "pathology/features/dinov2_vitb14_224_0.5mpp"))
    p.add_argument("--min-tiles", type=int, default=100)
    p.add_argument("--out", required=True, help="output JSON path (a CSV is written next to it)")
    args = p.parse_args()
    if args.split_name == "test" and not args.confirm_final:
        raise SystemExit("test split: pass --confirm-final (the locked test was already evaluated once by mil_v1; only a frozen final ensemble may look again)")
    paths = sorted(q for pat in args.checkpoints for q in glob.glob(pat))
    if not paths:
        raise SystemExit("no checkpoints matched")
    split = load_split(Path(args.split))
    cohort = load_cohort(Path(args.cohort))
    labels = {pid: cohort[pid]["class"] for pid in cohort}
    ids, excluded = apply_qc(Path(args.features_dir), split["splits"][args.split_name], args.min_tiles)
    overlap = training_overlap(paths, split, set(ids))
    leaked = {k: v for k, v in overlap.items() if v.get("n_overlap")}
    if leaked and not args.allow_train_overlap:
        worst = max(leaked.values(), key=lambda v: v["n_overlap"])
        raise SystemExit(f"refusing: {len(leaked)}/{len(paths)} checkpoints were trained on patients in the '{args.split_name}' split (up to {worst['n_overlap']} of {len(ids)}). k-fold models are trained on the train+val pool, so their only clean split is test. Use --mode fixed models for val, or pass --allow-train-overlap to record a deliberately invalid number.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = []
    for path in paths:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        m = GatedAttentionMIL(**ck["model_config"]).to(device).eval()
        m.load_state_dict(ck["model"])
        models.append(m)
    cal = json.loads(Path(args.calibration).read_text()) if args.calibration else None
    T = cal["temperature"] if cal else 1.0
    threshold = cal["abstention"]["chosen_threshold"] if cal else None
    ds = FeatureBagDataset(Path(args.features_dir), ids, labels, bag_size=None, train=False)
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=2, collate_fn=collate_single)
    probs, y, pids = [], [], []
    with torch.inference_mode():
        for feats, label, pid in loader:
            feats = feats.to(device)
            acc = np.zeros(len(CLASSES))
            for m in models:
                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                    logits, _ = m(feats)
                acc += torch.softmax(logits.float() / T, 1)[0].cpu().numpy()
            probs.append(acc / len(models))
            y.append(label)
            pids.append(pid)
    probs = np.stack(probs)
    y = np.array(y)
    metrics = compute_metrics(y, probs)
    ci = bootstrap_ci(y, probs, n_boot=1000)
    result = {"checkpoints": paths, "n_models": len(paths), "split": args.split_name, "n": int(len(y)), "temperature": T, "metrics": metrics, "bootstrap_ci95": ci, "qc_excluded": excluded, "training_overlap": overlap}
    if leaked:
        result["INVALID"] = f"{len(leaked)}/{len(paths)} models were trained on patients in this split; these metrics are optimistic and must not be reported"
    if threshold is not None:
        s = np.sort(probs, axis=1)
        keep = (s[:, -1] - s[:, -2]) >= threshold
        correct = probs.argmax(1) == y
        result["abstention"] = {"threshold": threshold, "coverage": float(keep.mean()), "accuracy_kept": float(correct[keep].mean()) if keep.any() else None, "accuracy_abstained": float(correct[~keep].mean()) if (~keep).any() else None, "n_abstained": int((~keep).sum())}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    with out.with_suffix(".csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["patient_id", "label", "pred", "p_A", "p_O", "p_G"])
        for pid, lab, pr in zip(pids, y, probs):
            w.writerow([pid, CLASSES[lab], CLASSES[int(pr.argmax())], *[f"{v:.4f}" for v in pr]])
    print(json.dumps({k: v for k, v in metrics.items() if k != "confusion_matrix"}, indent=1))
    print("confusion (rows=true A,O,G):", metrics["confusion_matrix"])
    print("CI:", json.dumps(ci))
    if threshold is not None:
        print("abstention:", result["abstention"])
    print("wrote", out)


if __name__ == "__main__":
    main()
