#!/usr/bin/env python3
"""Re-measure the UWCSE ensemble weights on a grade-stratified sample.

Why: in uwcse_v1 the ten cases used to measure the weights were drawn at random and came
out 7/10 grade 4. Non-enhancing low-grade tumours were therefore almost absent from the
measurement, the grid search never saw that behaviour, and the resulting TC weight (0.53)
leaned towards nnU-Net — which marks a tumour core on 60 of the 68 cases that have none.

This run changes only *which cases the weights are measured on*, never the measurement:
the same deterministic 13-point grid search over the same cached probability maps. No
inference is repeated, so nnU-Net's and Swin UNETR's outputs are bit-identical to uwcse_v1.

Parameters are fixed here before the run and are not tuned against the test result:
  * 30 validation cases, allocated across WHO grades in proportion to the 202-case pool
    (largest-remainder rounding), drawn with seed 42
  * every remaining case is test
  * the same seven variants are reported
Both uwcse_v1 and this run must be quoted together; neither supersedes the other silently.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uwcse_ensemble as ue  # noqa: E402

VARIANTS = ["nnUNet", "SwinUNETR", "V0_Naive", "V1_CSW", "V2_CSW+UNC", "V3_CSW+PP", "V4_UWCSE_Full"]
REGIONS = ["TC", "WT", "ET"]


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def grades(metadata: Path) -> dict[str, int]:
    meta = pd.read_csv(metadata)
    out = {}
    for _, row in meta.iterrows():
        num = row["ID"].rsplit("-", 1)[1]
        if num.isdigit():
            out[f"UCSF-PDGM-{int(num):04d}"] = int(row["WHO CNS Grade"])
    return out


def stratified_draw(cases: list[str], grade: dict[str, int], n: int, seed: int) -> list[str]:
    """Allocate n cases across grades in proportion to the pool (largest remainder)."""
    counts = Counter(grade[c] for c in cases)
    total = len(cases)
    exact = {g: n * counts[g] / total for g in counts}
    take = {g: int(np.floor(v)) for g, v in exact.items()}
    for g in sorted(exact, key=lambda g: exact[g] - take[g], reverse=True):
        if sum(take.values()) >= n:
            break
        take[g] += 1
    rng = np.random.RandomState(seed)
    chosen: list[str] = []
    for g in sorted(counts):
        pool = sorted(c for c in cases if grade[c] == g)
        rng.shuffle(pool)
        chosen += pool[: take[g]]
    return sorted(chosen)


def variant_masks(prob_nn, prob_sw, weights) -> dict[str, np.ndarray]:
    p_v0 = ue.vote_naive(prob_nn, prob_sw, 0.5)
    p_v1 = ue.vote_class_specific(prob_nn, prob_sw, weights)
    p_v2 = ue.vote_uwcse(prob_nn, prob_sw, weights)
    b_v1 = ue.mc_to_brats((p_v1 > 0.5).astype(np.uint8))
    b_v2 = ue.mc_to_brats((p_v2 > 0.5).astype(np.uint8))
    return {
        "nnUNet": ue.mc_to_brats((prob_nn > 0.5).astype(np.uint8)),
        "SwinUNETR": ue.mc_to_brats((prob_sw > 0.5).astype(np.uint8)),
        "V0_Naive": ue.mc_to_brats((p_v0 > 0.5).astype(np.uint8)),
        "V1_CSW": b_v1, "V2_CSW+UNC": b_v2,
        "V3_CSW+PP": ue.postprocess_brats(b_v1), "V4_UWCSE_Full": ue.postprocess_brats(b_v2),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default=str(data_root() / "runs/uwcse_v1/_probs_cache"),
                   help="probability maps from the uwcse_v1 inference pass (reused, never recomputed)")
    p.add_argument("--out", default=str(data_root() / "runs/uwcse_v2"))
    p.add_argument("--metadata", default=str(data_root() / "datasets/ucsf_pdgm_metadata/UCSF-PDGM-metadata_v5.csv"))
    p.add_argument("--n-val", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    cache, out = Path(args.cache), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    grade = grades(Path(args.metadata))
    cases = sorted(f.stem for f in cache.glob("*.npz") if f.stem in grade)
    val_ids = stratified_draw(cases, grade, args.n_val, args.seed)
    test_ids = [c for c in cases if c not in set(val_ids)]
    print(f"havuz {len(cases)} · ağırlık ölçümü {len(val_ids)} · test {len(test_ids)}")
    print(f"  ölçüm kümesi grade dağılımı: {dict(sorted(Counter(grade[c] for c in val_ids).items()))}")
    print(f"  test kümesi grade dağılımı:  {dict(sorted(Counter(grade[c] for c in test_ids).items()))}")

    def load(cid):
        z = np.load(cache / f"{cid}.npz")
        return z["prob_nn"].astype(np.float32), z["prob_sw"].astype(np.float32), z["gt_mc"]

    print("\nağırlık ölçümü (13 noktalı ızgara, determinist)")
    per_case_w = []
    for cid in val_ids:
        pn, ps, gt = load(cid)
        w = ue.find_optimal_weights(pn, ps, gt)
        per_case_w.append((cid, w))
        print(f"  [{cid}] grade {grade[cid]}  TC={w[0]:.2f} WT={w[1]:.2f} ET={w[2]:.2f}"
              f"   (referans TC={int(gt[0].sum())} ET={int(gt[2].sum())})")
    weights = np.array([w for _, w in per_case_w]).mean(axis=0).tolist()
    print(f"\n  ortalama ağırlıklar: TC={weights[0]:.3f} WT={weights[1]:.3f} ET={weights[2]:.3f}")
    (out / "optimal_weights.json").write_text(json.dumps({
        "averaged": dict(zip(REGIONS, weights)),
        "per_val_case": {cid: dict(zip(REGIONS, w)) for cid, w in per_case_w}}, indent=2) + "\n")

    print(f"\ntest değerlendirmesi ({len(test_ids)} vaka)")
    per_case: dict[str, dict] = {}
    presence: dict[str, dict] = {}
    for i, cid in enumerate(test_ids, 1):
        pn, ps, gt = load(cid)
        presence[cid] = {r: bool(gt[k].sum() > 0) for k, r in enumerate(REGIONS)}
        masks = variant_masks(pn, ps, weights)
        rows = {}
        for name in VARIANTS:
            d = ue.dice_regions(ue.brats_to_regions(masks[name]), gt)
            d["Mean"] = round((d["TC"] + d["WT"] + d["ET"]) / 3, 4)
            rows[name] = d
        per_case[cid] = rows
        if i % 40 == 0 or i == len(test_ids):
            print(f"  {i}/{len(test_ids)}")

    (out / "test_metrics.json").write_text(json.dumps(
        {"optimal_weights": dict(zip(REGIONS, weights)), "per_case": per_case}, indent=2) + "\n")
    (out / "split.json").write_text(json.dumps(
        {"seed": args.seed, "n_safe": len(cases), "stratified_by": "WHO CNS Grade",
         "val": val_ids, "test": test_ids}, indent=2) + "\n")

    summary = {}
    for v in VARIANTS:
        summary[v] = {}
        for r in REGIONS + ["Mean"]:
            vals = np.array([per_case[c][v][r] for c in per_case])
            summary[v][r] = {"mean": float(vals.mean()), "std": float(vals.std()),
                             "median": float(np.median(vals))}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n{'model':<16}{'bölge':<5}{'var: n':>8}{'Dice':>9}   {'yok: n':>8}{'sessiz':>12}")
    for v in ("nnUNet", "SwinUNETR", "V4_UWCSE_Full"):
        for r in REGIONS:
            present = [c for c in per_case if presence[c][r]]
            absent = [c for c in per_case if not presence[c][r]]
            dp = np.array([per_case[c][v][r] for c in present])
            da = np.array([per_case[c][v][r] for c in absent]) if absent else np.array([])
            silent = f"{(da > 0.99).sum()}/{len(da)}" if len(da) else "—"
            print(f"{v:<16}{r:<5}{len(present):>8}{dp.mean():>9.4f}   {len(absent):>8}{silent:>12}")
    print(f"\nyazıldı -> {out}")


if __name__ == "__main__":
    main()
