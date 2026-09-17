#!/usr/bin/env python3
"""Resumable DINOv2 embedding extraction for the TCGA glioma cohort.

For every patient in the cohort (optionally restricted to a split) the slide is opened
with OpenSlide, tissue tiles are found at 0.5 µm/px, at most ``--max-tiles`` are kept
(uniform random subsample, seeded per patient), tiles are decoded by ``--workers``
DataLoader workers and embedded by the frozen DINOv2 ViT-B/14 in bf16. Output per
patient: ``<features_dir>/<patient_id>.npz`` (feats float16 N×768, coords int32 N×2,
meta JSON). Files are written to a temporary name and renamed atomically, existing
complete files are skipped, so the job can be killed and restarted at any time.
Progress: a tqdm bar on the terminal, ``manifest.jsonl`` (one line per slide) and
``status.json`` (counts, throughput, ETA) in the features directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import load_cohort, load_split  # noqa: E402
from wsi_tiles import TILE_PX, TARGET_MPP, TileDataset, normalize_batch, open_slide, slide_geometry, subsample_coords, tissue_coords, tissue_mask  # noqa: E402


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def load_dinov2(root: Path, device):
    sys.path.insert(0, str(root / "models/dinov2-vitb14/src"))
    from dinov2.models.vision_transformer import vit_base  # noqa: PLC0415

    model = vit_base(patch_size=14, img_size=518, init_values=1.0, block_chunks=0)
    state = torch.load(str(root / "models/dinov2-vitb14/dinov2_vitb14_pretrain.pth"), map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    return model.to(device).eval()


def is_complete(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with np.load(path) as z:
            return "feats" in z and z["feats"].shape[0] > 0
    except Exception:  # noqa: BLE001 - corrupt file → redo
        return False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", default=str(data_root() / "pathology/datasets/tcga_glioma/manifests/cohort.tsv"))
    p.add_argument("--split", default=None, help="splits.json; process train, val, test in that order")
    p.add_argument("--patients", nargs="*", default=None, help="explicit patient ids (overrides split)")
    p.add_argument("--features-dir", default=str(data_root() / "pathology/features/dinov2_vitb14_224_0.5mpp"))
    p.add_argument("--max-tiles", type=int, default=8192)
    p.add_argument("--min-tissue", type=float, default=0.6)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--limit", type=int, default=None, help="stop after this many newly processed slides")
    p.add_argument("--seed", type=int, default=20260914)
    args = p.parse_args()
    root = data_root()
    cohort = load_cohort(Path(args.cohort))
    if args.patients:
        order = args.patients
    elif args.split:
        s = load_split(Path(args.split))["splits"]
        order = s["train"] + s["val"] + s["test"]
    else:
        order = sorted(cohort)
    features_dir = Path(args.features_dir).expanduser()
    features_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_dinov2(root, device)
    stop = {"flag": False}

    def handle(signum, frame):  # finish the current slide, then stop
        stop["flag"] = True
        tqdm.write(f"signal {signum}: finishing current slide then exiting")

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)
    pending = [pid for pid in order if not is_complete(features_dir / f"{pid}.npz")]
    done_before = len(order) - len(pending)
    tqdm.write(f"{len(order)} slides in scope, {done_before} already done, {len(pending)} pending")
    manifest = (features_dir / "manifest.jsonl").open("a")
    processed = 0
    t_start = time.time()
    tile_seconds = []
    for pid in tqdm(pending, desc="slides", unit="slide"):
        if stop["flag"] or (args.limit is not None and processed >= args.limit):
            break
        row = cohort[pid]
        slide_path = root / "pathology/datasets/tcga_glioma/raw/full" / row["file_id"] / row["file_name"]
        t0 = time.time()
        slide = open_slide(slide_path)
        geom = slide_geometry(slide, TARGET_MPP, TILE_PX)
        thumb, mask = tissue_mask(slide)
        coords_all = tissue_coords(geom, mask, thumb.size, args.min_tissue)
        coords = subsample_coords(coords_all, args.max_tiles, args.seed + int.from_bytes(pid.encode()[-4:], "little"))
        slide.close()
        if not coords:
            manifest.write(json.dumps({"patient_id": pid, "status": "no_tissue", "time": dt.datetime.now().isoformat()}) + "\n")
            manifest.flush()
            continue
        ds = TileDataset(slide_path, coords, geom)
        loader = DataLoader(ds, batch_size=args.batch, num_workers=args.workers, pin_memory=device.type == "cuda", persistent_workers=False)
        feats = np.zeros((len(coords), 768), dtype=np.float16)
        with torch.inference_mode():
            for batch, idx in tqdm(loader, desc=pid, leave=False, unit="batch"):
                x = normalize_batch(batch.to(device, non_blocking=True))
                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                    emb = model(x)
                feats[idx.numpy()] = emb.float().cpu().numpy().astype(np.float16)
        seconds = time.time() - t0
        meta = {"patient_id": pid, "class": row["class"], "slide": row["file_name"], "geometry": geom, "tissue_tiles_total": len(coords_all), "tiles_stored": len(coords), "max_tiles": args.max_tiles, "min_tissue": args.min_tissue, "encoder": "dinov2_vitb14 (sha256 0b8b82f8…)", "tile_px": TILE_PX, "target_mpp": TARGET_MPP, "seconds": round(seconds, 1), "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        tmp = features_dir / f".{pid}.tmp.npz"  # np.savez appends .npz unless the name already ends with it
        with tmp.open("wb") as handle:
            np.savez(handle, feats=feats, coords=np.asarray(coords, dtype=np.int32), meta=json.dumps(meta))
        os.replace(tmp, features_dir / f"{pid}.npz")
        manifest.write(json.dumps({"patient_id": pid, "status": "ok", "tiles": len(coords), "tissue_tiles_total": len(coords_all), "seconds": round(seconds, 1), "tiles_per_s": round(len(coords) / seconds, 1), "time": meta["created"]}) + "\n")
        manifest.flush()
        processed += 1
        tile_seconds.append((len(coords), seconds))
        done = done_before + processed
        rate = sum(n for n, _ in tile_seconds) / max(sum(s for _, s in tile_seconds), 1e-6)
        remaining = len(order) - done
        mean_slide_s = float(np.mean([s for _, s in tile_seconds]))
        status = {"scope": len(order), "done": done, "remaining": remaining, "processed_this_run": processed, "mean_seconds_per_slide": round(mean_slide_s, 1), "tiles_per_s_end_to_end": round(rate, 1), "eta_hours": round(remaining * mean_slide_s / 3600, 2), "elapsed_hours": round((time.time() - t_start) / 3600, 2), "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        (features_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n")
        tqdm.write(f"{pid} {row['class']} tiles={len(coords)}/{len(coords_all)} {seconds:.0f}s ({len(coords)/seconds:.0f} tile/s) | done {done}/{len(order)} | ETA {status['eta_hours']} h")
    manifest.close()
    tqdm.write("stopped" if stop["flag"] else "finished")


if __name__ == "__main__":
    main()
