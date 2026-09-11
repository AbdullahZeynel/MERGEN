"""
Wilcoxon signed-rank tests + descriptive stats for the UWCSE test results.
Writes results_eval/statistics.json.
"""
import json
from pathlib import Path
import numpy as np
from scipy.stats import wilcoxon

R = Path(__file__).parent / "results_eval"
data = json.loads((R / "test_metrics.json").read_text())
per_case = data["per_case"]
case_ids = list(per_case.keys())

variants = ["nnUNet", "SwinUNETR", "V0_Naive", "V1_CSW",
            "V2_CSW+UNC", "V3_CSW+PP", "V4_UWCSE_Full"]


def get_scores(variant, region):
    return np.array([per_case[c][variant][region] for c in case_ids])


# Pairs of (target_variant, baseline_variant) to test
pairs = [
    ("V4_UWCSE_Full", "V0_Naive",   "UWCSE Full vs Naive baseline"),
    ("V4_UWCSE_Full", "nnUNet",     "UWCSE Full vs nnU-Net alone"),
    ("V4_UWCSE_Full", "SwinUNETR",  "UWCSE Full vs Swin UNETR alone"),
    ("V1_CSW",        "V0_Naive",   "CSW vs Naive — contribution of class-specific weights"),
    ("V2_CSW+UNC",    "V1_CSW",     "UNC contribution"),
    ("V3_CSW+PP",     "V1_CSW",     "PP contribution"),
    ("V4_UWCSE_Full", "V2_CSW+UNC", "PP contribution on top of UNC"),
]


def run():
    out = {"n_test_cases": len(case_ids), "case_ids": case_ids, "tests": {}}
    print(f"\nN = {len(case_ids)} test cases\n")
    for tgt, base, desc in pairs:
        out["tests"][f"{tgt}_vs_{base}"] = {"description": desc, "regions": {}}
        print(f"=== {desc} ({tgt} - {base}) ===")
        print(f"  {'region':6} {'mean_diff':>10} {'wilcoxon_W':>12} {'p_value':>12}  {'verdict'}")
        for region in ("TC", "WT", "ET", "Mean"):
            t = get_scores(tgt, region)
            b = get_scores(base, region)
            diff = t - b
            try:
                w_stat, p_val = wilcoxon(t, b, zero_method="wilcox",
                                         alternative="greater")
            except ValueError as e:
                w_stat, p_val = float("nan"), float("nan")
            mean_diff = float(diff.mean())
            verdict = "  *significant" if p_val < 0.05 else ""
            print(f"  {region:6} {mean_diff:+10.5f} {w_stat:>12.2f} {p_val:>12.5f}{verdict}")
            out["tests"][f"{tgt}_vs_{base}"]["regions"][region] = {
                "mean_diff": mean_diff,
                "median_diff": float(np.median(diff)),
                "wilcoxon_W": float(w_stat) if w_stat == w_stat else None,
                "p_value_one_sided": float(p_val) if p_val == p_val else None,
                "significant_05": bool(p_val < 0.05) if p_val == p_val else False,
                "n_target_better": int((diff > 0).sum()),
                "n_baseline_better": int((diff < 0).sum()),
                "n_tied": int((diff == 0).sum()),
            }
        print()

    # Also descriptive table
    desc = {}
    for v in variants:
        desc[v] = {}
        for r in ("TC", "WT", "ET", "Mean"):
            arr = get_scores(v, r)
            desc[v][r] = {
                "mean": float(arr.mean()),
                "std": float(arr.std(ddof=1)),
                "median": float(np.median(arr)),
                "min": float(arr.min()),
                "max": float(arr.max()),
            }
    out["descriptive"] = desc

    (R / "statistics.json").write_text(json.dumps(out, indent=2))
    print(f"Wrote {R / 'statistics.json'}")


if __name__ == "__main__":
    run()
