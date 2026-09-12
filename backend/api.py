"""Browser-facing gateway; all demo reads go through private MCP tools."""
import asyncio
import base64
import hashlib
import os
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Response
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

app = FastAPI(title='MERGEN demo gateway', docs_url=None, redoc_url=None, openapi_url=None)
MCP_URL = os.environ.get('MERGEN_MCP_URL', 'http://127.0.0.1:9010/mcp')
parsed = urlparse(MCP_URL)
if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password:
    raise ValueError('MCP URL must use private loopback HTTP')
slots = asyncio.Semaphore(4)


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


async def asset_response(tool, arguments, expected_mime):
    result = await call_tool(tool, arguments)
    if 'error' in result:
        raise HTTPException({'missing': 404, 'invalid': 400, 'too_large': 413}.get(result['error'], 502), 'Demo asset unavailable')
    try:
        payload = base64.b64decode(result['base64'], validate=True)
        digest = hashlib.sha256(payload).hexdigest()
        if result['mime'] != expected_mime or digest != result['sha256'] or len(payload) > 8 * 1024 * 1024:
            raise ValueError('Invalid asset')
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, 'Invalid demo asset') from None
    return Response(payload, media_type=expected_mime, headers={
        'Cache-Control': 'private, max-age=60', 'ETag': f'"{digest}"',
        'X-Content-Type-Options': 'nosniff', 'X-Mergen-Source': 'mcp'})


@app.get('/api/health')
async def health():
    await call_tool('list_cases', {})
    return {'demoMcp': 'ready', 'liveAi': 'not_connected'}


@app.get('/api/demo/cases')
async def cases(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return await call_tool('list_cases', {})


@app.get('/api/demo/cases/{case_id}/slices/{axis}/{index}')
async def slice_image(case_id: str, axis: Literal['axial', 'coronal', 'sagittal'], index: int):
    return await asset_response('get_slice', {'case_id': case_id, 'axis': axis, 'index': index}, 'image/png')


@app.get('/api/demo/cases/{case_id}/mesh')
async def mesh(case_id: str):
    return await asset_response('get_mesh', {'case_id': case_id}, 'application/json')
