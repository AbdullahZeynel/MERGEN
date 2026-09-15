"""The one seam between the executor and a model.

An adapter knows nothing of the VPS, the dispatcher, tokens or the spool. It
receives a verified imaging job and two job-specific directories, and either
leaves a result ZIP in its output directory or fails with a contract error
code. G3 ships no implementation: tests use a fake one, G4 adds the real one.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from pydantic import TypeAdapter, ValidationError

from backend.live_contracts import ModelVersion, Slug
from mergen_spool.contract import ErrorCode

ERROR_CODES = frozenset(get_args(ErrorCode))
# The forms ResultManifest.modelId and ResultManifest.modelVersion accept.
_MODEL_ID = TypeAdapter(Slug)
_MODEL_VERSION = TypeAdapter(ModelVersion)


class AdapterFailure(Exception):
    """An explicit failure with a code from the spool contract.

    `reason` is for developers only and is never logged: it may name inputs.
    """

    def __init__(self, error_code: str, reason: str = ""):
        super().__init__(error_code)
        self.error_code = error_code if error_code in ERROR_CODES else "internal-error"
        self.reason = reason


@dataclass(frozen=True)
class ImagingJob:
    job_id: str
    disease: str
    # T1, T1CE, T2 and FLAIR, each a NIfTI file inside input_dir.
    volumes: Mapping[str, Path]
    input_dir: Path
    # Empty when the adapter starts; the only place it may write.
    output_dir: Path
    max_result_bytes: int
    # True once the dispatcher has cancelled the job or the executor stops.
    cancelled: Callable[[], bool]


@dataclass(frozen=True)
class ModelIdentity:
    """The model an adapter declares; every result it publishes names it."""

    model_id: str
    model_version: str


class ImagingAdapter(ABC):
    # The model this adapter runs, as its result manifests name it: model_id is
    # a slug and model_version has the form of ResultManifest.modelVersion.
    # Checked at start; an adapter without a valid identity is not advertised.
    model_id: str
    model_version: str

    def preflight(self) -> None:
        """Raise AdapterFailure("model-unavailable") when the model cannot run.

        Called once at start; an adapter that fails it is not advertised.
        """

    @abstractmethod
    def run(self, job: ImagingJob) -> str:
        """Write the result ZIP into job.output_dir and return its file name.

        The ZIP holds manifest.json (backend.live_contracts.ResultManifest for
        this job, naming model_id and model_version) and the assets it lists.
        Write nowhere else, poll job.cancelled() and stop early when it turns true.
        """


def model_identity(adapter: ImagingAdapter) -> ModelIdentity | None:
    """The adapter's declared model, or None when no result could name it."""
    model_id = getattr(adapter, "model_id", None)
    model_version = getattr(adapter, "model_version", None)
    try:
        _MODEL_ID.validate_python(model_id, strict=True)
        _MODEL_VERSION.validate_python(model_version, strict=True)
    except ValidationError:
        return None
    return ModelIdentity(model_id, model_version)


def default_imaging_adapter() -> ImagingAdapter | None:
    """The adapter this release runs. None until G4 adds the real model."""
    return None
