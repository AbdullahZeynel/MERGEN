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
    health = json.loads(read('/api/health'))
    assert health['demoMcp'] == 'ready' and health['liveAi'] in ('ready', 'not_connected')
    catalog = json.loads(read('/api/demo/catalog'))
    assert catalog['schemaVersion'] == 3 and catalog['collections']
    selected = catalog['collections'][0]
    collection_base = (f'/api/demo/modules/{selected["module"]}'
                       f'/diseases/{selected["disease"]}/cases')
    manifest = json.loads(read(collection_base))
    assert manifest['schemaVersion'] == 3 and manifest['cases']
    legacy = json.loads(read('/api/demo/cases'))
    assert legacy['version'] == 2
    assert [case['id'] for case in legacy['cases']] == [case['id'] for case in manifest['cases']]
    paths = []
    for case in manifest['cases']:
        mesh = json.loads(read(case['mesh']))
        assert 'BRAIN' in mesh and any(key in mesh for key in ('ET', 'ED', 'TC_NCR'))
        previews = {preview['axis']: preview['index'] for preview in case['previews']}
        for axis, dimension in [('axial', 2), ('coronal', 1), ('sagittal', 0)]:
            for index in (0, case['shape'][dimension] // 2, case['shape'][dimension] - 1):
                paths.append(f'{collection_base}/{case["id"]}/slices/{axis}/{index}')
            paths.append(f'{collection_base}/{case["id"]}/overlays/prediction/{axis}/{previews[axis]}')
    with ThreadPoolExecutor(max_workers=10) as pool:
        for payload in pool.map(read, paths):
            assert payload.startswith(b'\x89PNG\r\n\x1a\n')
    print(f'PASS: v3 catalog, v2 compatibility, {len(manifest["cases"])} meshes, '
          f'{len(paths)} PNG assets, 10 concurrent HTTP requests, SHA-256 integrity. '
          'Not a 10-user capacity benchmark.')
