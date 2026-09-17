#!/usr/bin/env python3
"""Single-slide inference: .svs → tissue tiles → DINOv2 embeddings → Attention-MIL →
A/O/G probabilities + attention heatmap PNG + JSON. This is the inference contract the
backend will call; it never trains and never touches the split files.

``--checkpoint`` accepts one or more paths/globs. The shipped model is the 5-fold ensemble,
so the probabilities are the mean over the fold models and the heatmap is the mean of their
per-model min-max normalised attention.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import glob
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import CLASSES  # noqa: E402
from extract_embeddings import load_dinov2  # noqa: E402
from model import GatedAttentionMIL  # noqa: E402
from wsi_tiles import TILE_PX, TARGET_MPP, TileDataset, normalize_batch, open_slide, overlay_values, slide_geometry, subsample_coords, tissue_coords, tissue_mask  # noqa: E402


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slide", required=True)
    p.add_argument("--checkpoint", required=True, nargs="+", help="one or more checkpoints or globs; probabilities are averaged over them")
    p.add_argument("--out", required=True)
    p.add_argument("--max-tiles", type=int, default=8192)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--uncertain-margin", type=float, default=0.15, help="flag for expert review when top-2 probability gap is below this")
    p.add_argument("--calibration", default=None, help="calibration.json from calibrate.py: applies temperature and its abstention threshold")
    args = p.parse_args()
    calibration = json.loads(Path(args.calibration).read_text()) if args.calibration else None
    temperature = calibration["temperature"] if calibration else 1.0
    if calibration:
        args.uncertain_margin = calibration["abstention"]["chosen_threshold"]
    root = data_root()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    t0 = time.time()
    encoder = load_dinov2(root, device)
    ck_paths = sorted({q for pat in args.checkpoint for q in (glob.glob(pat) or [pat])})
    if not ck_paths:
        raise SystemExit("no checkpoints matched")
    heads, ck = [], None
    for path in ck_paths:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        h = GatedAttentionMIL(**ck["model_config"]).to(device).eval()
        h.load_state_dict(ck["model"])
        heads.append(h)
    slide = open_slide(args.slide)
    geom = slide_geometry(slide, TARGET_MPP, TILE_PX)
    thumb, mask = tissue_mask(slide)
    coords = subsample_coords(tissue_coords(geom, mask, thumb.size), args.max_tiles, seed=0)
    slide.close()
    if not coords:
        raise SystemExit("no tissue found; refusing to produce a prediction")
    loader = DataLoader(TileDataset(args.slide, coords, geom), batch_size=args.batch, num_workers=args.workers, pin_memory=device.type == "cuda")
    feats = torch.zeros((len(coords), 768), dtype=torch.float32, device=device)
    with torch.inference_mode():
        for batch, idx in loader:
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                feats[idx.to(device)] = encoder(normalize_batch(batch.to(device))).float()
        probs_sum = np.zeros(len(CLASSES))
        attn_sum = np.zeros(len(coords))
        for h in heads:
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, attention = h(feats)
            probs_sum += torch.softmax(logits.float() / temperature, 1)[0].cpu().numpy()
            a = attention.float().cpu().numpy()
            attn_sum += (a - a.min()) / (a.max() - a.min() + 1e-12)
    probs = probs_sum / len(heads)
    attn = attn_sum / len(heads)
    order = np.argsort(probs)[::-1]
    gap = float(probs[order[0]] - probs[order[1]])
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.slide).name.split(".")[0]
    norm = (attn - attn.min()) / (attn.max() - attn.min() + 1e-12)  # attn is already the mean of per-model normalised maps
    overlay_values(thumb, coords, norm, geom).save(out / f"{stem}_attention.png")
    thumb.save(out / f"{stem}_thumbnail.png")
    result = {"slide": Path(args.slide).name, "kind": "predicted", "classes": CLASSES, "probabilities": {c: round(float(v), 4) for c, v in zip(CLASSES, probs)}, "predicted_class": CLASSES[int(order[0])], "top2_gap": round(gap, 4), "needs_expert_review": gap < args.uncertain_margin, "uncertainty_threshold": args.uncertain_margin, "calibration": {"file": args.calibration, "temperature": temperature} if calibration else None, "n_tiles": len(coords), "geometry": geom, "checkpoints": ck_paths, "n_models": len(heads), "ensemble": len(heads) > 1, "encoder": "dinov2_vitb14", "seconds": round(time.time() - t0, 1), "gpu_peak_mib": round(torch.cuda.max_memory_allocated() / 2**20) if device.type == "cuda" else None, "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "note": "Model output on H&E; not a molecular test result."}
    (out / f"{stem}_prediction.json").write_text(json.dumps(result, indent=2) + "\n")
    np.save(out / f"{stem}_attention.npy", np.column_stack([np.asarray(coords, dtype=np.int32), attn.astype(np.float32)[:, None]]))
    print(json.dumps({k: result[k] for k in ("predicted_class", "probabilities", "top2_gap", "needs_expert_review", "n_tiles", "seconds")}, indent=1))


if __name__ == "__main__":
    main()
