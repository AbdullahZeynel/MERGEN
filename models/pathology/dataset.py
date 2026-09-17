"""Feature-bag dataset for MIL training.

Each patient has one ``<features_dir>/<patient_id>.npz`` written by
``extract_embeddings.py`` with ``feats`` (N × 768 float16), ``coords`` (N × 2 int32) and
``meta`` (JSON string). Training bags are a fresh random subset of at most ``bag_size``
tiles every epoch (acts as augmentation); evaluation uses all stored tiles.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

CLASSES = ["A", "O", "G"]
CLASS_INDEX = {c: i for i, c in enumerate(CLASSES)}


def load_cohort(path: Path) -> dict[str, dict]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return {r["patient_id"]: r for r in csv.DictReader(handle, delimiter="\t")}


def load_split(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def split_hash(split: dict) -> str:
    return hashlib.sha256(json.dumps(split["splits"], sort_keys=True).encode()).hexdigest()[:16]


def feature_path(features_dir: Path, patient_id: str) -> Path:
    return Path(features_dir) / f"{patient_id}.npz"


def available_patients(features_dir: Path, patient_ids: list[str]) -> list[str]:
    return [p for p in patient_ids if feature_path(features_dir, p).is_file()]


def tile_counts(features_dir: Path, patient_ids: list[str]) -> dict[str, int]:
    counts = {}
    for pid in patient_ids:
        path = feature_path(features_dir, pid)
        if path.is_file():
            with np.load(path) as z:
                counts[pid] = int(z["feats"].shape[0])
    return counts


def apply_qc(features_dir: Path, patient_ids: list[str], min_tiles: int) -> tuple[list[str], dict[str, str]]:
    """Return (kept ids, {excluded id: reason}). Slides without features (no tissue found)
    or with fewer than ``min_tiles`` stored tiles are excluded — faint or nearly empty
    scans would form degenerate bags."""
    counts = tile_counts(features_dir, patient_ids)
    kept, excluded = [], {}
    for pid in patient_ids:
        if pid not in counts:
            excluded[pid] = "no_features (no tissue detected)"
        elif counts[pid] < min_tiles:
            excluded[pid] = f"low_tissue ({counts[pid]} tiles < {min_tiles})"
        else:
            kept.append(pid)
    return kept, excluded


class FeatureBagDataset(Dataset):
    def __init__(self, features_dir: Path, patient_ids: list[str], labels: dict[str, str], bag_size: int | None, train: bool, seed: int = 0, max_eval_tiles: int | None = None):
        self.features_dir = Path(features_dir)
        self.patient_ids = list(patient_ids)
        self.labels = labels
        self.bag_size = bag_size
        self.train = train
        self.max_eval_tiles = max_eval_tiles
        self.epoch = 0
        self.seed = seed

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __len__(self):
        return len(self.patient_ids)

    def __getitem__(self, idx):
        pid = self.patient_ids[idx]
        with np.load(feature_path(self.features_dir, pid)) as z:
            feats = z["feats"]
            n = feats.shape[0]
            cap = self.bag_size if self.train else self.max_eval_tiles
            if cap is not None and n > cap:
                rng = np.random.default_rng((self.seed * 1_000_003 + self.epoch) * 7_919 + idx if self.train else self.seed + idx)
                sel = np.sort(rng.choice(n, size=cap, replace=False))
                feats = feats[sel]
            feats = torch.from_numpy(np.asarray(feats, dtype=np.float32))
        return feats, CLASS_INDEX[self.labels[pid]], pid


def class_weights(labels: list[str]) -> torch.Tensor:
    counts = np.array([sum(1 for l in labels if l == c) for c in CLASSES], dtype=np.float64)
    weights = counts.sum() / (len(CLASSES) * np.maximum(counts, 1))
    return torch.tensor(weights, dtype=torch.float32)


def collate_single(batch):
    """Bags have different sizes; batch size is 1 so just unwrap."""
    assert len(batch) == 1
    return batch[0]
