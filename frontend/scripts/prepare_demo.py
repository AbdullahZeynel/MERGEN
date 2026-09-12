"""Export all FLAIR slices and MR foreground context. No model inference.

Install requirements-demo.txt in a separate preparation environment.
The resulting preview package is intentionally Git-ignored.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.measure import marching_cubes

REPO = Path(__file__).resolve().parents[2]


def prepare(source: Path, output: Path) -> int:
    if output.exists():
        raise ValueError('Output already exists; choose a new directory.')
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
            slice_dir = case_dir / 'slices' / axis
            slice_dir.mkdir(parents=True)
            for layer in range(volume.shape[dimension]):
                plane = np.flipud(np.take(volume, layer, axis=dimension).T)
                low, high = float(plane.min()), float(plane.max())
                normalized = (plane-low)/(high-low) if high > low else np.zeros_like(plane)
                Image.fromarray(np.clip(normalized*255, 0, 255).astype(np.uint8)).save(slice_dir / f'{layer}.png')
            previews.append({"axis": axis, "index": index, "src": f"/api/demo/cases/{case_id}/slices/{axis}/{index}"})
        records.append({"id": case_id, "source": "UCSF-PDGM", "mode": "demo", "status": "demo_ready", "shape": list(volume.shape), "modality": "FLAIR", "previews": previews, "genomics": None})
        mesh_file = source / case_id / "mesh_ensemble.json"
        if mesh_file.is_file():
            meshes = json.loads(mesh_file.read_text())
            # Approximate MR foreground envelope, not a cortical/healthy tissue segmentation.
            labels, count = ndimage.label(volume > 0)
            if count:
                sizes = np.bincount(labels.ravel()); sizes[0] = 0
                foreground = ndimage.binary_fill_holes(labels == sizes.argmax())
                vertices, faces, _, _ = marching_cubes(np.pad(foreground, 1), level=0.5, step_size=3)
                meshes['BRAIN'] = {'vertices': (vertices - 1).tolist(), 'faces': faces.tolist()}
                records[-1]['brainContext'] = 'mr-foreground-envelope'
            (case_dir / 'mesh_ensemble.json').write_text(json.dumps(meshes, separators=(',', ':')))
            records[-1]["mesh"] = f"/api/demo/cases/{case_id}/mesh"
        print(f'Prepared {case_id}', flush=True)
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "manifest.json.tmp"
    if not records:
        raise ValueError('No source cases found')
    temporary.write_text(json.dumps({"version": 2, "cases": records}, indent=2), encoding="utf-8")
    temporary.replace(output / "manifest.json")
    print(f"Prepared {len(records)} demo cases; no inference executed.")
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO / "models/imaging/results")
    parser.add_argument("--output", type=Path, default=REPO / ".local/demo-v2")
    args = parser.parse_args()
    prepare(args.source, args.output)
