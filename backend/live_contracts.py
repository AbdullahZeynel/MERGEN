"""Versioned contracts shared by the public API and private GPU workers."""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
SafePath = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")]

LIVE_PROFILES = {
    "schemaVersion": 1,
    "profiles": [
        {"module": "imaging", "disease": "glioma", "bundle": "zip",
         "modalities": ["T1", "T1CE", "T2", "FLAIR"], "groundTruthAccepted": False},
    ],
}


class InputFile(BaseModel):
    path: SafePath
    role: Slug
    modality: Literal["T1", "T1CE", "T2", "FLAIR"] | None = None


class InputManifest(BaseModel):
    schemaVersion: Literal[1]
    module: Literal["imaging"]
    disease: Slug
    files: list[InputFile] = Field(default_factory=list, max_length=4096)

    @model_validator(mode="after")
    def validate_module_input(self):
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate file path")
        if self.disease != "glioma":
            raise ValueError("unsupported imaging disease profile")
        if any(not (item.path.endswith(".nii") or item.path.endswith(".nii.gz")) for item in self.files):
            raise ValueError("imaging volumes must use NIfTI format")
        modalities = {item.modality for item in self.files}
        if (modalities != {"T1", "T1CE", "T2", "FLAIR"} or len(self.files) != 4
                or any(item.role != "volume" for item in self.files)):
            raise ValueError("glioma imaging requires one T1, T1CE, T2 and FLAIR volume")
        return self


class ResultAsset(BaseModel):
    path: SafePath
    kind: Literal["report-json", "report-pdf", "prediction-nifti", "prediction-glb", "slice", "overlay"]
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    size: int = Field(ge=0)

    @model_validator(mode="after")
    def extension_matches_kind(self):
        suffixes = {
            "report-json": (".json",), "report-pdf": (".pdf",),
            "prediction-nifti": (".nii.gz",), "prediction-glb": (".glb",),
            "slice": (".png",), "overlay": (".png",),
        }
        if not self.path.endswith(suffixes[self.kind]):
            raise ValueError("result asset extension does not match its kind")
        return self


class ResultManifest(BaseModel):
    schemaVersion: Literal[1]
    jobId: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
    module: Literal["imaging"]
    disease: Slug
    modelId: Slug
    modelVersion: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")]
    hasPrediction: Literal[True]
    hasGroundTruth: Literal[False]
    assets: list[ResultAsset] = Field(min_length=1, max_length=8192)

    @model_validator(mode="after")
    def unique_assets(self):
        paths = [asset.path for asset in self.assets]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate result asset")
        kinds = {asset.kind for asset in self.assets}
        required = {"report-json", "prediction-nifti", "prediction-glb"}
        if not required <= kinds:
            raise ValueError(f"required assets are missing: {sorted(required - kinds)}")
        return self


def valid_worker_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", value))
