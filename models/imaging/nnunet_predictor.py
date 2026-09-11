"""
nnU-Net v2 wrapper for the brain tumor segmentation ensemble.

Loads the BraTS 2021 community-trained nnU-Net model (Dataset002_BRATS19 zip from
Zenodo 11582627) and exposes a predict() method that returns a 3-channel
probability map (TC, WT, ET) shaped (3, X, Y, Z) — same convention as the other
ensemble models so it can be plugged into the soft-voting step.

This wrapper uses nnU-Net's synchronous `predict_single_npy_array` to avoid
Python multiprocessing — on Windows the spawn-based workers would each try to
re-load torch DLLs, and on a 6 GB Laptop GPU + modest page file that frequently
runs out of paging memory (WinError 1455). Synchronous inference keeps the
torch state in a single process for the whole evaluation loop.
"""
import os
import numpy as np
import nibabel as nib
import torch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# nnU-Net needs these env vars present before its imports run.
os.environ.setdefault("nnUNet_results", f"{BASE_DIR}/nnUNet_data/nnUNet_results")
os.environ.setdefault("nnUNet_raw", f"{BASE_DIR}/nnUNet_data/nnUNet_raw")
os.environ.setdefault("nnUNet_preprocessed", f"{BASE_DIR}/nnUNet_data/nnUNet_preprocessed")

from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

MODEL_DIR = (
    f"{BASE_DIR}/nnUNet_data/nnUNet_results/"
    "Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres"
)


def _resolve_nii(case_dir: str, fname: str) -> str:
    """UCSF-PDGM ships each *.nii inside a folder of the same name.
    Support both flat (case_dir/file.nii) and nested layouts."""
    flat = os.path.join(case_dir, fname)
    nested = os.path.join(case_dir, fname, fname)
    return flat if os.path.isfile(flat) else nested


class NNUNetBraTSPredictor:
    """Single-fold nnU-Net predictor returning (TC, WT, ET) region prob maps.
    Output shape matches nibabel/MONAI convention: (3, X, Y, Z) with float32 in [0, 1].
    """

    def __init__(self, folds=(0,), device=None, use_mirroring=True):
        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.predictor = nnUNetPredictor(
            tile_step_size=0.5,
            use_gaussian=True,
            use_mirroring=use_mirroring,
            perform_everything_on_device=True,
            device=self.device,
            verbose=False,
            verbose_preprocessing=False,
            allow_tqdm=False,
        )
        self.predictor.initialize_from_trained_model_folder(
            MODEL_DIR,
            use_folds=folds,
            checkpoint_name="checkpoint_final.pth",
        )

    def predict(self, case, dataset_dir):
        """
        case: dict with keys flair/t1/t1c/t2 (filenames) and dir (subdir)
        dataset_dir: root that contains case["dir"]

        Returns numpy (3, X, Y, Z) — channels (TC, WT, ET), values in [0,1].
        """
        case_dir = os.path.join(dataset_dir, case["dir"])

        # nnU-Net channel order is T1, T1c, T2, FLAIR (see dataset.json)
        files = [case["t1"], case["t1c"], case["t2"], case["flair"]]
        paths = [_resolve_nii(case_dir, f) for f in files]

        # Read with nibabel so we use the same I/O as the rest of the pipeline,
        # then transpose into ITK (Z,Y,X) order which is what nnU-Net trained on.
        nib_img0 = nib.load(paths[0])
        spacing_xyz = list(nib_img0.header.get_zooms()[:3])
        spacing_zyx = spacing_xyz[::-1]

        channels = []
        for p in paths:
            arr_xyz = nib.load(p).get_fdata().astype(np.float32)
            channels.append(arr_xyz.transpose(2, 1, 0))  # -> (Z, Y, X)
        input_arr = np.stack(channels, axis=0)            # (4, Z, Y, X)

        # Synchronous inference — no multiprocessing, no spawned workers.
        seg, probs = self.predictor.predict_single_npy_array(
            input_image=input_arr,
            image_properties={"spacing": spacing_zyx},
            segmentation_previous_stage=None,
            output_file_truncated=None,
            save_or_return_probabilities=True,
        )
        # probs: (5, Z, Y, X)  with class indices 0=bg, 1=NCR, 2=ED, 3=empty, 4=ET
        # The dataset.json swaps NCR/edema labels but the *output* preserves the
        # standard BraTS label values — verified empirically against GT histograms.
        ncr = probs[1]
        ed = probs[2]
        et = probs[4]
        tc = ncr + et
        wt = ncr + ed + et
        regions_zyx = np.stack([tc, wt, et], axis=0)      # (3, Z, Y, X)
        # Back to (3, X, Y, Z) for the rest of the pipeline.
        return regions_zyx.transpose(0, 3, 2, 1).astype(np.float32)

    def unload(self):
        """Free GPU memory."""
        del self.predictor
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
