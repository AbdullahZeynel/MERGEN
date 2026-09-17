#!/usr/bin/env python3
"""Repeated training for variance estimates: seed repeats on the locked split, or
K-fold cross-validation on the train+val pool. The locked test split is never used.

Modes
  --mode fixed  : train on the locked train split, evaluate on the locked val split,
                  once per seed (default seeds 1..5). Reports mean ± std over seeds and
                  a seed-ensemble (mean probability) score on val.
  --mode kfold  : stratified (class × grade) K-fold over train+val (647 patients minus
                  QC exclusions). Every patient is predicted exactly once by a model that
                  never saw it (out-of-fold, OOF); reports per-fold mean ± std and the
                  pooled OOF metrics with bootstrap CI.

Each (seed, fold) run is a normal ``train.py`` run directory (checkpoints, logs, resume),
so an interrupted sweep continues where it stopped: finished runs are skipped.
Outputs: ``<run_root>/cv_summary.json`` and ``oof_predictions_seed<S>.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import CLASSES, CLASS_INDEX, apply_qc, load_cohort, load_split  # noqa: E402
from metrics import bootstrap_ci, compute_metrics  # noqa: E402

HERE = Path(__file__).resolve().parent


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def stratified_folds(ids: list[str], cohort: dict, k: int, seed: int) -> list[list[str]]:
    rng = np.random.default_rng(seed)
    groups = defaultdict(list)
    for pid in ids:
        groups[(cohort[pid]["class"], cohort[pid].get("grade") or "NA")].append(pid)
    folds = [[] for _ in range(k)]
    offset = 0
    for key in sorted(groups):
        members = sorted(groups[key])
        rng.shuffle(members)
        for i, pid in enumerate(members):
            folds[(i + offset) % k].append(pid)
        offset += len(members)
    return [sorted(f) for f in folds]


def read_predictions(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def metrics_from_rows(rows: list[dict]) -> tuple[dict, dict]:
    labels = np.array([CLASS_INDEX[r["label"]] for r in rows])
    probs = np.array([[float(r["p_A"]), float(r["p_O"]), float(r["p_G"])] for r in rows])
    return compute_metrics(labels, probs), bootstrap_ci(labels, probs, n_boot=1000)


def run_one(run_dir: Path, train_ids: list[str], val_ids: list[str], seed: int, args, py: str) -> dict:
    if (run_dir / "best_metrics.json").is_file() and (run_dir / "predictions_val.csv").is_file():
        print(f"skip (done): {run_dir}")
    else:
        cmd = [py, str(HERE / "train.py"), "--run-dir", str(run_dir), "--split", args.split, "--features-dir", args.features_dir, "--epochs", str(args.epochs), "--bag-size", str(args.bag_size), "--patience", str(args.patience), "--min-tiles", str(args.min_tiles), "--seed", str(seed), "--workers", str(args.workers), "--allow-missing-features", "--resume", "auto", "--train-patients", *train_ids, "--val-patients", *val_ids]
        subprocess.run(cmd, check=True)
        subprocess.run([py, str(HERE / "evaluate.py"), "--run-dir", str(run_dir), "--split-name", "val", "--features-dir", args.features_dir, "--split", args.split, "--min-tiles", str(args.min_tiles), "--patients", *val_ids, "--n-boot", "200"], check=True)
    ev = json.loads((run_dir / "eval_val.json").read_text())
    return {"run_dir": str(run_dir), "n_val": ev["n"], "best_epoch": ev.get("checkpoint_epoch"), "metrics": {k: ev["metrics"][k] for k in ("macro_f1", "balanced_accuracy", "auroc_macro_ovr", "mcc", "accuracy")}}


def summarize(runs: list[dict]) -> dict:
    keys = ("macro_f1", "balanced_accuracy", "auroc_macro_ovr", "mcc", "accuracy")
    return {k: {"mean": float(np.mean([r["metrics"][k] for r in runs])), "std": float(np.std([r["metrics"][k] for r in runs], ddof=1)) if len(runs) > 1 else 0.0, "values": [round(r["metrics"][k], 4) for r in runs]} for k in keys}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["fixed", "kfold"], default="kfold")
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5], help="seeds; in kfold mode each seed is a full K-fold repetition")
    p.add_argument("--run-root", default=None)
    p.add_argument("--split", default=str(data_root() / "pathology/splits/splits_v1.json"))
    p.add_argument("--cohort", default=str(data_root() / "pathology/datasets/tcga_glioma/manifests/cohort.tsv"))
    p.add_argument("--features-dir", default=str(data_root() / "pathology/features/dinov2_vitb14_224_0.5mpp"))
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--bag-size", type=int, default=4096)
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--min-tiles", type=int, default=100)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    py = sys.executable
    split = load_split(Path(args.split))
    cohort = load_cohort(Path(args.cohort))
    features_dir = Path(args.features_dir)
    run_root = Path(args.run_root or data_root() / "pathology/runs" / ("seeds_v1" if args.mode == "fixed" else "cv_v1"))
    run_root.mkdir(parents=True, exist_ok=True)
    summary = {"mode": args.mode, "seeds": args.seeds, "folds": args.folds if args.mode == "kfold" else 1, "hyperparameters": {"epochs": args.epochs, "bag_size": args.bag_size, "patience": args.patience, "min_tiles": args.min_tiles}, "test_split_used": False, "runs": [], "per_seed": {}}
    if args.mode == "fixed":
        train_ids, exc_tr = apply_qc(features_dir, split["splits"]["train"], args.min_tiles)
        val_ids, exc_va = apply_qc(features_dir, split["splits"]["val"], args.min_tiles)
        summary["qc_excluded"] = {**exc_tr, **exc_va}
        runs = []
        prob_sum = defaultdict(lambda: np.zeros(3))
        labels_by_pid = {}
        for s in args.seeds:
            r = run_one(run_root / f"seed{s}", train_ids, val_ids, s, args, py)
            r["seed"] = s
            runs.append(r)
            for row in read_predictions(Path(r["run_dir"]) / "predictions_val.csv"):
                prob_sum[row["patient_id"]] += np.array([float(row["p_A"]), float(row["p_O"]), float(row["p_G"])])
                labels_by_pid[row["patient_id"]] = row["label"]
        summary["runs"] = runs
        summary["over_seeds"] = summarize(runs)
        pids = sorted(prob_sum)
        ens_rows = [{"patient_id": pid, "label": labels_by_pid[pid], **{f"p_{c}": prob_sum[pid][i] / len(args.seeds) for i, c in enumerate(CLASSES)}} for pid in pids]
        m, ci = metrics_from_rows(ens_rows)
        summary["seed_ensemble_val"] = {"metrics": {k: m[k] for k in ("macro_f1", "balanced_accuracy", "auroc_macro_ovr", "mcc", "accuracy")}, "confusion_matrix": m["confusion_matrix"], "bootstrap_ci95": ci}
        with (run_root / "seed_ensemble_val_predictions.csv").open("w", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(["patient_id", "label", "pred", "p_A", "p_O", "p_G"])
            for r in ens_rows:
                pr = [r["p_A"], r["p_O"], r["p_G"]]
                w.writerow([r["patient_id"], r["label"], CLASSES[int(np.argmax(pr))], *[f"{v:.4f}" for v in pr]])
    else:
        pool_ids = split["splits"]["train"] + split["splits"]["val"]
        pool_ids, exc = apply_qc(features_dir, pool_ids, args.min_tiles)
        summary["qc_excluded"] = exc
        summary["pool_size"] = len(pool_ids)
        for s in args.seeds:
            folds = stratified_folds(pool_ids, cohort, args.folds, seed=s)
            seed_runs = []
            oof = []
            for f in range(args.folds):
                val_ids = folds[f]
                train_ids = sorted(pid for g in range(args.folds) if g != f for pid in folds[g])
                r = run_one(run_root / f"seed{s}" / f"fold{f}", train_ids, val_ids, s * 100 + f, args, py)
                r.update({"seed": s, "fold": f, "n_train": len(train_ids)})
                seed_runs.append(r)
                oof += read_predictions(Path(r["run_dir"]) / "predictions_val.csv")
            m, ci = metrics_from_rows(oof)
            with (run_root / f"oof_predictions_seed{s}.csv").open("w", newline="") as handle:
                w = csv.DictWriter(handle, fieldnames=list(oof[0].keys()))
                w.writeheader()
                w.writerows(oof)
            summary["runs"] += seed_runs
            summary["per_seed"][str(s)] = {"per_fold": summarize(seed_runs), "oof": {"n": len(oof), "metrics": {k: m[k] for k in ("macro_f1", "balanced_accuracy", "auroc_macro_ovr", "mcc", "accuracy")}, "per_class_f1": m["per_class_f1"], "confusion_matrix": m["confusion_matrix"], "bootstrap_ci95": ci}}
            (run_root / "cv_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        if len(args.seeds) > 1:
            summary["over_seeds_oof"] = {k: {"mean": float(np.mean([summary["per_seed"][str(s)]["oof"]["metrics"][k] for s in args.seeds])), "std": float(np.std([summary["per_seed"][str(s)]["oof"]["metrics"][k] for s in args.seeds], ddof=1))} for k in ("macro_f1", "balanced_accuracy", "auroc_macro_ovr", "mcc", "accuracy")}
    (run_root / "cv_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("\n==== SUMMARY ====")
    if args.mode == "fixed":
        for k, v in summary["over_seeds"].items():
            print(f"{k:<20} {v['mean']:.4f} ± {v['std']:.4f}  {v['values']}")
        e = summary["seed_ensemble_val"]
        print("seed-ensemble val:", {k: round(v, 4) for k, v in e["metrics"].items()}, "CI macro-F1", {k: round(v, 3) for k, v in e["bootstrap_ci95"].get("macro_f1", {}).items()})
    else:
        for s in args.seeds:
            ps = summary["per_seed"][str(s)]
            print(f"seed {s}: per-fold macro-F1 {ps['per_fold']['macro_f1']['mean']:.4f} ± {ps['per_fold']['macro_f1']['std']:.4f} | OOF n={ps['oof']['n']} macro-F1 {ps['oof']['metrics']['macro_f1']:.4f} BA {ps['oof']['metrics']['balanced_accuracy']:.4f} AUROC {ps['oof']['metrics']['auroc_macro_ovr']:.4f} MCC {ps['oof']['metrics']['mcc']:.4f} | CI macro-F1 {ps['oof']['bootstrap_ci95'].get('macro_f1', {})}")
        if "over_seeds_oof" in summary:
            print("over seeds (OOF):", {k: f"{v['mean']:.4f} ± {v['std']:.4f}" for k, v in summary["over_seeds_oof"].items()})
    print("wrote", run_root / "cv_summary.json")


if __name__ == "__main__":
    main()
