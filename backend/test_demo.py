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
        genomics = self.root_v3 / 'genomics/glioma-variant-pathogenicity'
        genomics.mkdir(parents=True)
        (genomics / 'manifest.json').write_text(json.dumps({
            'schemaVersion': 3, 'module': 'genomics',
            'disease': 'glioma-variant-pathogenicity',
            'cases': [{'id': 'GEN-TEST', 'reports': ['result', 'explanation']}],
        }))
        gen_case = genomics / 'cases/GEN-TEST'
        gen_case.mkdir(parents=True)
        (gen_case / 'result.json').write_bytes(b'{"transport":"test"}')
        (gen_case / 'input.json').write_bytes(b'{"transport":"not-listed"}')
        catalog = json.loads((self.root_v3 / 'catalog.json').read_text())
        catalog['collections'].append({
            'module': 'genomics', 'disease': 'glioma-variant-pathogenicity',
            'manifest': 'genomics/glioma-variant-pathogenicity/manifest.json',
        })
        (self.root_v3 / 'catalog.json').write_text(json.dumps(catalog))
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
                {'module': 'genomics', 'disease': 'glioma-variant-pathogenicity',
                 'caseCount': 1},
                {'module': 'imaging', 'disease': 'glioma', 'caseCount': 1},
            ],
        })
        manifest = self.store_v3.list_cases('imaging', 'glioma')
        self.assertEqual(manifest['cases'][0]['id'], 'V3-TEST')
        self.assertEqual(self.store_v3.list_cases('genomics', 'glioma')['error'], 'missing')
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
                response = await client.get('/api/demo/modules/genomics/diseases/glioma/cases')
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

    async def test_genomics_report_is_bounded(self):
        gen = ('GEN-TEST', 'report')
        ortak = {'module': 'genomics', 'disease': 'glioma-variant-pathogenicity'}
        ok = self.store_v3.asset(*gen, layer='result', **ortak)
        self.assertEqual(base64.b64decode(ok['base64']), b'{"transport":"test"}')
        self.assertEqual(ok['mime'], 'application/json')
        # manifest'te bildirilmeyen belge okunmaz, üretilmemiş belge de
        self.assertEqual(self.store_v3.asset(*gen, layer='input', **ortak)['error'], 'invalid')
        self.assertEqual(self.store_v3.asset(*gen, layer='explanation', **ortak)['error'], 'missing')
        # beyaz liste dışı ad ve dizin dışına çıkma denemesi
        for ad in ('gizli', '../catalog', 'result.json', ''):
            self.assertEqual(self.store_v3.asset(*gen, layer=ad, **ortak)['error'], 'invalid')
        # yanlış koleksiyon ya da bilinmeyen vaka
        self.assertEqual(
            self.store_v3.asset('GEN-TEST', 'report', layer='result',
                                module='imaging', disease='glioma')['error'], 'missing')
        self.assertEqual(self.store_v3.asset('YOK', 'report', layer='result', **ortak)['error'],
                         'missing')

    async def test_genomics_report_route_uses_mcp(self):
        asset = self.store_v3.asset('GEN-TEST', 'report', layer='result',
                                    module='genomics',
                                    disease='glioma-variant-pathogenicity')
        yol = ('/api/demo/modules/genomics/diseases/glioma-variant-pathogenicity'
               '/cases/GEN-TEST/report/result')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value=asset)) as call:
                response = await client.get(yol)
                self.assertEqual(response.content, b'{"transport":"test"}')
                self.assertEqual(response.headers['X-Mergen-Source'], 'mcp')
                call.assert_awaited_once_with('get_report', {
                    'module': 'genomics', 'disease': 'glioma-variant-pathogenicity',
                    'case_id': 'GEN-TEST', 'name': 'result',
                })
            with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
                self.assertEqual((await client.get(yol)).status_code, 404)
            # beyaz liste dışı belge adı route'a bile ulaşmaz
            with patch('backend.api.call_tool', AsyncMock()) as call:
                response = await client.get(yol.replace('/result', '/gizli'))
                self.assertEqual(response.status_code, 422)
                call.assert_not_awaited()

    async def test_unknown_asset_is_404(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
                self.assertEqual((await client.get('/api/demo/cases/UNKNOWN/mesh')).status_code, 404)
