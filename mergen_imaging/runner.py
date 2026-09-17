"""Single-case Swin UNETR runner for the G4 local process contract."""
from __future__ import annotations

import errno
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import zipfile
from pathlib import Path

from mergen_imaging import MODEL_ID, MODEL_VERSION
from mergen_imaging.glb import mesh_glb_bytes

CHANNEL_ORDER = ("FLAIR", "T1CE", "T1", "T2")
ROI = (128, 128, 128)
OVERLAP = 0.6
THRESHOLD = 0.5
# The reference pipeline resamples and reorients nothing, so the checkpoint has
# only ever seen this voxel grid: 1 mm isotropic, LPS, axis aligned. Every
# reviewed case carries exactly this direction matrix, so it is written out
# rather than derived, and a drift is visible in review. A volume in any other
# space would be scored just as confidently and just as wrongly, with nothing
# on screen to say so.
DIRECTION = ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
DIRECTION_TOLERANCE = 1e-3


class ResourceLimit(Exception):
    pass


class InputRejected(Exception):
    """The input is outside the contract this checkpoint was trained for."""


def _locked_distributions() -> dict[str, str]:
    result = {}
    for raw in Path(__file__).with_name("requirements.lock").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            name, version = line.split("==", 1)
            result[name] = version
    return result


def _verify_environment() -> None:
    for distribution, expected in _locked_distributions().items():
        installed = importlib.metadata.version(distribution).split("+", 1)[0]
        if installed != expected:
            raise RuntimeError("model environment version mismatch")


def _digest(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _checkpoint(model_root: Path) -> Path:
    document = json.loads((model_root / "manifest.json").read_text(encoding="utf-8"))
    checkpoints = document.get("checkpoints")
    if not isinstance(checkpoints, list) or len(checkpoints) != 1:
        raise ValueError("exactly one checkpoint is required")
    relative = checkpoints[0].get("path")
    if not isinstance(relative, str):
        raise ValueError("checkpoint path is missing")
    return model_root.joinpath(*relative.split("/"))


def _same_geometry(shape, affine, reference_shape, reference_affine) -> bool:
    if tuple(shape) != tuple(reference_shape):
        return False
    try:
        left = affine.tolist() if hasattr(affine, "tolist") else affine
        right = reference_affine.tolist() if hasattr(reference_affine, "tolist") else reference_affine
        return (len(left) == len(right) == 4
                and all(len(a) == len(b) == 4 for a, b in zip(left, right))
                and all(math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-4)
                        for row_a, row_b in zip(left, right) for a, b in zip(row_a, row_b)))
    except (TypeError, ValueError):
        return False


def _load_model(model_root: Path):
    import torch
    from monai.networks.nets import SwinUNETR

    _verify_environment()
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("CUDA is unavailable")
    model = SwinUNETR(in_channels=4, out_channels=3, feature_size=48,
                      drop_rate=0.0, attn_drop_rate=0.0, dropout_path_rate=0.0,
                      use_checkpoint=False)
    # The parent verifies this exact file's size and SHA-256 before the child
    # starts. The published checkpoint has NumPy scalar metadata and cannot be
    # opened by PyTorch's restricted weights-only loader.
    checkpoint = torch.load(_checkpoint(model_root), map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict") if isinstance(checkpoint, dict) else None
    if not isinstance(state, dict):
        raise ValueError("checkpoint state_dict is missing")
    model.load_state_dict(state, strict=True)
    model.eval().cuda()
    return model


def _preprocessed_space(affine) -> bool:
    """Whether this affine is the voxel grid the checkpoint was trained on.

    Spacing and orientation are one statement: each direction entry has to be
    what the reviewed cases carry, which rules out a rescaled volume, a
    reoriented one and a rotated one alike.
    """
    rows = affine.tolist() if hasattr(affine, "tolist") else affine
    try:
        if len(rows) != 4 or any(len(row) != 4 for row in rows):
            return False
        return all(abs(float(rows[row][column]) - DIRECTION[row][column]) <= DIRECTION_TOLERANCE
                   for row in range(3) for column in range(3))
    except (TypeError, ValueError):
        return False


def _load_input(volumes: dict):
    import nibabel as nib
    import numpy as np
    import torch
    from monai.transforms import NormalizeIntensity

    if set(volumes) != set(CHANNEL_ORDER):
        raise InputRejected("four modalities are required")
    arrays, reference = [], None
    for modality in CHANNEL_ORDER:
        image = nib.load(volumes[modality])
        array = image.get_fdata(dtype=np.float32)
        if array.ndim != 3 or not np.isfinite(array).all():
            raise InputRejected("invalid volume")
        if reference is None:
            # Every other modality is held to this one's affine below, so the
            # space is checked once, here.
            if not _preprocessed_space(image.affine):
                raise InputRejected("the volume is not in the reviewed space")
            reference = image
        elif not _same_geometry(array.shape, image.affine, reference.shape, reference.affine):
            raise InputRejected("modalities are not aligned")
        arrays.append(array)
    stacked = np.stack(arrays, axis=0)
    normalized = NormalizeIntensity(nonzero=True, channel_wise=True)(torch.from_numpy(stacked))
    return normalized.unsqueeze(0), reference


def _infer(model, image):
    import torch
    from monai.inferers import sliding_window_inference

    image = image.cuda(non_blocking=False)
    with torch.inference_mode(), torch.amp.autocast("cuda"):
        logits = sliding_window_inference(image, ROI, 1, model, overlap=OVERLAP)
        channels = (torch.sigmoid(logits)[0] > THRESHOLD).to(torch.uint8).cpu().numpy()
    output = channels[1] * 2
    output[channels[0] == 1] = 1
    output[channels[2] == 1] = 4
    return output.astype("uint8", copy=False)


def _meshes(labels) -> dict:
    import numpy as np
    from skimage.measure import marching_cubes

    result = {}
    for region, value in (("ET", 4), ("TC_NCR", 1), ("ED", 2)):
        binary = (labels == value).astype(np.float32)
        if int(binary.sum()) < 10:
            continue
        try:
            vertices, faces, _, _ = marching_cubes(binary, level=0.5, step_size=2)
            if len(vertices) > 50000:
                vertices, faces, _, _ = marching_cubes(binary, level=0.5, step_size=4)
        except ValueError:
            continue
        result[region] = {"vertices": vertices.tolist(), "faces": faces.tolist()}
    return result


def _package_result(request: dict, output: Path, files: tuple[tuple[str, str], ...]) -> str:
    assets = []
    for name, kind in files:
        size, digest = _digest(output / name)
        assets.append({"path": name, "kind": kind, "sha256": digest, "size": size})
    manifest = {"schemaVersion": 1, "jobId": request["jobId"], "module": "imaging",
                "disease": request["disease"], "modelId": request["modelId"],
                "modelVersion": request["modelVersion"], "hasPrediction": True,
                "hasGroundTruth": False, "assets": assets}
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    result = output / "result.zip"
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(manifest_path, "manifest.json")
        for asset in assets:
            archive.write(output / asset["path"], asset["path"])
    if result.stat().st_size > request["maxResultBytes"]:
        result.unlink()
        raise ResourceLimit
    return result.name


def _write_result(request: dict, labels, reference) -> str:
    import nibabel as nib

    output = Path(request["outputDir"])
    nifti = output / "prediction.nii.gz"
    glb = output / "prediction.glb"
    report = output / "report.json"
    prediction = nib.Nifti1Image(labels, reference.affine, reference.header)
    prediction.set_data_dtype("uint8")
    nib.save(prediction, nifti)
    glb.write_bytes(mesh_glb_bytes(_meshes(labels)))
    counts = {name: int((labels == value).sum())
              for name, value in (("enhancingTumor", 4), ("tumorCoreNcr", 1), ("edema", 2))}
    report.write_text(json.dumps({"schemaVersion": 1, "status": "research-output",
                                  "modelId": request["modelId"],
                                  "modelVersion": request["modelVersion"],
                                  "voxelCounts": counts,
                                  "notice": "Research prototype; not for clinical use."},
                                 separators=(",", ":")), encoding="utf-8")
    return _package_result(request, output, ((report.name, "report-json"),
                                             (nifti.name, "prediction-nifti"),
                                             (glb.name, "prediction-glb")))


def _respond(output: Path, name: str) -> None:
    _respond_payload(output, {"result": name})


def _respond_payload(output: Path, payload: dict) -> None:
    temporary = output / ".adapter-response.json.tmp"
    with temporary.open("w", encoding="utf-8") as target:
        json.dump(payload, target, separators=(",", ":"))
        target.flush()
        os.fsync(target.fileno())
    temporary.replace(output / ".adapter-response.json")


def _failure_code(exc: BaseException) -> str | None:
    """The contract code this failure may carry, or None to stay generic.

    Only a cause the caller can act on crosses the boundary; everything else
    is an opaque non-zero exit, because a message could quote the input.
    """
    if isinstance(exc, InputRejected):
        return "input-invalid"
    if (isinstance(exc, ResourceLimit)
            or isinstance(exc, OSError) and exc.errno == errno.ENOSPC
            or type(exc).__name__ == "OutOfMemoryError"):
        return "resource-exhausted"
    return None


def main() -> int:
    try:
        request = json.load(sys.stdin)
        output = Path(request.get("outputDir") or os.environ["TMPDIR"])
        if (request.get("modelId"), request.get("modelVersion")) != (MODEL_ID, MODEL_VERSION):
            return 2
        model = _load_model(Path(request["modelRoot"]))
        if request.get("operation") == "preflight":
            _respond(output, "result.zip")
            return 0
        if request.get("operation") != "run":
            return 2
        image, reference = _load_input(request["volumes"])
        name = _write_result(request, _infer(model, image), reference)
        _respond(output, name)
        return 0
    except Exception as exc:  # No paths, input metadata or exception text reach service logs.
        code = _failure_code(exc)
        if code is None or "output" not in locals():
            return 1
        try:
            _respond_payload(output, {"error": code})
            return 0
        except OSError:
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
