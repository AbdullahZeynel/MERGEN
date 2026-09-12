"""Export three genuine FLAIR center slices per local case. No model inference.

Run from any directory with a Python environment containing numpy and Pillow.
The resulting preview package is intentionally Git-ignored.
"""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]


def prepare(source: Path, output: Path) -> int:
    records = []
    # Only the two previously reviewed public demo cases are exported.
    for case_id in ("UCSF-PDGM-0004", "UCSF-PDGM-0007"):
        source_file = source / case_id / "flair.npz"
        if not source_file.is_file():
            continue
        with np.load(source_file, allow_pickle=False) as archive:
            volume = archive["data"]
        if volume.ndim != 3 or not np.isfinite(volume).all():
            raise ValueError(f"Invalid volume: {case_id}")
        case_dir = output / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        previews = []
        for axis, dimension in (("axial", 2), ("coronal", 1), ("sagittal", 0)):
            index = volume.shape[dimension] // 2
            # Matches legacy bg.T / origin='lower'. No anatomical orientation claim.
            plane = np.flipud(np.take(volume, index, axis=dimension).T)
            low, high = float(plane.min()), float(plane.max())
            normalized = (plane - low) / (high - low) if high > low else np.zeros_like(plane)
            Image.fromarray(np.clip(normalized * 255, 0, 255).astype(np.uint8)).save(case_dir / f"{axis}.png")
            previews.append({"axis": axis, "index": index, "src": f"/demo/{case_id}/{axis}.png"})
        records.append({"id": case_id, "source": "UCSF-PDGM", "mode": "demo", "status": "demo_ready", "shape": list(volume.shape), "modality": "FLAIR", "previews": previews, "genomics": None})
        mesh_file = source / case_id / "mesh_ensemble.json"
        if mesh_file.is_file():
            shutil.copyfile(mesh_file, case_dir / "mesh_ensemble.json")
            records[-1]["mesh"] = f"/demo/{case_id}/mesh_ensemble.json"
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps({"version": 1, "cases": records}, indent=2), encoding="utf-8")
    temporary.replace(output / "manifest.json")
    print(f"Prepared {len(records)} demo cases; no inference executed.")
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO / "models/imaging/results")
    parser.add_argument("--output", type=Path, default=REPO / "frontend/public/demo")
    args = parser.parse_args()
    prepare(args.source, args.output)
