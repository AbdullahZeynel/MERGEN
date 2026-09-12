"""Read-only smoke test against an already running local API and MCP pair."""
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = 'http://127.0.0.1:9000'


def read(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as response:
        payload = response.read()
        if '/slices/' in path or path.endswith('/mesh'):
            assert response.headers['X-Mergen-Source'] == 'mcp'
            assert response.headers['ETag'] == '"' + hashlib.sha256(payload).hexdigest() + '"'
        return payload


if __name__ == '__main__':
    assert json.loads(read('/api/health')) == {'demoMcp': 'ready', 'liveAi': 'not_connected'}
    manifest = json.loads(read('/api/demo/cases'))
    assert manifest['version'] == 2 and manifest['cases']
    paths = []
    for case in manifest['cases']:
        mesh = json.loads(read(case['mesh']))
        assert 'BRAIN' in mesh and any(key in mesh for key in ('ET', 'ED', 'TC_NCR'))
        for axis, dimension in [('axial', 2), ('coronal', 1), ('sagittal', 0)]:
            for index in (0, case['shape'][dimension] // 2, case['shape'][dimension] - 1):
                paths.append(f'/api/demo/cases/{case["id"]}/slices/{axis}/{index}')
    with ThreadPoolExecutor(max_workers=10) as pool:
        for payload in pool.map(read, paths):
            assert payload.startswith(b'\x89PNG\r\n\x1a\n')
    print(f'PASS: {len(manifest["cases"])} meshes, {len(paths)} slices, 10 concurrent HTTP requests, SHA-256 integrity. Not a 10-user capacity benchmark.')
