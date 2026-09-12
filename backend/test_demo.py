"""Gateway and store boundaries. Synthetic bytes test transport, not medical output."""
import base64
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
        (collection / 'manifest.json').write_text(json.dumps({
            'schemaVersion': 3, 'module': 'imaging', 'disease': 'glioma',
            'cases': [{'id': 'V3-TEST', 'shape': [2, 2, 2]}],
        }))
        v3_slice = collection / 'cases/V3-TEST/slices/axial'
        v3_slice.mkdir(parents=True)
        (v3_slice / '0.png').write_bytes(b'v3-transport-test')
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
            'collections': [{'module': 'imaging', 'disease': 'glioma', 'caseCount': 1}],
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
        self.assertEqual(response.json(), {'version': 2, 'cases': manifest['cases']})

    async def test_unknown_asset_is_404(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
                self.assertEqual((await client.get('/api/demo/cases/UNKNOWN/mesh')).status_code, 404)
