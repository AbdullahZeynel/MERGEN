"""Write a synthetic four-modality fixture for the host acceptance run.

Nothing here comes from a person. The acceptance step in GPU_HOST_RUNBOOK.md
needs four aligned volumes on the reviewed grid, and an operator reaching for a
real case to get them would be putting patient data through a smoke test. The
shapes are crude on purpose: this measures the boundary, the environment and
the result contract, never segmentation quality.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from mergen_imaging.runner import DIRECTION

SHAPE = (240, 240, 155)
# Intensity and lesion contrast per modality, in the runner's channel order.
MODALITIES = (("FLAIR", 690, 1.70), ("T1CE", 540, 1.85), ("T1", 520, 0.55), ("T2", 760, 1.55))
SEED = 20260917


def _affine():
    import numpy as np

    affine = np.eye(4)
    affine[:3, :3] = np.array(DIRECTION)
    # The reviewed cases carry this translation with this direction matrix.
    affine[1, 3] = SHAPE[1] - 1
    return affine


def write_fixture(directory: Path) -> list[Path]:
    import nibabel as nib
    import numpy as np

    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    grid = np.meshgrid(*[np.arange(size) for size in SHAPE], indexing="ij")
    centre = [size // 2 for size in SHAPE]
    head = sum(((axis - middle) / radius) ** 2
               for axis, middle, radius in zip(grid, centre, (85, 95, 62))) <= 1.0
    lesion = sum(((axis - middle) / radius) ** 2
                 for axis, middle, radius in zip(grid, (150, 100, 85), (18, 15, 14))) <= 1.0
    lesion &= head
    affine, random = _affine(), np.random.default_rng(SEED)
    written = []
    for name, level, contrast in MODALITIES:
        volume = np.zeros(SHAPE, dtype=np.float32)
        volume[head] = level + random.normal(0, level * 0.06, int(head.sum()))
        volume[lesion] *= contrast
        path = directory / f"{name}.nii.gz"
        nib.save(nib.Nifti1Image(np.clip(volume, 0, None).astype(np.int16), affine), path)
        os.chmod(path, 0o600)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    for path in write_fixture(parser.parse_args().directory):
        print(f"{path.name} {path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
