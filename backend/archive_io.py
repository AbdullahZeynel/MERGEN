"""Bounded ZIP upload and manifest validation."""
from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from backend.live_contracts import InputManifest, ResultManifest


class InvalidArchive(ValueError):
    pass


class UploadTooLarge(ValueError):
    pass


async def write_stream(chunks, destination: Path, limit: int):
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    size = 0
    with destination.open("xb") as output:
        async for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise UploadTooLarge
            output.write(chunk)
    return size


async def file_chunks(path: Path):
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            yield chunk


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _member_digest(archive: zipfile.ZipFile, name: str) -> tuple[int, str]:
    size, digest = 0, hashlib.sha256()
    with archive.open(name) as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _safe_members(archive: zipfile.ZipFile, max_expanded: int, max_members: int):
    members, expanded = archive.infolist(), 0
    if not members or len(members) > max_members:
        raise InvalidArchive("invalid member count")
    if len({item.filename for item in members}) != len(members):
        raise InvalidArchive("duplicate archive member")
    for item in members:
        path = PurePosixPath(item.filename)
        mode = item.external_attr >> 16
        if item.is_dir() or path.is_absolute() or ".." in path.parts or "\\" in item.filename:
            raise InvalidArchive("unsafe archive path")
        if stat.S_ISLNK(mode) or item.flag_bits & 0x1:
            raise InvalidArchive("links and encrypted members are not allowed")
        expanded += item.file_size
        if expanded > max_expanded or (item.compress_size and item.file_size > item.compress_size * 200):
            raise InvalidArchive("expanded archive is too large")
    return members


def validate_input_archive(path: Path, max_expanded: int) -> InputManifest:
    try:
        with zipfile.ZipFile(path) as archive:
            members = _safe_members(archive, max_expanded, 4096)
            names = {item.filename for item in members}
            if "input.json" not in names:
                raise InvalidArchive("input.json is required")
            if archive.getinfo("input.json").file_size > 1024 * 1024:
                raise InvalidArchive("input manifest is too large")
            manifest = InputManifest.model_validate_json(archive.read("input.json"))
            declared = {item.path for item in manifest.files}
            if not declared.issubset(names) or "input.json" in declared:
                raise InvalidArchive("declared input file is missing")
            allowed = declared | {"input.json"}
            if names != allowed:
                raise InvalidArchive("undeclared archive member")
            return manifest
    except (zipfile.BadZipFile, KeyError, ValidationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidArchive("invalid input archive") from exc


def validate_result_archive(path: Path, max_expanded: int, job: dict) -> ResultManifest:
    try:
        with zipfile.ZipFile(path) as archive:
            members = _safe_members(archive, max_expanded, 8192)
            names = {item.filename for item in members}
            if "manifest.json" not in names:
                raise InvalidArchive("manifest.json is required")
            if archive.getinfo("manifest.json").file_size > 1024 * 1024:
                raise InvalidArchive("result manifest is too large")
            manifest = ResultManifest.model_validate_json(archive.read("manifest.json"))
            if (manifest.jobId != job["id"] or manifest.module != job["module"]
                    or manifest.disease != job["disease"]):
                raise InvalidArchive("result does not match claimed job")
            assets = {asset.path: asset for asset in manifest.assets}
            if names != set(assets) | {"manifest.json"}:
                raise InvalidArchive("result members do not match manifest")
            for name, asset in assets.items():
                size, checksum = _member_digest(archive, name)
                if size != asset.size or checksum != asset.sha256:
                    raise InvalidArchive("result checksum mismatch")
            return manifest
    except (zipfile.BadZipFile, KeyError, ValidationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidArchive("invalid result archive") from exc
