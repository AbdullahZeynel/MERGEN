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
MESH_DIGEST = re.compile(r'^[0-9a-f]{64}$')
MODULE_SCHEMAS = {'imaging': (3, 4), 'pathology': (4,)}
GENERIC_SCHEMA = (3,)
PATHOLOGY_CLASSES = ('A', 'O', 'G')
PATHOLOGY_ASSETS = {
    'attention': ('attention.jpg', 'image/jpeg'),
    'top_tiles': ('top_tiles.jpg', 'image/jpeg'),
    'thumbnail': ('thumbnail.jpg', 'image/jpeg'),
    'report': ('report.json', 'application/json'),
}
PATHOLOGY_IMAGES = ('attention', 'top_tiles', 'thumbnail')
REGIONS = ('TC', 'WT', 'ET')
ASSET_LIMIT = 8 * 1024 * 1024


def _number(value, maximum=None):
    return (type(value) in (int, float) and value >= 0
            and (maximum is None or value <= maximum))


def _metric_table(table, maximum):
    """Region score table; a region with nothing to compare against stays null."""
    return (isinstance(table, dict) and set(table) == set(REGIONS)
            and all(value is None or _number(value, maximum) for value in table.values()))


def _check_metrics(record):
    """Measured segmentation numbers. A score without a reference is refused."""
    volumes = record.get('regionVolumes')
    if volumes is not None and (
            not isinstance(volumes, dict) or not volumes
            or set(volumes) - {'reference', 'prediction'}
            or any(not isinstance(side, dict) or set(side) != set(REGIONS)
                   or any(type(count) is not int or count < 0 for count in side.values())
                   for side in volumes.values())):
        raise ValueError('Invalid region volumes')
    for name, maximum in (('dice', 1), ('hd95Mm', None)):
        table = record.get(name)
        if table is None:
            continue
        if not _metric_table(table, maximum):
            raise ValueError(f'Invalid {name} table')
        if not isinstance(volumes, dict) or 'reference' not in volumes:
            raise ValueError(f'{name} requires reference volumes')
    flags = record.get('reviewFlags')
    if flags is not None and (not isinstance(flags, list)
                              or any(not isinstance(flag, str) or not flag for flag in flags)):
        raise ValueError('Invalid review flags')


def _api_paths(value):
    if isinstance(value, str):
        if value.startswith('/api/'):
            yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _api_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _api_paths(item)


def _check_case_links(case, module, disease):
    """Every asset a case points at is its own: no borrowing another patient's."""
    own = (f'/api/demo/modules/{module}/diseases/{disease}/cases/{case["id"]}/',
           f'/api/demo/cases/{case["id"]}/')
    for path in _api_paths(case):
        if not path.startswith(own):
            raise ValueError('Case record points outside its own case')


def _pathology_asset_urls(module, disease, case_id, kinds):
    prefix = f'/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}'
    return {kind: f'{prefix}/report' if kind == 'report' else f'{prefix}/images/{kind}'
            for kind in kinds}


def _check_pathology_case(case, module, disease, margin):
    prediction = case.get('prediction')
    probabilities = prediction.get('probabilities') if isinstance(prediction, dict) else None
    assets = case.get('assets')
    if (not isinstance(prediction, dict) or prediction.get('class') not in PATHOLOGY_CLASSES
            or not isinstance(probabilities, dict)
            or set(probabilities) != set(PATHOLOGY_CLASSES)
            or not all(_number(value, 1) for value in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > 0.01
            or type(case.get('needsExpertReview')) is not bool
            or not isinstance(assets, dict) or not assets
            or set(assets) - set(PATHOLOGY_ASSETS)
            or assets != _pathology_asset_urls(module, disease, case['id'], assets)):
        raise ValueError('Invalid pathology case record')
    reference = case.get('reference')
    if reference is None:
        if 'agreesWithReference' in case:
            raise ValueError('Pathology case claims agreement without a reference')
    elif (not isinstance(reference, dict) or reference.get('class') not in PATHOLOGY_CLASSES
            or case.get('agreesWithReference') is not (prediction['class'] == reference['class'])):
        raise ValueError('Pathology case disagrees with its own reference')
    ranked = sorted(probabilities.values(), reverse=True)
    if case['needsExpertReview'] is not (ranked[0] - ranked[1] < margin):
        raise ValueError('Pathology review flag does not match the declared margin')


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
        module = manifest.get('module')
        requires_shape = manifest.get('version') == 2 or module == 'imaging'
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
        if module == 'pathology':
            margin = manifest.get('reviewMargin')
            if not _number(margin, 1) or margin == 0:
                raise ValueError('Pathology manifest requires a review margin')
            for case in cases:
                _check_pathology_case(case, module, manifest.get('disease'), margin)
        for case in cases:
            _check_case_links(case, module or DEFAULT_MODULE,
                              manifest.get('disease') or DEFAULT_DISEASE)
            _check_metrics(case)
        result = {case['id']: case for case in cases}
        if len(result) != len(cases):
            raise ValueError('Duplicate case IDs')
        return result

    @staticmethod
    def _example_map(manifest: dict) -> dict:
        """Figures measured elsewhere; never served as a browsable case."""
        examples = manifest.get('examples')
        if examples is None:
            return {}
        if not isinstance(examples, list) or not examples:
            raise ValueError('Invalid demo examples')
        module, disease = manifest.get('module'), manifest.get('disease')
        for example in examples:
            if (not isinstance(example, dict)
                    or not CASE_ID.fullmatch(str(example.get('id', '')))
                    or example.get('kind') != 'figure'
                    or not isinstance(example.get('ruleVersion'), str)
                    or not example['ruleVersion']
                    or example.get('figure') != (f'/api/demo/modules/{module}/diseases/'
                                                 f'{disease}/examples/{example["id"]}/figure')):
                raise ValueError('Invalid demo example')
            _check_metrics(example)
        result = {example['id']: example for example in examples}
        if len(result) != len(examples):
            raise ValueError('Duplicate example IDs')
        return result

    def _load_v2(self):
        manifest = self._json_file(Path('manifest.json'))
        if manifest.get('version') != 2:
            raise ValueError('Demo manifest version 2 or catalog schema 3 required')
        cases = self._case_map(manifest)
        self.collections[(DEFAULT_MODULE, DEFAULT_DISEASE)] = {
            'manifest': manifest, 'cases': cases, 'examples': {},
            'base': self.root, 'root': self.root,
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
            if (manifest.get('schemaVersion') not in MODULE_SCHEMAS.get(module, GENERIC_SCHEMA)
                    or manifest.get('module') != module or manifest.get('disease') != disease):
                raise ValueError('Demo collection manifest does not match catalog')
            collection_root = (self.root / relative).resolve().parent
            self.collections[key] = {
                'manifest': manifest,
                'cases': self._case_map(manifest),
                'examples': self._example_map(manifest),
                'base': collection_root / 'cases',
                'root': collection_root,
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
        digest = None
        dimensions = {'axial': 2, 'coronal': 1, 'sagittal': 0}
        shape = case.get('shape')
        in_bounds = (isinstance(shape, list) and axis in dimensions and type(index) is int
                     and 0 <= index < shape[dimensions[axis]])
        if kind == 'slice':
            if not in_bounds:
                return {'error': 'invalid'}
            relative = Path(case_id) / 'slices' / axis / f'{index}.png'
            mime = 'image/png'
        elif kind == 'overlay':
            if not in_bounds or layer not in case.get('overlays', []):
                return {'error': 'invalid'}
            relative = Path(case_id) / 'overlays' / layer / axis / f'{index}.png'
            mime = 'image/png'
        elif kind in PATHOLOGY_ASSETS:
            declared = case.get('assets')
            if not isinstance(declared, dict) or kind not in declared:
                return {'error': 'invalid'}
            name, mime = PATHOLOGY_ASSETS[kind]
            relative = Path(case_id) / name
        elif kind == 'mesh':
            mesh_ref = case.get('mesh')
            if isinstance(mesh_ref, str) and mesh_ref.endswith('.glb'):
                digest = mesh_ref.rsplit('/mesh/', 1)[-1].removesuffix('.glb')
                allowed_refs = {
                    f'/api/demo/cases/{case_id}/mesh/{digest}.glb',
                    (f'/api/demo/modules/{module}/diseases/{disease}/cases/'
                     f'{case_id}/mesh/{digest}.glb'),
                }
                if not MESH_DIGEST.fullmatch(digest) or mesh_ref not in allowed_refs:
                    return {'error': 'invalid'}
                relative = Path(case_id) / f'mesh-{digest}.glb'
                mime = 'model/gltf-binary'
            else:
                relative = Path(case_id) / 'mesh_ensemble.json'
                mime = 'application/json'
        else:
            return {'error': 'invalid'}
        return self._payload(collection['base'], relative, mime, digest)

    def example(self, example_id, module=DEFAULT_MODULE, disease=DEFAULT_DISEASE):
        collection = self.collections.get((module, disease))
        if collection is None or example_id not in collection['examples']:
            return {'error': 'missing'}
        return self._payload(collection['root'] / 'examples',
                             Path(example_id) / 'figure.png', 'image/png')

    @staticmethod
    def _payload(base, relative, mime, digest=None):
        base = base.resolve()
        path = (base / relative).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return {'error': 'missing'}
        if path.stat().st_size > ASSET_LIMIT:
            return {'error': 'too_large'}
        payload = path.read_bytes()
        payload_digest = hashlib.sha256(payload).hexdigest()
        if digest is not None and payload_digest != digest:
            return {'error': 'invalid'}
        return {'mime': mime, 'sha256': payload_digest,
                'base64': base64.b64encode(payload).decode('ascii')}
