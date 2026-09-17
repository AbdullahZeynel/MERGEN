#!/usr/bin/env python3
"""Temperature scaling + abstention threshold, fitted on validation predictions only.

Input: a predictions CSV written by ``evaluate.py`` (columns label, p_A, p_O, p_G). The
softmax probabilities are converted back to log-probabilities (logits up to a constant),
a single temperature T is fitted by minimising the negative log-likelihood, and expected
calibration error (ECE, 15 bins) and Brier score are reported before/after. Then the
top-2 probability gap is swept to find the abstention threshold that keeps at least
``--min-coverage`` of cases while maximising accuracy on the kept cases.

Output ``calibration.json`` is consumed by ``infer_slide.py --calibration`` and
``ensemble_eval.py --calibration``. Fit on val; report on test only once, explicitly.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

CLASSES = ["A", "O", "G"]


def load(path: Path):
    with Path(path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    probs = np.array([[float(r["p_A"]), float(r["p_O"]), float(r["p_G"])] for r in rows])
    labels = np.array([CLASSES.index(r["label"]) for r in rows])
    return rows, probs, labels


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def nll(probs, labels):
    return float(-np.mean(np.log(np.clip(probs[np.arange(len(labels)), labels], 1e-12, 1))))


def ece(probs, labels, bins=15):
    conf = probs.max(1)
    pred = probs.argmax(1)
    acc = (pred == labels).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(acc[m].mean() - conf[m].mean())
    return float(total)


def brier(probs, labels):
    onehot = np.eye(probs.shape[1])[labels]
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def fit_temperature(logits, labels):
    grid = np.concatenate([np.linspace(0.3, 1.0, 36), np.linspace(1.0, 10.0, 181)])
    scores = [nll(softmax(logits / t), labels) for t in grid]
    t0 = grid[int(np.argmin(scores))]
    fine = np.linspace(max(0.2, t0 - 0.1), t0 + 0.1, 41)
    scores = [nll(softmax(logits / t), labels) for t in fine]
    return float(fine[int(np.argmin(scores))])


def sweep(probs, labels, min_coverage: float):
    s = np.sort(probs, axis=1)
    gap = s[:, -1] - s[:, -2]
    correct = probs.argmax(1) == labels
    table = []
    for thr in np.round(np.arange(0.0, 0.95, 0.05), 2):
        keep = gap >= thr
        table.append({"threshold": float(thr), "coverage": float(keep.mean()), "accuracy_kept": float(correct[keep].mean()) if keep.any() else None, "accuracy_abstained": float(correct[~keep].mean()) if (~keep).any() else None, "n_abstained": int((~keep).sum())})
    eligible = [t for t in table if t["coverage"] >= min_coverage and t["accuracy_kept"] is not None]
    best = max(eligible, key=lambda t: (t["accuracy_kept"], t["coverage"])) if eligible else table[0]
    return table, best


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--predictions", required=True, help="validation predictions CSV (evaluate.py output)")
    p.add_argument("--out", required=True, help="calibration.json path")
    p.add_argument("--min-coverage", type=float, default=0.85)
    p.add_argument("--apply", default=None, help="optional second CSV (e.g. test predictions) to report calibrated metrics on; use only once")
    args = p.parse_args()
    rows, probs, labels = load(Path(args.predictions))
    logits = np.log(np.clip(probs, 1e-12, 1))
    T = fit_temperature(logits, labels)
    cal = softmax(logits / T)
    before = {"nll": nll(probs, labels), "ece": ece(probs, labels), "brier": brier(probs, labels), "mean_confidence": float(probs.max(1).mean()), "accuracy": float((probs.argmax(1) == labels).mean())}
    after = {"nll": nll(cal, labels), "ece": ece(cal, labels), "brier": brier(cal, labels), "mean_confidence": float(cal.max(1).mean()), "accuracy": float((cal.argmax(1) == labels).mean())}
    table, best = sweep(cal, labels, args.min_coverage)
    out = {"fitted_on": str(args.predictions), "n": int(len(labels)), "temperature": T, "before": before, "after": after, "abstention": {"metric": "top2_gap_on_calibrated_probs", "min_coverage": args.min_coverage, "chosen_threshold": best["threshold"], "chosen": best, "sweep": table}, "classes": CLASSES, "note": "Temperature and threshold were chosen on the validation split; report test behaviour only once."}
    if args.apply:
        rows2, probs2, labels2 = load(Path(args.apply))
        cal2 = softmax(np.log(np.clip(probs2, 1e-12, 1)) / T)
        s = np.sort(cal2, axis=1)
        keep = (s[:, -1] - s[:, -2]) >= best["threshold"]
        correct = cal2.argmax(1) == labels2
        out["applied_to"] = {"file": str(args.apply), "n": int(len(labels2)), "ece_before": ece(probs2, labels2), "ece_after": ece(cal2, labels2), "nll_before": nll(probs2, labels2), "nll_after": nll(cal2, labels2), "coverage": float(keep.mean()), "accuracy_kept": float(correct[keep].mean()) if keep.any() else None, "accuracy_abstained": float(correct[~keep].mean()) if (~keep).any() else None, "accuracy_all": float(correct.mean())}
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("temperature", "before", "after")}, indent=1))
    print("abstention threshold:", best)
    if args.apply:
        print("applied:", json.dumps(out["applied_to"], indent=1))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
