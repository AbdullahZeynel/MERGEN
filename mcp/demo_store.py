"""Read-only, bounded access to explicitly configured demo packages."""
import base64
import hashlib
import json
import re
from pathlib import Path


DEFAULT_MODULE = 'imaging'
DEFAULT_DISEASE = 'glioma'
COLLECTION_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
CASE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
# Genomik vakada okunabilecek JSON belgeleri; serbest dosya adı kabul edilmez.
REPORT_NAMES = ('result', 'explanation', 'input')


class DemoStore:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.collections = {}
        catalog_path = self.root / 'catalog.json'
        if catalog_path.is_file():
            self._load_v3(self._json_file(Path('catalog.json')))
        else:
            self._load_v2()

    def _json_file(self, relative: Path) -> dict:
        path = (self.root / relative).resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError('Demo manifest path escapes package root')
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Demo manifest must be an object')
        return value

    @staticmethod
    def _case_map(manifest: dict) -> dict:
        cases = manifest.get('cases')
        if not isinstance(cases, list) or not cases:
            raise ValueError('Demo manifest requires cases')
        requires_shape = manifest.get('version') == 2 or manifest.get('module') == 'imaging'
        if any(
            not isinstance(case, dict)
            or not CASE_ID.fullmatch(str(case.get('id', '')))
            or (requires_shape and (
                not isinstance(case.get('shape'), list)
                or len(case['shape']) != 3
                or any(type(size) is not int or size <= 0 for size in case['shape'])
            ))
            for case in cases
        ):
            raise ValueError('Invalid case record')
        result = {case['id']: case for case in cases}
        if len(result) != len(cases):
            raise ValueError('Duplicate case IDs')
        return result

    def _load_v2(self):
        manifest = self._json_file(Path('manifest.json'))
        if manifest.get('version') != 2:
            raise ValueError('Demo manifest version 2 or catalog schema 3 required')
        cases = self._case_map(manifest)
        self.collections[(DEFAULT_MODULE, DEFAULT_DISEASE)] = {
            'manifest': manifest, 'cases': cases, 'base': self.root,
        }
        self.manifest = manifest

    def _load_v3(self, catalog: dict):
        entries = catalog.get('collections') if isinstance(catalog, dict) else None
        if not isinstance(catalog, dict) or catalog.get('schemaVersion') != 3 or not isinstance(entries, list) or not entries:
            raise ValueError('Demo catalog schema version 3 required')
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Invalid demo collection')
            module = entry.get('module')
            disease = entry.get('disease')
            manifest_ref = entry.get('manifest')
            if (not isinstance(module, str) or not COLLECTION_ID.fullmatch(module)
                    or not isinstance(disease, str) or not COLLECTION_ID.fullmatch(disease)
                    or not isinstance(manifest_ref, str)):
                raise ValueError('Invalid demo collection')
            key = (module, disease)
            if key in self.collections:
                raise ValueError('Duplicate demo collection')
            relative = Path(manifest_ref)
            manifest = self._json_file(relative)
            if (manifest.get('schemaVersion') != 3 or manifest.get('module') != module
                    or manifest.get('disease') != disease):
                raise ValueError('Demo collection manifest does not match catalog')
            self.collections[key] = {
                'manifest': manifest,
                'cases': self._case_map(manifest),
                'base': (self.root / relative).resolve().parent / 'cases',
            }
        default = self.collections.get((DEFAULT_MODULE, DEFAULT_DISEASE))
        self.manifest = default['manifest'] if default else next(iter(self.collections.values()))['manifest']

    def catalog(self) -> dict:
        collections = []
        for (module, disease), collection in sorted(self.collections.items()):
            collections.append({
                'module': module,
                'disease': disease,
                'caseCount': len(collection['cases']),
            })
        return {'schemaVersion': 3, 'collections': collections}

    def list_cases(self, module=DEFAULT_MODULE, disease=DEFAULT_DISEASE) -> dict:
        collection = self.collections.get((module, disease))
        if collection is None:
            return {'error': 'missing'}
        return collection['manifest']

    def asset(self, case_id, kind, axis=None, index=None, layer=None,
              module=DEFAULT_MODULE, disease=DEFAULT_DISEASE):
        collection = self.collections.get((module, disease))
        if collection is None:
            return {'error': 'missing'}
        case = collection['cases'].get(case_id)
        if case is None:
            return {'error': 'missing'}
        if kind == 'slice':
            dimensions = {'axial': 2, 'coronal': 1, 'sagittal': 0}
            if axis not in dimensions or type(index) is not int or not 0 <= index < case['shape'][dimensions[axis]]:
                return {'error': 'invalid'}
            relative = Path(case_id) / 'slices' / axis / f'{index}.png'
            mime = 'image/png'
        elif kind == 'overlay':
            dimensions = {'axial': 2, 'coronal': 1, 'sagittal': 0}
            if (layer not in case.get('overlays', []) or axis not in dimensions or type(index) is not int
                    or not 0 <= index < case['shape'][dimensions[axis]]):
                return {'error': 'invalid'}
            relative = Path(case_id) / 'overlays' / layer / axis / f'{index}.png'
            mime = 'image/png'
        elif kind == 'mesh':
            relative = Path(case_id) / 'mesh_ensemble.json'
            mime = 'application/json'
        elif kind == 'report':
            if layer not in REPORT_NAMES or layer not in case.get('reports', []):
                return {'error': 'invalid'}
            relative = Path(case_id) / f'{layer}.json'
            mime = 'application/json'
        else:
            return {'error': 'invalid'}
        base = collection['base'].resolve()
        path = (base / relative).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return {'error': 'missing'}
        if path.stat().st_size > 8 * 1024 * 1024:
            return {'error': 'too_large'}
        payload = path.read_bytes()
        return {'mime': mime, 'sha256': hashlib.sha256(payload).hexdigest(),
                'base64': base64.b64encode(payload).decode('ascii')}
