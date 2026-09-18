"""Single-case UWCSE v3 runner for the G4 local process contract.

The product configuration, not one of its members: nnU-Net BraTS21 (five
folds) and Swin UNETR BraTS21 (fold 0) run one after the other so only one
is resident at a time, and the UWCSE v3 rule fuses their probabilities.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.metadata
import json
import math
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from mergen_imaging import (MODEL_ID, MODEL_VERSION, NNUNET_FOLDS, NNUNET_MEMBER,
                            PRODUCT_WEIGHTS, SWIN_MEMBER)
from mergen_imaging.glb import mesh_glb_bytes

CHANNEL_ORDER = ("FLAIR", "T1CE", "T1", "T2")
# nnU-Net was trained with its own channel order and reads volumes in ITK axis
# order; models/imaging/nnunet_predictor.py is the reference for both.
NNUNET_CHANNEL_ORDER = ("T1", "T1CE", "T2", "FLAIR")
NNUNET_FOLD_DIR = re.compile(r"^fold_(\d+)$")
CHECKPOINT_ROLES = ("nnunet-fold", "nnunet-plan", "swin")
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


class Members(NamedTuple):
    """The trained-model folder of the nnU-Net folds, their file name, and Swin."""

    nnunet_dir: Path
    nnunet_checkpoint: str
    swin: Path


def _members(model_root: Path) -> Members:
    """The product ensemble this manifest describes, or a refusal.

    The parent has already verified every listed file's size and digest; what is
    checked here is that the set is the ensemble that was measured. A manifest
    missing a fold, repeating one, or carrying an extra member would still run
    and would still be scored — as a different ensemble, under the same name.
    """
    document = json.loads((model_root / "manifest.json").read_text(encoding="utf-8"))
    checkpoints = document.get("checkpoints")
    if not isinstance(checkpoints, list) or not checkpoints:
        raise ValueError("the manifest lists no checkpoints")
    folds: dict[int, Path] = {}
    plans: list[Path] = []
    names: set[str] = set()
    swin = None
    for item in checkpoints:
        if not isinstance(item, dict):
            raise ValueError("invalid checkpoint entry")
        role, relative = item.get("role"), item.get("path")
        if role not in CHECKPOINT_ROLES or not isinstance(relative, str) or not relative:
            raise ValueError("every checkpoint declares one of the known roles")
        path = model_root.joinpath(*PurePosixPath(relative).parts)
        if role == "swin":
            if swin is not None:
                raise ValueError("exactly one swin checkpoint is required")
            swin = path
        elif role == "nnunet-plan":
            plans.append(path)
        else:
            fold = item.get("fold")
            match = NNUNET_FOLD_DIR.fullmatch(path.parent.name)
            if fold not in NNUNET_FOLDS or fold in folds:
                raise ValueError("every nnU-Net fold is declared once")
            if match is None or int(match.group(1)) != fold:
                raise ValueError("the nnU-Net fold directory and the declared fold differ")
            folds[fold] = path
            names.add(path.name)
    if swin is None:
        raise ValueError("the swin checkpoint is missing")
    if set(folds) != set(NNUNET_FOLDS):
        raise ValueError("the product ensemble needs every nnU-Net fold")
    if len(names) != 1:
        raise ValueError("the nnU-Net folds carry different checkpoint names")
    directories = {path.parent.parent for path in folds.values()}
    if len(directories) != 1:
        raise ValueError("the nnU-Net folds are not in one trained model folder")
    nnunet_dir = directories.pop()
    for plan in plans:
        if plan.parent != nnunet_dir:
            raise ValueError("an nnU-Net plan sits outside the trained model folder")
    return Members(nnunet_dir, names.pop(), swin)


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


def _require_cuda() -> None:
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("CUDA is unavailable")


def _load_swin(checkpoint_path: Path):
    from monai.networks.nets import SwinUNETR

    _verify_environment()
    _require_cuda()
    model = SwinUNETR(in_channels=4, out_channels=3, feature_size=48,
                      drop_rate=0.0, attn_drop_rate=0.0, dropout_path_rate=0.0,
                      use_checkpoint=False)
    # The parent verifies this exact file's size and SHA-256 before the child
    # starts. The published checkpoint has NumPy scalar metadata and cannot be
    # opened by PyTorch's restricted weights-only loader.
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
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
    # Swin sees the z-scored volumes; nnU-Net normalises internally and gets the
    # raw ones, exactly as in the reference pipeline.
    normalized = NormalizeIntensity(nonzero=True, channel_wise=True)(torch.from_numpy(stacked))
    return stacked, normalized.unsqueeze(0), reference


def _swin_probabilities(model, image):
    """(3, X, Y, Z) sigmoid probabilities for TC, WT, ET."""
    import torch
    from monai.inferers import sliding_window_inference

    image = image.cuda(non_blocking=False)
    with torch.inference_mode(), torch.amp.autocast("cuda"):
        logits = sliding_window_inference(image, ROI, 1, model, overlap=OVERLAP)
        probabilities = torch.sigmoid(logits)[0].float().cpu().numpy()
    del image, logits
    torch.cuda.empty_cache()
    return probabilities.astype("float32", copy=False)


def _nnunet_probabilities(members: Members, volumes, reference, workspace: Path):
    """(3, X, Y, Z) probabilities from the five folds.

    Mirrors models/imaging/nnunet_predictor.py, which is the configuration the
    locked-test numbers were measured with: synchronous inference, no spawned
    workers, region maps derived from the class probabilities.
    """
    import numpy as np
    import torch

    _require_cuda()
    # nnU-Net reads these three variables while it is being imported. Only the
    # results root holds anything; the other two are empty scratch directories
    # inside the job's own output tree, removed again below.
    results_root = members.nnunet_dir.parent.parent
    scratch = workspace / ".nnunet-work"
    for name, value in (("nnUNet_results", results_root),
                        ("nnUNet_raw", scratch / "raw"),
                        ("nnUNet_preprocessed", scratch / "preprocessed")):
        Path(value).mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(value)
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    predictor = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=True,
                                perform_everything_on_device=True, device=torch.device("cuda"),
                                verbose=False, verbose_preprocessing=False, allow_tqdm=False)
    predictor.initialize_from_trained_model_folder(
        str(members.nnunet_dir), use_folds=tuple(NNUNET_FOLDS),
        checkpoint_name=members.nnunet_checkpoint)
    order = [CHANNEL_ORDER.index(name) for name in NNUNET_CHANNEL_ORDER]
    # (4, Z, Y, X): nnU-Net trained on ITK axis order.
    stacked = np.stack([volumes[index].transpose(2, 1, 0) for index in order], axis=0)
    spacing = list(reference.header.get_zooms()[:3])[::-1]
    _, probabilities = predictor.predict_single_npy_array(
        input_image=stacked, image_properties={"spacing": spacing},
        segmentation_previous_stage=None, output_file_truncated=None,
        save_or_return_probabilities=True)
    del predictor, stacked
    torch.cuda.empty_cache()
    shutil.rmtree(scratch, ignore_errors=True)
    # probabilities: (5, Z, Y, X) over 0=bg, 1=NCR, 2=ED, 4=ET.
    ncr, edema, enhancing = probabilities[1], probabilities[2], probabilities[4]
    regions = np.stack([ncr + enhancing, ncr + edema + enhancing, enhancing], axis=0)
    return regions.transpose(0, 3, 2, 1).astype("float32", copy=False)


def _combine(prob_nnunet, prob_swin):
    """The product rule: UWCSE v3 fusion, BraTS post-processing, review flags."""
    import numpy as np

    from mergen_imaging import uwcse

    fused = uwcse.vote_uwcse(prob_nnunet, prob_swin, PRODUCT_WEIGHTS)
    labels = uwcse.postprocess_brats(uwcse.mc_to_brats((fused > THRESHOLD).astype(np.uint8)))
    return labels, uwcse.review_flags(labels), uwcse.region_volumes(labels)


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


def _member_records() -> list:
    """Which networks produced this result, named the way the registry names them."""
    return [{"modelId": NNUNET_MEMBER[0], "modelVersion": NNUNET_MEMBER[1],
             "folds": list(NNUNET_FOLDS)},
            {"modelId": SWIN_MEMBER[0], "modelVersion": SWIN_MEMBER[1]}]


def _write_result(request: dict, labels, reference, flags: list, volumes: dict) -> str:
    import nibabel as nib

    output = Path(request["outputDir"])
    nifti = output / "prediction.nii.gz"
    glb = output / "prediction.glb"
    report = output / "report.json"
    prediction = nib.Nifti1Image(labels, reference.affine, reference.header)
    prediction.set_data_dtype("uint8")
    nib.save(prediction, nifti)
    glb.write_bytes(mesh_glb_bytes(_meshes(labels)))
    from mergen_imaging import uwcse

    counts = {name: int((labels == value).sum())
              for name, value in (("enhancingTumor", 4), ("tumorCoreNcr", 1), ("edema", 2))}
    report.write_text(json.dumps({"schemaVersion": 2, "status": "research-output",
                                  "modelId": request["modelId"],
                                  "modelVersion": request["modelVersion"],
                                  "members": _member_records(),
                                  "rule": {"id": "uwcse", "version": MODEL_VERSION,
                                           "weights": dict(zip(("TC", "WT", "ET"),
                                                               PRODUCT_WEIGHTS)),
                                           "tcMin": uwcse.TC_MIN, "etMin": uwcse.ET_MIN,
                                           "minComponentVoxels": uwcse.MIN_CC_SIZE},
                                  "regionVolumes": volumes,
                                  "reviewFlags": flags,
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
        model_root = Path(request["modelRoot"])
        members = _members(model_root)
        if request.get("operation") == "preflight":
            # Loading Swin proves the environment and the published file; the
            # nnU-Net folder is checked for the files its predictor needs,
            # because initialising five folds is not a startup cost.
            _load_swin(members.swin)
            for required in ("dataset.json", "plans.json"):
                if not (members.nnunet_dir / required).is_file():
                    raise ValueError("the nnU-Net model folder is incomplete")
            _respond(output, "result.zip")
            return 0
        if request.get("operation") != "run":
            return 2
        # The environment is held to the lock before either member runs, not
        # only before the one that happens to load first.
        _verify_environment()
        raw, image, reference = _load_input(request["volumes"])
        # One member is resident at a time; each frees the device before the
        # next is built (measured peaks 3.1 GiB and 4.4 GiB).
        prob_nnunet = _nnunet_probabilities(members, raw, reference, output)
        prob_swin = _swin_probabilities(_load_swin(members.swin), image)
        labels, flags, volumes = _combine(prob_nnunet, prob_swin)
        name = _write_result(request, labels, reference, flags, volumes)
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
