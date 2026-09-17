"""Browser-facing gateway; all demo reads go through private MCP tools."""
import asyncio
import base64
import hashlib
import os
import re
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Response
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from backend.live_api import get_live_store, router as live_router

app = FastAPI(title='MERGEN demo gateway', docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(live_router)
MCP_URL = os.environ.get('MERGEN_MCP_URL', 'http://127.0.0.1:9010/mcp')
parsed = urlparse(MCP_URL)
if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password:
    raise ValueError('MCP URL must use private loopback HTTP')
slots = asyncio.Semaphore(4)
MESH_DIGEST = re.compile(r'^[0-9a-f]{64}$')


async def call_tool(name: str, arguments: dict):
    try:
        async with asyncio.timeout(15):
            async with slots:
                async with streamablehttp_client(MCP_URL) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(name, arguments)
                        if result.isError or not isinstance(result.structuredContent, dict):
                            raise ValueError('Invalid tool response')
                        return result.structuredContent
    except Exception:
        raise HTTPException(503, 'Demo MCP service unavailable') from None


async def asset_response(tool, arguments, expected_mime, *, expected_digest=None,
                         cache_control='private, max-age=60'):
    result = await call_tool(tool, arguments)
    if 'error' in result:
        raise HTTPException({'missing': 404, 'invalid': 400, 'too_large': 413}.get(result['error'], 502), 'Demo asset unavailable')
    try:
        payload = base64.b64decode(result['base64'], validate=True)
        digest = hashlib.sha256(payload).hexdigest()
        allowed_mimes = (expected_mime,) if isinstance(expected_mime, str) else expected_mime
        if (result['mime'] not in allowed_mimes or digest != result['sha256']
                or (expected_digest is not None and digest != expected_digest)
                or len(payload) > 8 * 1024 * 1024):
            raise ValueError('Invalid asset')
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, 'Invalid demo asset') from None
    return Response(payload, media_type=result['mime'], headers={
        'Cache-Control': cache_control, 'ETag': f'"{digest}"',
        'X-Content-Type-Options': 'nosniff', 'X-Mergen-Source': 'mcp'})


def collection_response(result: dict) -> dict:
    if result.get('error') == 'missing':
        raise HTTPException(404, 'Demo collection unavailable')
    if result.get('schemaVersion') not in (3, 4):
        raise HTTPException(502, 'Invalid demo collection')
    return result


def legacy_manifest(result: dict) -> dict:
    """Keep the deployed imaging UI working while demo packages move on."""
    if result.get('schemaVersion') not in (3, 4):
        return result
    cases = []
    for original in result.get('cases', []):
        case = dict(original)
        case_id = case.get('id')
        if 'previews' in case:
            case['previews'] = [
                {**preview, 'src': f"/api/demo/cases/{case_id}/slices/{preview.get('axis')}/{preview.get('index')}"}
                for preview in case['previews']
            ]
        if case.get('mesh'):
            match = re.search(r'/mesh/([0-9a-f]{64})\.glb$', str(case['mesh']))
            case['mesh'] = (f'/api/demo/cases/{case_id}/mesh/{match.group(1)}.glb'
                            if match else f'/api/demo/cases/{case_id}/mesh')
        cases.append(case)
    return {'version': 2, 'cases': cases}


@app.get('/api/health')
async def health(live_store=Depends(get_live_store)):
    await call_tool('list_cases', {})
    capabilities = live_store.available_capabilities()
    return {'demoMcp': 'ready', 'liveAi': 'ready' if capabilities else 'not_connected',
            'liveCapabilities': capabilities}


@app.get('/api/demo/cases')
async def cases(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    result = await call_tool('list_cases', {})
    return legacy_manifest(result)


@app.get('/api/demo/catalog')
async def catalog(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    result = await call_tool('list_catalog', {})
    if result.get('schemaVersion') != 3:
        raise HTTPException(502, 'Invalid demo catalog')
    return result


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases')
async def collection_cases(module: str, disease: str, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return collection_response(await call_tool('list_cases', {
        'module': module, 'disease': disease,
    }))


@app.get('/api/demo/cases/{case_id}/slices/{axis}/{index}')
async def slice_image(case_id: str, axis: Literal['axial', 'coronal', 'sagittal'], index: int):
    return await asset_response('get_slice', {'case_id': case_id, 'axis': axis, 'index': index}, 'image/png')


@app.get('/api/demo/cases/{case_id}/overlays/{layer}/{axis}/{index}')
async def overlay_image(case_id: str, layer: Literal['prediction', 'ground_truth'],
                        axis: Literal['axial', 'coronal', 'sagittal'], index: int):
    return await asset_response('get_overlay', {'case_id': case_id, 'layer': layer,
                                                'axis': axis, 'index': index}, 'image/png')


@app.get('/api/demo/cases/{case_id}/mesh')
async def mesh(case_id: str):
    return await asset_response('get_mesh', {'case_id': case_id},
                                ('application/json', 'model/gltf-binary'))


@app.get('/api/demo/cases/{case_id}/mesh/{digest}.glb')
async def immutable_mesh(case_id: str, digest: str):
    if not MESH_DIGEST.fullmatch(digest):
        raise HTTPException(404, 'Demo asset unavailable')
    return await asset_response(
        'get_mesh', {'case_id': case_id}, 'model/gltf-binary',
        expected_digest=digest, cache_control='public, max-age=31536000, immutable')


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}/slices/{axis}/{index}')
async def collection_slice(module: str, disease: str, case_id: str,
                           axis: Literal['axial', 'coronal', 'sagittal'], index: int):
    return await asset_response('get_slice', {
        'module': module, 'disease': disease, 'case_id': case_id,
        'axis': axis, 'index': index,
    }, 'image/png')


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}/overlays/{layer}/{axis}/{index}')
async def collection_overlay(module: str, disease: str, case_id: str,
                             layer: Literal['prediction', 'ground_truth'],
                             axis: Literal['axial', 'coronal', 'sagittal'], index: int):
    return await asset_response('get_overlay', {
        'module': module, 'disease': disease, 'case_id': case_id,
        'layer': layer, 'axis': axis, 'index': index,
    }, 'image/png')


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}/images/{kind}')
async def collection_pathology_image(module: str, disease: str, case_id: str,
                                     kind: Literal['attention', 'top_tiles', 'thumbnail']):
    return await asset_response('get_pathology_image', {
        'module': module, 'disease': disease, 'case_id': case_id, 'kind': kind,
    }, 'image/jpeg')


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}/report')
async def collection_case_report(module: str, disease: str, case_id: str):
    return await asset_response('get_case_report', {
        'module': module, 'disease': disease, 'case_id': case_id,
    }, 'application/json')


@app.get('/api/demo/modules/{module}/diseases/{disease}/examples/{example_id}/figure')
async def collection_example_figure(module: str, disease: str, example_id: str):
    return await asset_response('get_example_figure', {
        'module': module, 'disease': disease, 'example_id': example_id,
    }, 'image/png')


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}/mesh')
async def collection_mesh(module: str, disease: str, case_id: str):
    return await asset_response('get_mesh', {
        'module': module, 'disease': disease, 'case_id': case_id,
    }, ('application/json', 'model/gltf-binary'))


@app.get('/api/demo/modules/{module}/diseases/{disease}/cases/{case_id}/mesh/{digest}.glb')
async def immutable_collection_mesh(module: str, disease: str, case_id: str, digest: str):
    if not MESH_DIGEST.fullmatch(digest):
        raise HTTPException(404, 'Demo asset unavailable')
    return await asset_response(
        'get_mesh', {'module': module, 'disease': disease, 'case_id': case_id},
        'model/gltf-binary', expected_digest=digest,
        cache_control='public, max-age=31536000, immutable')
