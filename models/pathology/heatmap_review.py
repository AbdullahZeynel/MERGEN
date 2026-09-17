#!/usr/bin/env python3
"""Attention-heatmap review sheet for a trained MIL checkpoint.

Picks correctly and incorrectly classified patients from a predictions CSV, recomputes
tiles + DINOv2 embeddings + attention for each slide, and writes per case:
``<pid>_attention.png`` (overlay), ``<pid>_top_tiles.png`` (the highest-attention 224 px
tiles) and one combined ``review_sheet.png`` (thumbnail | attention | top tiles, with
true/predicted class and probabilities). This is what a pathologist should look at to
judge whether the model attends to plausible regions; it is not a metric.
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
from PIL import Image
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import CLASSES, load_cohort  # noqa: E402
from extract_embeddings import load_dinov2  # noqa: E402
from model import GatedAttentionMIL  # noqa: E402
from wsi_tiles import TILE_PX, TARGET_MPP, TileDataset, normalize_batch, open_slide, overlay_values, slide_geometry, subsample_coords, tissue_coords, tissue_mask  # noqa: E402


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def montage(tiles: list[Image.Image], cols: int = 6, size: int = 224) -> Image.Image:
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * size, max(rows, 1) * size), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t.resize((size, size)), ((i % cols) * size, (i // cols) * size))
    return sheet


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--checkpoint", default="best.pt")
    p.add_argument("--predictions", default="predictions_val.csv", help="CSV inside run-dir to pick cases from (val by default)")
    p.add_argument("--n-correct", type=int, default=3)
    p.add_argument("--n-wrong", type=int, default=3)
    p.add_argument("--patients", nargs="*", default=None, help="explicit patient ids instead of automatic picks")
    p.add_argument("--max-tiles", type=int, default=4096)
    p.add_argument("--top-k", type=int, default=12)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    root = data_root()
    run_dir = Path(args.run_dir).expanduser()
    out = Path(args.out).expanduser() if args.out else run_dir / "heatmaps"
    out.mkdir(parents=True, exist_ok=True)
    cohort = load_cohort(root / "pathology/datasets/tcga_glioma/manifests/cohort.tsv")
    with (run_dir / args.predictions).open(newline="") as handle:
        preds = {r["patient_id"]: r for r in csv.DictReader(handle)}
    if args.patients:
        chosen = args.patients
    else:
        rng = np.random.default_rng(0)
        correct = [pid for pid, r in preds.items() if r["label"] == r["pred"]]
        wrong = [pid for pid, r in preds.items() if r["label"] != r["pred"]]
        chosen = list(rng.choice(correct, min(args.n_correct, len(correct)), replace=False)) + list(rng.choice(wrong, min(args.n_wrong, len(wrong)), replace=False))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = load_dinov2(root, device)
    ck = torch.load(run_dir / args.checkpoint, map_location="cpu", weights_only=False)
    head = GatedAttentionMIL(**ck["model_config"]).to(device).eval()
    head.load_state_dict(ck["model"])
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, axes = plt.subplots(len(chosen), 3, figsize=(18, 5.2 * len(chosen)))
    if len(chosen) == 1:
        axes = np.array([axes])
    summary = []
    for row_i, pid in enumerate(chosen):
        c = cohort[pid]
        slide_path = root / "pathology/datasets/tcga_glioma/raw/full" / c["file_id"] / c["file_name"]
        slide = open_slide(slide_path)
        geom = slide_geometry(slide, TARGET_MPP, TILE_PX)
        thumb, mask = tissue_mask(slide)
        coords = subsample_coords(tissue_coords(geom, mask, thumb.size), args.max_tiles, seed=0)
        loader = DataLoader(TileDataset(slide_path, coords, geom), batch_size=128, num_workers=args.workers, pin_memory=device.type == "cuda")
        feats = torch.zeros((len(coords), 768), device=device)
        with torch.inference_mode():
            for batch, idx in loader:
                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                    feats[idx.to(device)] = encoder(normalize_batch(batch.to(device))).float()
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, attention = head(feats)
        probs = torch.softmax(logits.float(), 1)[0].cpu().numpy()
        attn = attention.float().cpu().numpy()
        norm = (attn - attn.min()) / (attn.max() - attn.min() + 1e-12)
        overlay = overlay_values(thumb, coords, norm, geom, alpha=0.6)
        overlay.save(out / f"{pid}_attention.png")
        top = np.argsort(attn)[::-1][: args.top_k]
        tiles = []
        for i in top:
            x0, y0 = coords[i]
            tiles.append(slide.read_region((int(x0), int(y0)), geom["level"], (geom["read_px"], geom["read_px"])).convert("RGB"))
        slide.close()
        sheet = montage(tiles)
        sheet.save(out / f"{pid}_top_tiles.png")
        pred = CLASSES[int(probs.argmax())]
        rec = {"patient_id": pid, "true": c["class"], "pred_now": pred, "pred_in_csv": preds.get(pid, {}).get("pred"), "grade": c["grade"], "site": c["tissue_source_site"], "probs": {k: round(float(v), 3) for k, v in zip(CLASSES, probs)}, "n_tiles": len(coords), "attention_top1_share": round(float(attn.max()), 4), "attention_top10_share": round(float(np.sort(attn)[::-1][:10].sum()), 4), "attention_entropy_norm": round(float(-(attn * np.log(attn + 1e-12)).sum() / np.log(len(attn))), 4)}
        summary.append(rec)
        axes[row_i, 0].imshow(thumb)
        axes[row_i, 0].set_title(f"{pid} | gerçek {c['class']} → tahmin {pred} ({'DOĞRU' if pred == c['class'] else 'YANLIŞ'}) | grade {c['grade']} | {c['tissue_source_site']}", fontsize=9)
        axes[row_i, 1].imshow(overlay)
        axes[row_i, 1].set_title(f"attention (kırmızı = yüksek) | p A {probs[0]:.2f} O {probs[1]:.2f} G {probs[2]:.2f} | {len(coords)} kare | top-10 kare payı {rec['attention_top10_share']:.2f}", fontsize=9)
        axes[row_i, 2].imshow(sheet)
        axes[row_i, 2].set_title(f"en yüksek attention'lı {len(tiles)} kare (224 px, 0,5 µm/px)", fontsize=9)
        for ax in axes[row_i]:
            ax.axis("off")
        print(json.dumps(rec))
    fig.tight_layout()
    fig.savefig(out / "review_sheet.png", dpi=110)
    (out / "review_summary.json").write_text(json.dumps({"checkpoint": str(run_dir / args.checkpoint), "cases": summary}, indent=2) + "\n")
    print("wrote", out / "review_sheet.png")


if __name__ == "__main__":
    main()
