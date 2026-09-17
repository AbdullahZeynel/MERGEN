"""Create compact GLB 2.0 files from reviewed mesh arrays.

Region names, colours and materials come from `mergen_imaging.glb`, which the
live runner also uses: the prepared demo and a live result must not end up
drawn differently. Only the numpy input handling and the content-addressed
file name live here.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mergen_imaging.glb import REGIONS, material  # noqa: E402


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * ((-len(data)) % 4)


def mesh_glb_bytes(meshes: dict) -> bytes:
    """Return a GLB with one indexed triangle primitive for each known region."""
    binary = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    materials: list[dict] = []
    gltf_meshes: list[dict] = []
    nodes: list[dict] = []

    def view(payload: bytes, target: int) -> int:
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        binary.extend(payload)
        buffer_views.append({
            'buffer': 0,
            'byteOffset': offset,
            'byteLength': len(payload),
            'target': target,
        })
        return len(buffer_views) - 1

    for region in REGIONS:
        item = meshes.get(region)
        if item is None:
            continue
        vertices = np.asarray(item.get('vertices'), dtype='<f4')
        faces_raw = np.asarray(item.get('faces'))
        if (vertices.ndim != 2 or vertices.shape[1:] != (3,) or not len(vertices)
                or not np.isfinite(vertices).all()):
            raise ValueError(f'Invalid vertices for {region}')
        if (faces_raw.ndim != 2 or faces_raw.shape[1:] != (3,) or not len(faces_raw)
                or not np.issubdtype(faces_raw.dtype, np.integer)
                or faces_raw.min() < 0 or faces_raw.max() >= len(vertices)):
            raise ValueError(f'Invalid faces for {region}')
        index_dtype = '<u2' if len(vertices) <= 65535 else '<u4'
        component_type = 5123 if index_dtype == '<u2' else 5125
        faces = faces_raw.astype(index_dtype, copy=False).reshape(-1)

        position_view = view(vertices.tobytes(order='C'), 34962)
        positions = {
            'bufferView': position_view,
            'componentType': 5126,
            'count': len(vertices),
            'type': 'VEC3',
            'min': vertices.min(axis=0).astype(float).tolist(),
            'max': vertices.max(axis=0).astype(float).tolist(),
        }
        accessors.append(positions)
        position_accessor = len(accessors) - 1

        index_view = view(faces.tobytes(order='C'), 34963)
        accessors.append({
            'bufferView': index_view,
            'componentType': component_type,
            'count': len(faces),
            'type': 'SCALAR',
            'min': [int(faces.min())],
            'max': [int(faces.max())],
        })
        index_accessor = len(accessors) - 1

        materials.append(material(region))
        gltf_meshes.append({
            'name': region,
            'extras': {'region': region},
            'primitives': [{
                'attributes': {'POSITION': position_accessor},
                'indices': index_accessor,
                'material': len(materials) - 1,
                'mode': 4,
            }],
        })
        nodes.append({
            'name': region,
            'mesh': len(gltf_meshes) - 1,
            'extras': {'region': region},
        })

    if not nodes:
        raise ValueError('No supported mesh regions')
    while len(binary) % 4:
        binary.append(0)
    document = {
        'asset': {'version': '2.0', 'generator': 'MERGEN mesh_glb.py'},
        'scene': 0,
        'scenes': [{'nodes': list(range(len(nodes)))}],
        'nodes': nodes,
        'meshes': gltf_meshes,
        'materials': materials,
        'accessors': accessors,
        'bufferViews': buffer_views,
        'buffers': [{'byteLength': len(binary)}],
    }
    json_chunk = _pad(json.dumps(document, separators=(',', ':')).encode('utf-8'), b' ')
    binary_chunk = bytes(binary)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    return b''.join((
        struct.pack('<4sII', b'glTF', 2, total),
        struct.pack('<I4s', len(json_chunk), b'JSON'), json_chunk,
        struct.pack('<I4s', len(binary_chunk), b'BIN\x00'), binary_chunk,
    ))


def write_mesh_glb(meshes: dict, directory: Path) -> tuple[Path, str]:
    payload = mesh_glb_bytes(meshes)
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f'mesh-{digest}.glb'
    path.write_bytes(payload)
    return path, digest
