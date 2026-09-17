#!/usr/bin/env python3
"""How much does the weight-measurement sample matter — its size, and its composition?

uwcse_v2 showed that *which* cases the weights are measured on changes the ensemble's
behaviour more than anything else we can tune. Two open questions follow:

  1. size        — 30 cases fixed the worst of it, but is the curve still climbing?
  2. composition — is it better to add easy (enhancing, grade 4) cases, where every model
                   already agrees, or hard ones (non-enhancing, empty tumour core), where
                   the blend decision is actually fragile?

Design, fixed before the run:
  * A common test set of 100 cases is drawn once (grade-stratified, seed 7) and is used for
    every configuration, so the curves are comparable. It never enters any measurement set.
  * Measurement sets are drawn from the remaining 102 cases with seed 42:
      proportional  n = 10, 20, 30, 45, 60, 80   (grade proportions of the pool)
      easy-heavy    n = 45                       (grade 4 only)
      hard-heavy    n = 45                       (cases whose reference has no tumour core)
  * Reported per configuration: the measured weights, Dice where each region is present,
    and the silence rate where it is absent.

This is a descriptive sweep, not a model-selection procedure: the shipped coefficients are
not changed here, and no configuration is chosen by its test number.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uwcse_ensemble as ue  # noqa: E402

REGIONS = ["TC", "WT", "ET"]
VARIANTS = ["nnUNet", "SwinUNETR", "V0_Naive", "V4_UWCSE_Full"]


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def grades(metadata: Path) -> dict[str, int]:
    meta = pd.read_csv(metadata)
    return {f"UCSF-PDGM-{int(r['ID'].rsplit('-', 1)[1]):04d}": int(r["WHO CNS Grade"])
            for _, r in meta.iterrows() if r["ID"].rsplit("-", 1)[1].isdigit()}


def stratified(cases: list[str], grade: dict[str, int], n: int, seed: int) -> list[str]:
    counts = Counter(grade[c] for c in cases)
    exact = {g: n * counts[g] / len(cases) for g in counts}
    take = {g: int(np.floor(v)) for g, v in exact.items()}
    for g in sorted(exact, key=lambda g: exact[g] - take[g], reverse=True):
        if sum(take.values()) >= n:
            break
        take[g] += 1
    rng = np.random.RandomState(seed)
    out: list[str] = []
    for g in sorted(counts):
        pool = sorted(c for c in cases if grade[c] == g)
        rng.shuffle(pool)
        out += pool[: take[g]]
    return sorted(out)


def draw(cases: list[str], grade: dict[str, int], empty_tc: set[str], kind: str, n: int, seed: int) -> list[str]:
    if kind == "proportional":
        return stratified(cases, grade, n, seed)
    rng = np.random.RandomState(seed)
    pool = sorted(c for c in cases if (grade[c] == 4 if kind == "easy" else c in empty_tc))
    rng.shuffle(pool)
    return sorted(pool[:n])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default=str(data_root() / "runs/uwcse_v1/_probs_cache"))
    p.add_argument("--out", default=str(data_root() / "runs/uwcse_sweep"))
    p.add_argument("--metadata", default=str(data_root() / "datasets/ucsf_pdgm_metadata/UCSF-PDGM-metadata_v5.csv"))
    p.add_argument("--n-test", type=int, default=100)
    p.add_argument("--test-seed", type=int, default=7)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    cache, out = Path(args.cache), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    grade = grades(Path(args.metadata))
    cases = sorted(f.stem for f in cache.glob("*.npz") if f.stem in grade)

    gt_cache: dict[str, np.ndarray] = {}
    empty_tc: set[str] = set()
    for c in cases:
        gt = np.load(cache / f"{c}.npz")["gt_mc"]
        gt_cache[c] = gt
        if gt[0].sum() == 0:
            empty_tc.add(c)

    test_ids = stratified(cases, grade, args.n_test, args.test_seed)
    pool = [c for c in cases if c not in set(test_ids)]
    print(f"havuz {len(cases)} · ortak test {len(test_ids)} · ölçüm havuzu {len(pool)}")
    print(f"  test grade dağılımı: {dict(sorted(Counter(grade[c] for c in test_ids).items()))}")
    print(f"  testte çekirdeği boş olan: {sum(1 for c in test_ids if c in empty_tc)}")
    print(f"  ölçüm havuzunda çekirdeği boş olan: {sum(1 for c in pool if c in empty_tc)}\n")

    configs = ([("proportional", n) for n in (10, 20, 30, 45, 60, 80)]
               + [("easy", 45), ("hard", 45)])

    # measure the weights for every configuration first (cheap, reads only the drawn cases)
    measured = {}
    for kind, n in configs:
        ids = draw(pool, grade, empty_tc, kind, n, args.seed)
        ws = []
        for cid in ids:
            z = np.load(cache / f"{cid}.npz")
            ws.append(ue.find_optimal_weights(z["prob_nn"].astype(np.float32),
                                              z["prob_sw"].astype(np.float32), gt_cache[cid]))
        w = np.array(ws).mean(axis=0)
        measured[(kind, n)] = {"ids": ids, "weights": w.tolist(),
                               "per_case": np.array(ws).tolist(),
                               "n_empty_tc": sum(1 for c in ids if c in empty_tc),
                               "grades": dict(sorted(Counter(grade[c] for c in ids).items()))}
        print(f"  {kind:<13} n={n:<3} TC={w[0]:.3f} WT={w[1]:.3f} ET={w[2]:.3f}   "
              f"(çekirdeği boş {measured[(kind, n)]['n_empty_tc']}/{len(ids)}, grade {measured[(kind, n)]['grades']})")

    # one pass over the common test set, evaluating every configuration on each case
    print(f"\nortak test kümesinde değerlendirme ({len(test_ids)} vaka × {len(configs)} yapılandırma)")
    acc: dict = {k: {v: {r: {"present": [], "absent": []} for r in REGIONS} for v in VARIANTS} for k in measured}
    for i, cid in enumerate(test_ids, 1):
        z = np.load(cache / f"{cid}.npz")
        pn, ps, gt = z["prob_nn"].astype(np.float32), z["prob_sw"].astype(np.float32), gt_cache[cid]
        base = {"nnUNet": ue.mc_to_brats((pn > 0.5).astype(np.uint8)),
                "SwinUNETR": ue.mc_to_brats((ps > 0.5).astype(np.uint8)),
                "V0_Naive": ue.mc_to_brats((ue.vote_naive(pn, ps, 0.5) > 0.5).astype(np.uint8))}
        base_dice = {v: ue.dice_regions(ue.brats_to_regions(m), gt) for v, m in base.items()}
        for key, m in measured.items():
            masks = dict(base)
            masks["V4_UWCSE_Full"] = ue.postprocess_brats(
                ue.mc_to_brats((ue.vote_uwcse(pn, ps, m["weights"]) > 0.5).astype(np.uint8)))
            for v in VARIANTS:
                d = base_dice[v] if v in base_dice else ue.dice_regions(ue.brats_to_regions(masks[v]), gt)
                for k, r in enumerate(REGIONS):
                    acc[key][v][r]["present" if gt[k].sum() > 0 else "absent"].append(d[r])
        if i % 20 == 0 or i == len(test_ids):
            print(f"  {i}/{len(test_ids)}")

    rows = []
    for (kind, n), m in measured.items():
        entry = {"composition": kind, "n_measure": n, "weights": dict(zip(REGIONS, m["weights"])),
                 "n_empty_tc_in_measure": m["n_empty_tc"], "grades_in_measure": m["grades"], "variants": {}}
        for v in VARIANTS:
            ev = {}
            for r in REGIONS:
                pres = np.array(acc[(kind, n)][v][r]["present"])
                abst = np.array(acc[(kind, n)][v][r]["absent"])
                ev[r] = {"n_present": len(pres), "dice_present": float(pres.mean()) if len(pres) else None,
                         "n_absent": len(abst),
                         "silent": int((abst > 0.99).sum()) if len(abst) else 0,
                         "silent_rate": float((abst > 0.99).mean()) if len(abst) else None}
            entry["variants"][v] = ev
        rows.append(entry)
    payload = {"test_ids": test_ids, "n_test": len(test_ids), "test_seed": args.test_seed,
               "measure_seed": args.seed, "pool_size": len(pool), "configs": rows,
               "note": ("Betimleyici tarama. Ortak test kümesi her yapılandırmada aynıdır ve hiçbir "
                        "ölçüme girmez; buradan bir yapılandırma test skoruna bakılarak seçilmemiştir.")}
    (out / "sweep.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{'bileşim':<14}{'n':>4}{'TC ağr.':>9}{'TC Dice(var)':>14}{'TC sessiz(yok)':>16}{'ET sessiz(yok)':>16}")
    for e in rows:
        tc = e["variants"]["V4_UWCSE_Full"]["TC"]
        et = e["variants"]["V4_UWCSE_Full"]["ET"]
        tc_sil = f"{tc['silent']}/{tc['n_absent']}"
        et_sil = f"{et['silent']}/{et['n_absent']}"
        print(f"{e['composition']:<14}{e['n_measure']:>4}{e['weights']['TC']:>9.3f}"
              f"{tc['dice_present']:>14.4f}{tc_sil:>16}{et_sil:>16}")
    print(f"\nyazıldı -> {out / 'sweep.json'}")


if __name__ == "__main__":
    main()
