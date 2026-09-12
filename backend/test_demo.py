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

    async def test_bounds_and_unknown_case(self):
        for axis, index in [('axial', -1), ('axial', 2), ('../', 0)]:
            self.assertEqual(self.store.asset('TEST', 'slice', axis, index)['error'], 'invalid')
        self.assertEqual(self.store.asset('../outside', 'mesh')['error'], 'missing')

    async def test_symlink_escape(self):
        (self.root / 'TEST/mesh_ensemble.json').symlink_to('/etc/hosts')
        self.assertEqual(self.store.asset('TEST', 'mesh')['error'], 'missing')

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

    async def test_unknown_asset_is_404(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
                self.assertEqual((await client.get('/api/demo/cases/UNKNOWN/mesh')).status_code, 404)
