"""Gateway and store boundaries. Synthetic bytes test transport, not medical output."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.api import app

spec = importlib.util.spec_from_file_location('demo_store', Path(__file__).parents[1] / 'mcp/demo_store.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'manifest.json').write_text(json.dumps({'version': 2, 'cases': [{'id': 'TEST', 'shape': [2, 2, 2]}]}))
        directory = self.root / 'TEST/slices/axial'
        directory.mkdir(parents=True)
        (directory / '0.png').write_bytes(b'transport-test')
        self.store = module.DemoStore(self.root)

    def test_bounds_and_unknown_case(self):
        for axis, index in [('axial', -1), ('axial', 2), ('../', 0)]:
            self.assertEqual(self.store.asset('TEST', 'slice', axis, index)['error'], 'invalid')
        self.assertEqual(self.store.asset('../outside', 'mesh')['error'], 'missing')

    def test_symlink_escape(self):
        (self.root / 'TEST/mesh_ensemble.json').symlink_to('/etc/hosts')
        self.assertEqual(self.store.asset('TEST', 'mesh')['error'], 'missing')

    def test_asset_and_gateway_integrity(self):
        result = self.store.asset('TEST', 'slice', 'axial', 0)
        self.assertEqual(base64.b64decode(result['base64']), b'transport-test')
        with patch('backend.api.call_tool', AsyncMock(return_value=result)) as call:
            response = TestClient(app).get('/api/demo/cases/TEST/slices/axial/0')
            self.assertEqual(response.content, b'transport-test')
            self.assertEqual(response.headers['x-mergen-source'], 'mcp')
            call.assert_awaited_once_with('get_slice', {'case_id': 'TEST', 'axis': 'axial', 'index': 0})
        result['sha256'] = 'wrong'
        with patch('backend.api.call_tool', AsyncMock(return_value=result)):
            self.assertEqual(TestClient(app).get('/api/demo/cases/TEST/slices/axial/0').status_code, 502)

    def test_disconnected_mcp_does_not_return_demo(self):
        with patch('backend.api.streamablehttp_client', side_effect=ConnectionError):
            self.assertEqual(TestClient(app).get('/api/demo/cases').status_code, 503)

    def test_unknown_asset_is_404(self):
        with patch('backend.api.call_tool', AsyncMock(return_value={'error': 'missing'})):
            self.assertEqual(TestClient(app).get('/api/demo/cases/UNKNOWN/mesh').status_code, 404)
