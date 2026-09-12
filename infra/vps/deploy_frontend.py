"""Install a verified static archive locally on the VPS; atomically switch releases.

Requires Python 3.11+. Does not use SSH, install software, or modify Caddy.
Old releases remain on disk so rollback is possible.
"""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

MAX_BYTES = 512 * 1024 * 1024


def switch_link(root: Path, name: str, target: Path) -> None:
    link = root / name
    if link.exists() and not link.is_symlink():
        raise ValueError(f"Refusing to replace non-symlink: {name}")
    temporary = root / f".{name}-{os.getpid()}"
    temporary.symlink_to(target.relative_to(root))
    os.replace(temporary, link)


def release_target(root: Path, name: str) -> Path | None:
    link = root / name
    if not link.is_symlink():
        if link.exists():
            raise ValueError(f"Expected release symlink: {name}")
        return None
    target = link.resolve()
    if target.parent != root / "releases" or not (target / "index.html").is_file():
        raise ValueError(f"Invalid release target: {name}")
    return target


def retain_assets(root: Path, release: Path) -> None:
    """Keep hashed assets accessible across upgrades and rollbacks for open tabs."""
    shared = root / 'shared'
    if shared.is_symlink() or (shared / 'assets').is_symlink():
        raise ValueError('Shared assets must not be symlinks')
    shared.mkdir(exist_ok=True)
    for source in (release / 'assets').rglob('*'):
        destination = shared / source.relative_to(release)
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if destination.read_bytes() != source.read_bytes():
                    raise ValueError('An immutable asset name has conflicting content')
                continue
            descriptor, temporary_name = tempfile.mkstemp(prefix='.asset-', dir=destination.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, 'wb') as output, source.open('rb') as input_file:
                    shutil.copyfileobj(input_file, output)
                temporary.chmod(0o644)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)


def install(archive: Path, digest: str, root: Path) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("A full lowercase SHA-256 is required")
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise ValueError("Archive checksum mismatch")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    old = release_target(root, "current")
    release_target(root, "previous")
    releases = root / "releases"
    if releases.is_symlink():
        raise ValueError("Release directory must not be a symlink")
    releases.mkdir(exist_ok=True)
    target = releases / digest[:16]
    if target.exists():
        raise ValueError("Release already exists; use rollback or a new artifact")
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases))
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            entries = bundle.getmembers()
            if sum(item.size for item in entries) > MAX_BYTES or len(entries) > 10000:
                raise ValueError("Archive exceeds static release limits")
            names = set()
            for entry in entries:
                path = PurePosixPath(entry.name)
                if path.is_absolute() or '..' in path.parts or any(p.startswith('.') for p in path.parts):
                    raise ValueError("Unsafe archive path")
                if not entry.isdir() and not entry.isfile():
                    raise ValueError("Only regular files and directories are allowed")
                if path in names:
                    raise ValueError("Duplicate archive entry")
                names.add(path)
                destination = staging.joinpath(*path.parts)
                if entry.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.extractfile(entry) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(0o644)
        if not (staging / "index.html").is_file() or not (staging / "assets").is_dir():
            raise ValueError("Missing frontend entrypoint or assets")
        for directory in (staging, *(p for p in staging.rglob('*') if p.is_dir())):
            directory.chmod(0o755)
        retain_assets(root, staging)
        staging.rename(target)
        if old:
            switch_link(root, "previous", old)
        switch_link(root, "current", target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)  # Only this invocation's generated staging directory.
    return target.name


def rollback(root: Path) -> str:
    root = root.resolve()
    old, previous = release_target(root, "current"), release_target(root, "previous")
    if not old or not previous:
        raise ValueError("No previous release available")
    switch_link(root, "current", previous)
    switch_link(root, "previous", old)
    return previous.name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "rollback"])
    parser.add_argument("--root", type=Path, default=Path("/srv/mergen"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.action == "install" and (not args.archive or not args.sha256):
        parser.error("install requires --archive and --sha256")
    try:
        result = install(args.archive, args.sha256, args.root) if args.action == "install" else rollback(args.root)
        print(f"Active release: {result}")
    except (ValueError, OSError, tarfile.TarError) as exc:
        parser.exit(1, f"Deployment stopped: {exc}\n")
