"""Run one anonymous four-volume fixture through the isolated model boundary."""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from backend.archive_io import validate_result_archive
from mergen_executor.adapter import ImagingJob
from mergen_executor.process_adapter import ProcessImagingAdapter

JOB_ID = "0" * 32


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--imaging-venv", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True,
                        help="anonymous directory with T1/T1CE/T2/FLAIR.nii.gz")
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    volumes = {name: args.fixture / f"{name}.nii.gz"
               for name in ("T1", "T1CE", "T2", "FLAIR")}
    if any(not path.is_file() or path.is_symlink() for path in volumes.values()):
        print("FAIL fixture must contain four regular, non-symlink NIfTI files")
        return 2
    adapter = ProcessImagingAdapter(args.model_root, args.imaging_venv,
                                    timeout=args.timeout, term_grace=10)
    try:
        adapter.preflight()
        with tempfile.TemporaryDirectory(prefix="mergen-model-smoke-") as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            started = time.monotonic()
            name = adapter.run(ImagingJob(JOB_ID, "glioma", volumes, args.fixture, output,
                                          2 * 1024**3, lambda: False))
            elapsed = time.monotonic() - started
            result = output / name
            manifest = validate_result_archive(
                result, 8 * 1024**3,
                {"id": JOB_ID, "module": "imaging", "disease": "glioma"})
            if (manifest.modelId, manifest.modelVersion) != (
                    adapter.model_id, adapter.model_version):
                raise ValueError
            print(f"PASS isolated inference ({elapsed:.1f}s, {result.stat().st_size} bytes)")
            return 0
    except Exception:  # Never print a path, patient metadata or model exception.
        print("FAIL isolated model preflight or inference")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
