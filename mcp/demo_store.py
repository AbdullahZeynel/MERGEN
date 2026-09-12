"""Read-only, bounded access to an explicitly configured demo package."""
import base64
import hashlib
import json
from pathlib import Path


class DemoStore:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.manifest = json.loads((self.root / 'manifest.json').read_text())
        if self.manifest.get('version') != 2:
            raise ValueError('Demo manifest version 2 required')
        self.cases = {case['id']: case for case in self.manifest['cases']}
        if len(self.cases) != len(self.manifest['cases']):
            raise ValueError('Duplicate case IDs')

    def asset(self, case_id, kind, axis=None, index=None, layer=None):
        case = self.cases.get(case_id)
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
        else:
            return {'error': 'invalid'}
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            return {'error': 'missing'}
        if path.stat().st_size > 8 * 1024 * 1024:
            return {'error': 'too_large'}
        payload = path.read_bytes()
        return {'mime': mime, 'sha256': hashlib.sha256(payload).hexdigest(),
                'base64': base64.b64encode(payload).decode('ascii')}
