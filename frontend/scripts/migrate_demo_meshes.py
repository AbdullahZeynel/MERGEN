"""Copy a schema-v3 demo package and replace legacy JSON meshes with hashed GLB."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from mesh_glb import write_mesh_glb


CASE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
COLLECTION_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path.name}')
    return value


def _inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError('Collection manifest escapes package root.')
    return candidate


def migrate(source: Path, output: Path) -> int:
    source = source.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; choose a new directory.')
    if not output.parent.is_dir():
        raise ValueError('Output parent directory does not exist.')
    if any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('Demo package must not contain symlinks.')
    catalog = _json(source / 'catalog.json')
    entries = catalog.get('collections')
    if catalog.get('schemaVersion') != 3 or not isinstance(entries, list):
        raise ValueError('Demo catalog schema version 3 required.')
    imaging = next((entry for entry in entries if entry.get('module') == 'imaging'), None)
    if (not isinstance(imaging, dict)
            or not isinstance(imaging.get('manifest'), str)
            or not isinstance(imaging.get('disease'), str)
            or not COLLECTION_ID.fullmatch(imaging['disease'])):
        raise ValueError('Imaging collection is missing.')
    manifest_ref = imaging['manifest']
    source_manifest = _inside(source, manifest_ref)

    staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}-', dir=output.parent))
    try:
        shutil.copytree(source, staging, symlinks=False, dirs_exist_ok=True)
        manifest_path = staging / source_manifest.relative_to(source)
        manifest = _json(manifest_path)
        if (manifest.get('schemaVersion') != 3 or manifest.get('module') != 'imaging'
                or manifest.get('disease') != imaging['disease']):
            raise ValueError('Imaging manifest does not match catalog.')
        cases = manifest.get('cases')
        if not isinstance(cases, list) or not cases:
            raise ValueError('Imaging manifest requires cases.')
        converted = 0
        for case in cases:
            case_id = case.get('id') if isinstance(case, dict) else None
            if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
                raise ValueError('Invalid imaging case ID.')
            mesh_ref = case.get('mesh')
            if isinstance(mesh_ref, str) and mesh_ref.endswith('.glb'):
                continue
            case_dir = manifest_path.parent / 'cases' / case_id
            legacy = case_dir / 'mesh_ensemble.json'
            if not legacy.is_file():
                raise ValueError(f'Legacy mesh is missing: {case_id}')
            _, digest = write_mesh_glb(_json(legacy), case_dir)
            legacy.unlink()
            case['mesh'] = (f'/api/demo/modules/{manifest["module"]}/diseases/'
                            f'{manifest["disease"]}/cases/{case_id}/mesh/{digest}.glb')
            converted += 1
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        temporary.replace(manifest_path)
        staging.replace(output)
        return converted
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(f'Converted {migrate(args.source, args.output)} meshes to hashed GLB.')
