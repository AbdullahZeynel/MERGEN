"""Slide-level metrics for the 3-class A/O/G task (all computed with scikit-learn)."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, matthews_corrcoef, precision_score, recall_score, roc_auc_score

CLASSES = ["A", "O", "G"]


def compute_metrics(labels: np.ndarray, probs: np.ndarray) -> dict:
    labels = np.asarray(labels)
    probs = np.asarray(probs, dtype=np.float64)
    probs = probs / np.clip(probs.sum(axis=1, keepdims=True), 1e-12, None)  # CSV rounding or ensembling can leave rows slightly off 1
    preds = probs.argmax(1)
    out = {
        "n": int(len(labels)),
        "accuracy": float(accuracy_score(labels, preds)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, preds)),
        "macro_f1": float(f1_score(labels, preds, average="macro", zero_division=0)),
        "mcc": float(matthews_corrcoef(labels, preds)) if len(set(labels.tolist())) > 1 else 0.0,
        "per_class_f1": {c: float(v) for c, v in zip(CLASSES, f1_score(labels, preds, average=None, labels=list(range(len(CLASSES))), zero_division=0))},
        "per_class_recall": {c: float(v) for c, v in zip(CLASSES, recall_score(labels, preds, average=None, labels=list(range(len(CLASSES))), zero_division=0))},
        "per_class_precision": {c: float(v) for c, v in zip(CLASSES, precision_score(labels, preds, average=None, labels=list(range(len(CLASSES))), zero_division=0))},
        "confusion_matrix": confusion_matrix(labels, preds, labels=list(range(len(CLASSES)))).tolist(),
    }
    try:
        out["auroc_macro_ovr"] = float(roc_auc_score(labels, probs, multi_class="ovr", average="macro", labels=list(range(len(CLASSES)))))
    except ValueError:
        out["auroc_macro_ovr"] = float("nan")
    return out


def bootstrap_ci(labels: np.ndarray, probs: np.ndarray, n_boot: int = 1000, seed: int = 0, keys=("macro_f1", "balanced_accuracy", "auroc_macro_ovr", "mcc", "accuracy")) -> dict:
    rng = np.random.default_rng(seed)
    labels = np.asarray(labels)
    probs = np.asarray(probs)
    samples = {k: [] for k in keys}
    n = len(labels)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(set(labels[idx].tolist())) < 2:
            continue
        m = compute_metrics(labels[idx], probs[idx])
        for k in keys:
            samples[k].append(m[k])
    return {k: {"ci95_low": float(np.nanpercentile(v, 2.5)), "ci95_high": float(np.nanpercentile(v, 97.5)), "n_boot": len(v)} for k, v in samples.items() if v}
