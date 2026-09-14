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
from mesh_glb import write_mesh_glb

REPO = Path(__file__).resolve().parents[2]
OVERLAY_COLORS = {
    1: (79, 201, 155, 170),   # necrotic/non-enhancing core
    2: (82, 145, 239, 150),   # edema
    4: (255, 83, 102, 190),   # enhancing tumor
}


def overlay_image(mask: np.ndarray) -> Image.Image:
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    for label, color in OVERLAY_COLORS.items():
        rgba[mask == label] = color
    return Image.fromarray(rgba, mode='RGBA')


DEFAULT_CASES = ("UCSF-PDGM-0004", "UCSF-PDGM-0007")


def selected_cases(source: Path, cases: list[str] | None, all_cases: bool) -> list[str]:
    if cases and all_cases:
        raise ValueError('Use either explicit cases or all cases, not both.')
    if all_cases:
        return sorted(path.name for path in source.iterdir() if path.is_dir())
    return list(cases or DEFAULT_CASES)


def prepare(source: Path, output: Path, cases: list[str] | None = None,
            all_cases: bool = False) -> int:
    if output.exists():
        raise ValueError('Output already exists; choose a new directory.')
    records = []
    for case_id in selected_cases(source, cases, all_cases):
        source_file = source / case_id / "flair.npz"
        if not source_file.is_file():
            continue
        with np.load(source_file, allow_pickle=False) as archive:
            volume = archive["data"]
        with np.load(source / case_id / "seg_volumes.npz", allow_pickle=False) as archive:
            masks = {"prediction": archive["ensemble"], "ground_truth": archive["gt"]}
        if volume.ndim != 3 or not np.isfinite(volume).all():
            raise ValueError(f"Invalid volume: {case_id}")
        for layer, mask in masks.items():
            if mask.shape != volume.shape or not set(np.unique(mask)).issubset({0, 1, 2, 4}):
                raise ValueError(f"Invalid {layer} mask: {case_id}")
        case_dir = output / 'imaging' / 'glioma' / 'cases' / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        previews = []
        for axis, dimension in (("axial", 2), ("coronal", 1), ("sagittal", 0)):
            projection_axes = tuple(i for i in range(3) if i != dimension)
            tumor_per_layer = np.count_nonzero(masks["prediction"], axis=projection_axes)
            index = int(tumor_per_layer.argmax())
            slice_dir = case_dir / 'slices' / axis
            slice_dir.mkdir(parents=True)
            for layer in range(volume.shape[dimension]):
                plane = np.flipud(np.take(volume, layer, axis=dimension).T)
                low, high = float(plane.min()), float(plane.max())
                normalized = (plane-low)/(high-low) if high > low else np.zeros_like(plane)
                Image.fromarray(np.clip(normalized*255, 0, 255).astype(np.uint8)).save(slice_dir / f'{layer}.png')
                for overlay, mask in masks.items():
                    mask_plane = np.flipud(np.take(mask, layer, axis=dimension).T)
                    overlay_dir = case_dir / 'overlays' / overlay / axis
                    overlay_dir.mkdir(parents=True, exist_ok=True)
                    overlay_image(mask_plane).save(overlay_dir / f'{layer}.png', optimize=True)
            previews.append({
                "axis": axis,
                "index": index,
                "src": (f"/api/demo/modules/imaging/diseases/glioma/cases/"
                        f"{case_id}/slices/{axis}/{index}"),
            })
        records.append({
            "schemaVersion": 3,
            "module": "imaging",
            "disease": "glioma",
            "caseId": case_id,
            "id": case_id,
            "source": "UCSF-PDGM",
            "mode": "demo",
            "status": "demo_ready",
            "modelId": "uwcse-full",
            "modelVersion": "unversioned-precomputed",
            "inputKind": "prepared-mri-segmentation",
            "hasPrediction": True,
            "hasGroundTruth": True,
            "shape": list(volume.shape),
            "modality": "FLAIR",
            "previews": previews,
            "overlays": ["prediction", "ground_truth"],
            "genomics": None,
        })
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
            _, digest = write_mesh_glb(meshes, case_dir)
            records[-1]["mesh"] = (f"/api/demo/modules/imaging/diseases/glioma/"
                                    f"cases/{case_id}/mesh/{digest}.glb")
        print(f'Prepared {case_id}', flush=True)
    output.mkdir(parents=True, exist_ok=True)
    if not records:
        raise ValueError('No source cases found')
    collection_dir = output / 'imaging' / 'glioma'
    temporary = collection_dir / 'manifest.json.tmp'
    temporary.write_text(json.dumps({
        "schemaVersion": 3,
        "module": "imaging",
        "disease": "glioma",
        "cases": records,
    }, indent=2), encoding="utf-8")
    temporary.replace(collection_dir / 'manifest.json')
    catalog = {
        "schemaVersion": 3,
        "collections": [{
            "module": "imaging",
            "disease": "glioma",
            "manifest": "imaging/glioma/manifest.json",
        }],
    }
    catalog_temporary = output / 'catalog.json.tmp'
    catalog_temporary.write_text(json.dumps(catalog, indent=2), encoding='utf-8')
    catalog_temporary.replace(output / 'catalog.json')
    print(f"Prepared {len(records)} demo cases; no inference executed.")
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO / "models/imaging/results")
    parser.add_argument("--output", type=Path, default=REPO / ".local/demo-v3")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--cases", nargs='+', metavar='CASE_ID',
                           help="explicit reviewed cases to publish")
    selection.add_argument("--all-cases", action='store_true',
                           help="publish every prepared case under --source")
    args = parser.parse_args()
    prepare(args.source, args.output, args.cases, args.all_cases)
