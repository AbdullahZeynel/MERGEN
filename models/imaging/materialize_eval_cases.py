#!/usr/bin/env python3
"""Turn recorded evaluation probabilities into Git-ignored demo source cases.

This does not run a model or tune weights. It applies the weights already recorded
by evaluate_uwcse.py to its cached test-set probabilities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from skimage.measure import marching_cubes

import uwcse_ensemble as ue


def find_volume(dataset: Path, case_id: str, suffix: str) -> Path:
    matches = list(dataset.glob(f"{case_id}_nifti/{case_id}_{suffix}.nii*"))
    if len(matches) != 1:
        raise ValueError(f"Expected one {suffix} volume for {case_id}; found {len(matches)}")
    match = matches[0]
    if match.is_dir():
        inner = [path for path in match.iterdir()
                 if path.is_file() and path.name.endswith((".nii", ".nii.gz"))]
        if len(inner) != 1:
            raise ValueError(f"Expected one file inside {match}; found {len(inner)}")
        return inner[0]
    return match


def mesh(volume: np.ndarray, label_value: int) -> dict | None:
    binary = (volume == label_value).astype(np.float32)
    if int(binary.sum()) < 10:
        return None
    vertices, faces, _, _ = marching_cubes(binary, level=0.5, step_size=2)
    if len(vertices) > 50_000:
        vertices, faces, _, _ = marching_cubes(binary, level=0.5, step_size=4)
    return {"vertices": vertices.tolist(), "faces": faces.tolist()}


def materialize_case(case_id: str, cache: Path, dataset: Path, output: Path,
                     weights: list[float]) -> None:
    cache_file = cache / f"{case_id}.npz"
    if not cache_file.is_file():
        raise ValueError(f"Missing probability cache: {case_id}")
    flair_file = find_volume(dataset, case_id, "FLAIR_bias")
    with np.load(cache_file, allow_pickle=False) as archive:
        prob_nn = archive["prob_nn"].astype(np.float32)
        prob_sw = archive["prob_sw"].astype(np.float32)
        gt_mc = archive["gt_mc"]
    if prob_nn.shape != prob_sw.shape or prob_nn.shape != gt_mc.shape or prob_nn.shape[0] != 3:
        raise ValueError(f"Invalid cached probability shapes: {case_id}")
    probability = ue.vote_uwcse(prob_nn, prob_sw, weights)
    prediction = ue.postprocess_brats(ue.mc_to_brats((probability > 0.5).astype(np.uint8)))
    ground_truth = ue.mc_to_brats(gt_mc)
    flair = np.asarray(nib.load(flair_file).dataobj, dtype=np.float32)
    if flair.shape != prediction.shape:
        raise ValueError(f"FLAIR/cache shape mismatch: {case_id}")

    destination = output / case_id
    destination.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(destination / "flair.npz", data=flair)
    np.savez_compressed(destination / "seg_volumes.npz",
                        ensemble=prediction, gt=ground_truth)
    colors = {"ET": "#ff4757", "TC_NCR": "#2ed573", "ED": "#1e90ff"}
    meshes = {}
    for region, label_value in (("ET", 4), ("TC_NCR", 1), ("ED", 2)):
        value = mesh(prediction, label_value)
        if value:
            value["color"] = colors[region]
            meshes[region] = value
    (destination / "mesh_ensemble.json").write_text(
        json.dumps(meshes, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs='+', required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new directory.")
    recorded = json.loads(args.weights.read_text(encoding="utf-8"))["averaged"]
    weights = [float(recorded[name]) for name in ("TC", "WT", "ET")]
    args.output.mkdir(parents=True)
    try:
        for case_id in args.cases:
            materialize_case(case_id, args.cache, args.dataset, args.output, weights)
            print(f"Materialized {case_id}", flush=True)
    except Exception:
        import shutil
        shutil.rmtree(args.output, ignore_errors=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
