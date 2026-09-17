#!/usr/bin/env python3
"""Patient-level train/val/test split for the MERGEN WSI A/O/G task.

Rules (see README):
* one row per patient in ``cohort.tsv`` (one diagnostic slide each), so patient == slide;
* stratified on class × grade group so that the grade/class confound is balanced
  across splits (in TCGA almost every G is grade 4 and A/O are grade 2–3);
* fixed seed, deterministic, written once to ``splits.json``; the test split is locked
  and must not be used for tuning;
* a report on tissue source sites and slide magnification per split is printed so that
  centre effects can be judged (sites are not held out in the default split; use
  ``--holdout-sites`` for a site-disjoint test variant).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def load_cohort(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    ids = [r["patient_id"] for r in rows]
    assert len(ids) == len(set(ids)), "cohort must have one row per patient"
    return rows


def stratified_split(rows: list[dict], frac_val: float, frac_test: float, seed: int) -> dict[str, list[str]]:
    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        groups[(r["class"], r.get("grade") or "NA")].append(r["patient_id"])
    out = {"train": [], "val": [], "test": []}
    for key in sorted(groups):
        ids = sorted(groups[key])
        rng.shuffle(ids)
        n = len(ids)
        n_test = round(n * frac_test)
        n_val = round(n * frac_val)
        out["test"] += ids[:n_test]
        out["val"] += ids[n_test : n_test + n_val]
        out["train"] += ids[n_test + n_val :]
    for k in out:
        out[k].sort()
    return out


def site_holdout_split(rows: list[dict], frac_test: float, frac_val: float, seed: int) -> dict[str, list[str]]:
    """Alternative: whole tissue-source sites go to test (centre-disjoint)."""
    rng = random.Random(seed)
    by_site: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_site[r["tissue_source_site"]].append(r)
    sites = sorted(by_site)
    rng.shuffle(sites)
    target = frac_test * len(rows)
    test_sites, n = [], 0
    for s in sites:
        if n >= target:
            break
        test_sites.append(s)
        n += len(by_site[s])
    test = sorted(r["patient_id"] for s in test_sites for r in by_site[s])
    rest = [r for r in rows if r["patient_id"] not in set(test)]
    inner = stratified_split(rest, frac_val / (1 - frac_test), 0.0, seed)
    return {"train": inner["train"], "val": inner["val"], "test": test, "test_sites": test_sites}


def describe(rows: list[dict], split: dict[str, list[str]]) -> dict:
    by_id = {r["patient_id"]: r for r in rows}
    rep = {}
    for name in ("train", "val", "test"):
        sub = [by_id[i] for i in split[name]]
        rep[name] = {
            "n": len(sub),
            "class": dict(sorted(Counter(r["class"] for r in sub).items())),
            "class_x_grade": {f"{c}/{g}": n for (c, g), n in sorted(Counter((r["class"], r.get("grade") or "NA") for r in sub).items())},
            "sites": len({r["tissue_source_site"] for r in sub}),
            "project": dict(sorted(Counter(r["project"] for r in sub).items())),
            "bytes": sum(int(r["size"]) for r in sub),
        }
    all_sets = [set(split[k]) for k in ("train", "val", "test")]
    rep["leakage_check"] = {"pairwise_overlap": [len(a & b) for i, a in enumerate(all_sets) for b in all_sets[i + 1 :]], "covers_all": sum(len(s) for s in all_sets) == len(rows)}
    train_sites = {by_id[i]["tissue_source_site"] for i in split["train"]}
    rep["test_sites_unseen_in_train"] = sorted({by_id[i]["tissue_source_site"] for i in split["test"]} - train_sites)
    return rep


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", default=str(Path.home() / "mergen-data/pathology/datasets/tcga_glioma/manifests/cohort.tsv"))
    p.add_argument("--out", default=str(Path.home() / "mergen-data/pathology/splits/splits_v1.json"))
    p.add_argument("--val", type=float, default=0.15)
    p.add_argument("--test", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=20260914)
    p.add_argument("--holdout-sites", action="store_true", help="centre-disjoint test split instead of stratified")
    args = p.parse_args()
    rows = load_cohort(Path(args.cohort))
    split = site_holdout_split(rows, args.test, args.val, args.seed) if args.holdout_sites else stratified_split(rows, args.val, args.test, args.seed)
    report = describe(rows, split)
    cohort_hash = hashlib.sha256(Path(args.cohort).read_bytes()).hexdigest()
    payload = {"version": "v1", "seed": args.seed, "strategy": "site_holdout" if args.holdout_sites else "stratified_class_x_grade", "fractions": {"val": args.val, "test": args.test}, "cohort_file": args.cohort, "cohort_sha256": cohort_hash, "classes": ["A", "O", "G"], "class_index": {"A": 0, "O": 1, "G": 2}, "splits": {k: split[k] for k in ("train", "val", "test")}, "test_sites": split.get("test_sites"), "report": report}
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        old = json.loads(out.read_text())
        if old.get("splits") != payload["splits"]:
            raise SystemExit(f"{out} exists with a different split; delete it explicitly if you really want to change the locked split")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(report, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
