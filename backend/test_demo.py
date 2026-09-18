"""Gateway and store boundaries. Synthetic bytes test transport, not medical output."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from backend.api import app

spec = importlib.util.spec_from_file_location('demo_store', Path(__file__).parents[1] / 'mcp/demo_store.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DemoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'manifest.json').write_text(json.dumps({'version': 2, 'cases': [{'id': 'TEST', 'shape': [2, 2, 2], 'overlays': ['prediction', 'ground_truth']}]}))
        directory = self.root / 'TEST/slices/axial'
        directory.mkdir(parents=True)
        (directory / '0.png').write_bytes(b'transport-test')
        overlay = self.root / 'TEST/overlays/prediction/axial'
        overlay.mkdir(parents=True)
        (overlay / '0.png').write_bytes(b'overlay-test')
        self.store = module.DemoStore(self.root)

        self.tmp_v3 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_v3.cleanup)
        self.root_v3 = Path(self.tmp_v3.name)
        (self.root_v3 / 'catalog.json').write_text(json.dumps({
            'schemaVersion': 3,
            'collections': [{
                'module': 'imaging', 'disease': 'glioma',
                'manifest': 'imaging/glioma/manifest.json',
            }],
        }))
        collection = self.root_v3 / 'imaging/glioma'
        collection.mkdir(parents=True)
        self.glb_payload = b'glTF\x02\x00\x00\x00transport-test'
        self.glb_digest = hashlib.sha256(self.glb_payload).hexdigest()
        (collection / 'manifest.json').write_text(json.dumps({
            'schemaVersion': 3, 'module': 'imaging', 'disease': 'glioma',
            'cases': [{'id': 'V3-TEST', 'shape': [2, 2, 2],
                       'mesh': ('/api/demo/modules/imaging/diseases/glioma/cases/'
                                f'V3-TEST/mesh/{self.glb_digest}.glb')}],
        }))
        v3_slice = collection / 'cases/V3-TEST/slices/axial'
        v3_slice.mkdir(parents=True)
        (v3_slice / '0.png').write_bytes(b'v3-transport-test')
        (collection / 'cases/V3-TEST' / f'mesh-{self.glb_digest}.glb').write_bytes(
            self.glb_payload)
        self.store_v3 = module.DemoStore(self.root_v3)

    async def test_bounds_and_unknown_case(self):
        for axis, index in [('axial', -1), ('axial', 2), ('../', 0)]:
            self.assertEqual(self.store.asset('TEST', 'slice', axis, index)['error'], 'invalid')
        self.assertEqual(self.store.asset('../outside', 'mesh')['error'], 'missing')

    async def test_symlink_escape(self):
        (self.root / 'TEST/mesh_ensemble.json').symlink_to('/etc/hosts')
        self.assertEqual(self.store.asset('TEST', 'mesh')['error'], 'missing')

    async def test_v3_catalog_filters_and_isolates_assets(self):
        self.assertEqual(self.store_v3.catalog(), {
            'schemaVersion': 3,
            'collections': [
                {'module': 'imaging', 'disease': 'glioma', 'caseCount': 1},
            ],
        })
        manifest = self.store_v3.list_cases('imaging', 'glioma')
        self.assertEqual(manifest['cases'][0]['id'], 'V3-TEST')
        self.assertEqual(self.store_v3.list_cases('unknown', 'glioma')['error'], 'missing')
        result = self.store_v3.asset('V3-TEST', 'slice', 'axial', 0,
                                     module='imaging', disease='glioma')
        self.assertEqual(base64.b64decode(result['base64']), b'v3-transport-test')
        self.assertEqual(self.store_v3.asset('V3-TEST', 'slice', 'axial', 0,
                                             module='../imaging', disease='glioma')['error'], 'missing')

    async def test_asset_and_gateway_integrity(self):
        result = self.store.asset('TEST', 'slice', 'axial', 0)
        self.assertEqual(base64.b64decode(result['base64']), b'transport-test')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=result)) as call:
                response = await client.get('/api/demo/cases/TEST/slices/axial/0')
                self.assertEqual(response.content, b'transport-test')
                self.assertEqual(response.headers['x-mergen-source'], 'mcp')
                call.assert_awaited_once_with('get_slice', {'case_id': 'TEST', 'axis': 'axial', 'index': 0})
            result['sha256'] = 'wrong'
            with patch('backend.api.call_tool', AsyncMock(return_value=result)):
                self.assertEqual((await client.get('/api/demo/cases/TEST/slices/axial/0')).status_code, 502)

    async def test_hashed_glb_is_immutable_and_digest_bound(self):
        asset = self.store_v3.asset('V3-TEST', 'mesh', module='imaging', disease='glioma')
        self.assertEqual(asset['mime'], 'model/gltf-binary')
        self.assertEqual(base64.b64decode(asset['base64']), self.glb_payload)
        path = f'/api/demo/cases/V3-TEST/mesh/{self.glb_digest}.glb'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=asset)):
                response = await client.get(path)
                self.assertEqual(response.content, self.glb_payload)
                self.assertEqual(response.headers['content-type'], 'model/gltf-binary')
                self.assertEqual(response.headers['cache-control'],
                                 'public, max-age=31536000, immutable')
            with patch('backend.api.call_tool', AsyncMock(return_value=asset)):
                wrong = '0' * 64
                self.assertEqual((await client.get(path.replace(self.glb_digest, wrong))).status_code,
                                 502)
            self.assertEqual((await client.get(path.replace(self.glb_digest, 'invalid'))).status_code,
                             404)
        glb_path = self.root_v3 / 'imaging/glioma/cases/V3-TEST' / f'mesh-{self.glb_digest}.glb'
        glb_path.write_bytes(b'tampered')
        self.assertEqual(self.store_v3.asset('V3-TEST', 'mesh', module='imaging',
                                             disease='glioma')['error'], 'invalid')

    async def test_overlay_is_bounded_and_uses_mcp(self):
        result = self.store.asset('TEST', 'overlay', 'axial', 0, 'prediction')
        self.assertEqual(base64.b64decode(result['base64']), b'overlay-test')
        self.assertEqual(self.store.asset('TEST', 'overlay', 'axial', 0, '../')['error'], 'invalid')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=result)) as call:
                response = await client.get('/api/demo/cases/TEST/overlays/prediction/axial/0')
                self.assertEqual(response.content, b'overlay-test')
                call.assert_awaited_once_with('get_overlay', {'case_id': 'TEST', 'layer': 'prediction', 'axis': 'axial', 'index': 0})

    async def test_disconnected_mcp_does_not_return_demo(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.streamablehttp_client', side_effect=ConnectionError):
                self.assertEqual((await client.get('/api/demo/cases')).status_code, 503)

    async def test_catalog_and_filtered_collection_use_mcp(self):
        catalog = self.store_v3.catalog()
        manifest = self.store_v3.list_cases('imaging', 'glioma')
        asset = self.store_v3.asset('V3-TEST', 'slice', 'axial', 0)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=catalog)) as call:
                response = await client.get('/api/demo/catalog')
                self.assertEqual(response.json(), catalog)
                call.assert_awaited_once_with('list_catalog', {})
            with patch('backend.api.call_tool', AsyncMock(return_value=manifest)) as call:
                response = await client.get('/api/demo/modules/imaging/diseases/glioma/cases')
                self.assertEqual(response.json(), manifest)
                call.assert_awaited_once_with('list_cases', {'module': 'imaging', 'disease': 'glioma'})
            with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
                response = await client.get('/api/demo/modules/unknown/diseases/glioma/cases')
                self.assertEqual(response.status_code, 404)
            with patch('backend.api.call_tool', AsyncMock(return_value=asset)) as call:
                response = await client.get(
                    '/api/demo/modules/imaging/diseases/glioma/cases/V3-TEST/slices/axial/0')
                self.assertEqual(response.content, b'v3-transport-test')
                call.assert_awaited_once_with('get_slice', {
                    'module': 'imaging', 'disease': 'glioma', 'case_id': 'V3-TEST',
                    'axis': 'axial', 'index': 0,
                })

    async def test_legacy_case_route_normalizes_v3_collection(self):
        manifest = self.store_v3.list_cases('imaging', 'glioma')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=manifest)):
                response = await client.get('/api/demo/cases')
        expected = dict(manifest['cases'][0])
        expected['mesh'] = f'/api/demo/cases/V3-TEST/mesh/{self.glb_digest}.glb'
        self.assertEqual(response.json(), {'version': 2, 'cases': [expected]})

    async def test_unknown_asset_is_404(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
                self.assertEqual((await client.get('/api/demo/cases/UNKNOWN/mesh')).status_code, 404)


PATHOLOGY_CASES = '/api/demo/modules/pathology/diseases/glioma/cases'


def slide(case_id, probabilities, predicted, reference, review):
    """One prepared slide record; synthetic classes test the contract, not a model."""
    case = {
        'schemaVersion': 4, 'module': 'pathology', 'disease': 'glioma',
        'caseId': case_id, 'id': case_id, 'patientId': f'PATIENT-{case_id}',
        'mode': 'demo', 'status': 'demo_ready', 'split': 'test',
        'prediction': {'class': predicted, 'probabilities': probabilities},
        'needsExpertReview': review,
        'assets': {
            'attention': f'{PATHOLOGY_CASES}/{case_id}/images/attention',
            'top_tiles': f'{PATHOLOGY_CASES}/{case_id}/images/top_tiles',
            'report': f'{PATHOLOGY_CASES}/{case_id}/report',
        },
    }
    if reference is not None:
        case['reference'] = {'class': reference}
        case['agreesWithReference'] = predicted == reference
    return case


class PathologyCollectionTests(unittest.IsolatedAsyncioTestCase):
    """Demo v4: a second collection whose records carry classes, not slices."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.imaging = self.root / 'imaging/glioma'
        self.pathology = self.root / 'pathology/glioma'
        (self.root / 'catalog.json').write_text(json.dumps({
            'schemaVersion': 3,
            'collections': [
                {'module': 'imaging', 'disease': 'glioma',
                 'manifest': 'imaging/glioma/manifest.json'},
                {'module': 'pathology', 'disease': 'glioma',
                 'manifest': 'pathology/glioma/manifest.json'},
            ],
        }))
        (self.imaging / 'cases/V4-TEST/slices/axial').mkdir(parents=True)
        (self.imaging / 'cases/V4-TEST/slices/axial/0.png').write_bytes(b'v4-slice')
        (self.imaging / 'examples/FIG-1').mkdir(parents=True)
        (self.imaging / 'examples/FIG-1/figure.png').write_bytes(b'v4-figure')
        for case_id in ('SLIDE-1', 'SLIDE-2'):
            case_dir = self.pathology / 'cases' / case_id
            case_dir.mkdir(parents=True)
            (case_dir / 'attention.jpg').write_bytes(f'attention-{case_id}'.encode())
            (case_dir / 'top_tiles.jpg').write_bytes(f'tiles-{case_id}'.encode())
            (case_dir / 'report.json').write_text(json.dumps({'id': case_id}))
        self.write_imaging()
        self.write_pathology()
        self.store = module.DemoStore(self.root)

    def write_imaging(self, cases=None, example=None, **changes):
        figure = {
            'id': 'FIG-1', 'kind': 'figure', 'caseId': 'FIG-1', 'ruleVersion': 'test-rule',
            'regionVolumes': {'reference': {'TC': 0, 'WT': 40, 'ET': 0},
                              'prediction': {'TC': 0, 'WT': 42, 'ET': 0}},
            'dice': {'TC': 1.0, 'WT': 0.95, 'ET': 1.0},
            'hd95Mm': {'TC': None, 'WT': 2.0, 'ET': None},
            'reviewFlags': [],
            'figure': '/api/demo/modules/imaging/diseases/glioma/examples/FIG-1/figure',
        }
        manifest = {
            'schemaVersion': 4, 'module': 'imaging', 'disease': 'glioma',
            'cases': cases if cases is not None else [{'id': 'V4-TEST', 'shape': [2, 2, 2]}],
            'examples': [figure if example is None else figure | example],
        } | changes
        (self.imaging / 'manifest.json').write_text(json.dumps(manifest))

    def write_pathology(self, cases=None, **changes):
        manifest = {
            'schemaVersion': 4, 'module': 'pathology', 'disease': 'glioma',
            'reviewMargin': 0.45,
            'cases': cases if cases is not None else [
                slide('SLIDE-1', {'A': 0.02, 'O': 0.96, 'G': 0.02}, 'O', 'O', False),
                slide('SLIDE-2', {'A': 0.53, 'O': 0.46, 'G': 0.01}, 'A', 'O', True),
            ],
        } | changes
        (self.pathology / 'manifest.json').write_text(json.dumps(manifest))

    def reload(self):
        return module.DemoStore(self.root)

    async def test_catalog_lists_both_collections(self):
        self.assertEqual(self.store.catalog()['collections'], [
            {'module': 'imaging', 'disease': 'glioma', 'caseCount': 1},
            {'module': 'pathology', 'disease': 'glioma', 'caseCount': 2},
        ])
        self.assertEqual(self.store.list_cases('pathology', 'glioma')['schemaVersion'], 4)
        self.assertEqual(self.store.list_cases('pathology', 'unknown')['error'], 'missing')

    async def test_only_declared_assets_are_served(self):
        for kind, expected, mime in (('attention', b'attention-SLIDE-1', 'image/jpeg'),
                                     ('top_tiles', b'tiles-SLIDE-1', 'image/jpeg'),
                                     ('report', b'{"id": "SLIDE-1"}', 'application/json')):
            asset = self.store.asset('SLIDE-1', kind, module='pathology', disease='glioma')
            self.assertEqual((base64.b64decode(asset['base64']), asset['mime']), (expected, mime))
        (self.pathology / 'cases/SLIDE-1/thumbnail.jpg').write_bytes(b'undeclared')
        self.assertEqual(self.store.asset('SLIDE-1', 'thumbnail', module='pathology',
                                          disease='glioma')['error'], 'invalid')
        self.assertEqual(self.store.asset('SLIDE-1', 'mesh', module='pathology',
                                          disease='glioma')['error'], 'missing')
        self.assertEqual(self.store.asset('SLIDE-1', 'slice', 'axial', 0, module='pathology',
                                          disease='glioma')['error'], 'invalid')
        self.assertEqual(self.store.asset('../SLIDE-1', 'attention', module='pathology',
                                          disease='glioma')['error'], 'missing')

    async def test_review_flag_must_match_the_declared_margin(self):
        certain = slide('SLIDE-1', {'A': 0.02, 'O': 0.96, 'G': 0.02}, 'O', 'O', True)
        self.write_pathology([certain])
        with self.assertRaisesRegex(ValueError, 'review flag'):
            self.reload()
        uncertain = slide('SLIDE-2', {'A': 0.53, 'O': 0.46, 'G': 0.01}, 'A', 'O', False)
        self.write_pathology([uncertain])
        with self.assertRaisesRegex(ValueError, 'review flag'):
            self.reload()
        uncertain['needsExpertReview'] = True
        self.write_pathology([uncertain])
        self.assertEqual(len(self.reload().collections[('pathology', 'glioma')]['cases']), 1)

    async def test_a_tile_grid_must_be_a_grid_the_slide_could_fill(self):
        # The sheet of top tiles is numbered on screen, so a declared layout that
        # is not one — or that claims more cells than the slide had tiles — is
        # refused rather than drawn with invented ranks.
        grid = {'tilePx': 224, 'columns': 6, 'rows': 2, 'count': 12,
                'ordering': 'attention_desc', 'micronsPerPixel': 0.5}
        good = slide('SLIDE-1', {'A': 0.02, 'O': 0.96, 'G': 0.02}, 'O', 'O', False)
        self.write_pathology([{**good, 'tilesUsed': 4096, 'tileGrid': grid}])
        cases = self.reload().collections[('pathology', 'glioma')]['cases']
        self.assertEqual(cases['SLIDE-1']['tileGrid'], grid)
        for broken, tiles in (
            ({**grid, 'count': 13}, 4096),
            ({**grid, 'rows': 0}, 4096),
            ({**grid, 'ordering': 'as_found'}, 4096),
            ({**grid, 'micronsPerPixel': 0}, 4096),
            ({k: v for k, v in grid.items() if k != 'tilePx'}, 4096),
            (grid, 8),
        ):
            self.write_pathology([{**good, 'tilesUsed': tiles, 'tileGrid': broken}])
            with self.assertRaisesRegex(ValueError, 'tile grid'):
                self.reload()
        # A package that says nothing about the layout stays valid; the screen
        # then shows the sheet whole instead of numbering it.
        self.write_pathology([good])
        self.assertEqual(len(self.reload().collections[('pathology', 'glioma')]['cases']), 1)

    async def test_agreement_is_checked_against_the_reference(self):
        wrong = slide('SLIDE-2', {'A': 0.53, 'O': 0.46, 'G': 0.01}, 'A', 'O', True)
        wrong['agreesWithReference'] = True
        self.write_pathology([wrong])
        with self.assertRaisesRegex(ValueError, 'disagrees with its own reference'):
            self.reload()
        unreferenced = slide('SLIDE-1', {'A': 0.02, 'O': 0.96, 'G': 0.02}, 'O', None, False)
        unreferenced['agreesWithReference'] = True
        self.write_pathology([unreferenced])
        with self.assertRaisesRegex(ValueError, 'without a reference'):
            self.reload()

    async def test_a_case_cannot_borrow_another_case_asset(self):
        borrowed = slide('SLIDE-1', {'A': 0.02, 'O': 0.96, 'G': 0.02}, 'O', 'O', False)
        borrowed['assets']['attention'] = f'{PATHOLOGY_CASES}/SLIDE-2/images/attention'
        self.write_pathology([borrowed])
        with self.assertRaisesRegex(ValueError, 'Invalid pathology case record'):
            self.reload()
        self.write_pathology()
        self.write_imaging(cases=[{
            'id': 'V4-TEST', 'shape': [2, 2, 2],
            'previews': [{'axis': 'axial', 'index': 0, 'src': ('/api/demo/modules/imaging/'
                                                               'diseases/glioma/cases/OTHER/'
                                                               'slices/axial/0')}],
        }])
        with self.assertRaisesRegex(ValueError, 'outside its own case'):
            self.reload()

    async def test_pathology_manifest_must_declare_v4_and_a_margin(self):
        self.write_pathology(schemaVersion=3)
        with self.assertRaisesRegex(ValueError, 'does not match catalog'):
            self.reload()
        self.write_pathology()
        (self.pathology / 'manifest.json').write_text(json.dumps({
            **json.loads((self.pathology / 'manifest.json').read_text()), 'reviewMargin': None}))
        with self.assertRaisesRegex(ValueError, 'requires a review margin'):
            self.reload()

    async def test_a_score_without_a_reference_volume_is_refused(self):
        self.write_imaging(example={'regionVolumes': {'prediction': {'TC': 0, 'WT': 42, 'ET': 0}}})
        with self.assertRaisesRegex(ValueError, 'dice requires reference volumes'):
            self.reload()
        self.write_imaging(example={'regionVolumes': None, 'dice': None,
                                    'hd95Mm': {'TC': None, 'WT': 2.0, 'ET': None}})
        with self.assertRaisesRegex(ValueError, 'hd95Mm requires reference volumes'):
            self.reload()

    async def test_a_review_flag_carries_its_reason_and_numbers(self):
        flag = {'finding': 'tumor_core', 'severity': 'low_confidence',
                'reason': 'non_enhancing_tumor', 'message': 'Gerekçe metni.',
                'evidence': {'tumor_core_voxels': 94522, 'enhancing_voxels': 0}}
        self.write_imaging(example={'reviewFlags': [flag]})
        examples = self.reload().collections[('imaging', 'glioma')]['examples']
        self.assertEqual(examples['FIG-1']['reviewFlags'], [flag])
        for broken in ('tumor_core', {**flag, 'message': ''}, {**flag, 'evidence': {}},
                       {**flag, 'evidence': {'tumor_core_voxels': 'many'}}):
            self.write_imaging(example={'reviewFlags': [broken]})
            with self.assertRaisesRegex(ValueError, 'Invalid review flags'):
                self.reload()

    async def test_an_example_is_a_figure_not_a_case(self):
        collection = self.store.collections[('imaging', 'glioma')]
        self.assertNotIn('FIG-1', collection['cases'])
        figure = self.store.example('FIG-1', module='imaging', disease='glioma')
        self.assertEqual((base64.b64decode(figure['base64']), figure['mime']),
                         (b'v4-figure', 'image/png'))
        self.assertEqual(self.store.asset('FIG-1', 'slice', 'axial', 0, module='imaging',
                                          disease='glioma')['error'], 'missing')
        for example_id in ('../FIG-1', 'UNKNOWN'):
            self.assertEqual(self.store.example(example_id, module='imaging',
                                                disease='glioma')['error'], 'missing')
        self.assertEqual(self.store.example('FIG-1', module='pathology',
                                            disease='glioma')['error'], 'missing')
        self.write_imaging(example={'figure': ('/api/demo/modules/imaging/diseases/glioma/'
                                               'examples/FIG-2/figure')})
        with self.assertRaisesRegex(ValueError, 'Invalid demo example'):
            self.reload()

    async def test_gateway_serves_the_collection_through_mcp(self):
        manifest = self.store.list_cases('pathology', 'glioma')
        image = self.store.asset('SLIDE-1', 'attention', module='pathology', disease='glioma')
        report = self.store.asset('SLIDE-1', 'report', module='pathology', disease='glioma')
        figure = self.store.example('FIG-1', module='imaging', disease='glioma')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=manifest)) as call:
                response = await client.get('/api/demo/modules/pathology/diseases/glioma/cases')
                self.assertEqual(response.json(), manifest)
                call.assert_awaited_once_with('list_cases', {'module': 'pathology',
                                                             'disease': 'glioma'})
            with patch('backend.api.call_tool', AsyncMock(return_value=image)) as call:
                response = await client.get(f'{PATHOLOGY_CASES}/SLIDE-1/images/attention')
                self.assertEqual(response.content, b'attention-SLIDE-1')
                self.assertEqual(response.headers['content-type'], 'image/jpeg')
                call.assert_awaited_once_with('get_pathology_image', {
                    'module': 'pathology', 'disease': 'glioma', 'case_id': 'SLIDE-1',
                    'kind': 'attention'})
            with patch('backend.api.call_tool', AsyncMock(return_value=report)) as call:
                response = await client.get(f'{PATHOLOGY_CASES}/SLIDE-1/report')
                self.assertEqual(response.json(), {'id': 'SLIDE-1'})
                call.assert_awaited_once_with('get_case_report', {
                    'module': 'pathology', 'disease': 'glioma', 'case_id': 'SLIDE-1'})
            with patch('backend.api.call_tool', AsyncMock(return_value=figure)) as call:
                response = await client.get('/api/demo/modules/imaging/diseases/glioma/'
                                            'examples/FIG-1/figure')
                self.assertEqual(response.content, b'v4-figure')
                call.assert_awaited_once_with('get_example_figure', {
                    'module': 'imaging', 'disease': 'glioma', 'example_id': 'FIG-1'})
            with patch('backend.api.call_tool', AsyncMock(return_value=image)):
                self.assertEqual((await client.get(
                    f'{PATHOLOGY_CASES}/SLIDE-1/images/heatmap')).status_code, 422)

    async def test_legacy_route_still_normalizes_a_v4_imaging_manifest(self):
        manifest = self.store.list_cases('imaging', 'glioma')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=manifest)):
                response = await client.get('/api/demo/cases')
        self.assertEqual(response.json(), {'version': 2, 'cases': manifest['cases']})
