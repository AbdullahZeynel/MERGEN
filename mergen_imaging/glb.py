"""GLB 2.0 writer for labelled tumour surfaces, and the region table itself.

The table below is the one source for what a region is called and how it is
coloured. The demo package writer (frontend/scripts/mesh_glb.py) imports it
rather than keeping its own copy, so a live result and a prepared demo cannot
end up drawn differently. The viewer's own copy is checked against this one by
mergen_imaging/test_runner.py.
"""
from __future__ import annotations

import json
import math
import struct

# BRAIN only ever appears in the prepared demo package: the live runner
# segments tumour regions and never produces an outer surface. It is listed
# here so both writers order and colour the four regions identically.
REGIONS = ("ET", "TC_NCR", "ED", "BRAIN")
COLORS = {
    "ET": (1.0, 0.349, 0.424, 0.75),
    "TC_NCR": (0.341, 0.808, 0.635, 0.75),
    "ED": (0.349, 0.620, 0.933, 0.75),
    "BRAIN": (0.886, 0.910, 0.941, 0.12),
}


def material(region: str) -> dict:
    """The glTF material a region is drawn with, shared by both writers."""
    return {"name": region, "pbrMetallicRoughness": {
        "baseColorFactor": list(COLORS[region]), "metallicFactor": 0,
        "roughnessFactor": 0.65}, "alphaMode": "BLEND", "doubleSided": True}


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * ((-len(data)) % 4)


def mesh_glb_bytes(meshes: dict) -> bytes:
    """Return one indexed triangle primitive per non-empty known region."""
    binary = bytearray()
    views, accessors, materials, gltf_meshes, nodes = [], [], [], [], []

    def view(payload: bytes, target: int) -> int:
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        binary.extend(payload)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(payload),
                      "target": target})
        return len(views) - 1

    for region in REGIONS:
        item = meshes.get(region)
        if item is None:
            continue
        vertices, faces = item.get("vertices"), item.get("faces")
        if (not isinstance(vertices, list) or not vertices
                or any(not isinstance(row, list) or len(row) != 3
                       or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                              for value in row) for row in vertices)):
            raise ValueError("invalid mesh vertices")
        if (not isinstance(faces, list) or not faces
                or any(not isinstance(row, list) or len(row) != 3
                       or any(not isinstance(value, int) or value < 0 or value >= len(vertices)
                              for value in row) for row in faces)):
            raise ValueError("invalid mesh faces")
        positions = b"".join(struct.pack("<fff", *map(float, row)) for row in vertices)
        wide = len(vertices) > 65535
        indices = [value for face in faces for value in face]
        packed_indices = b"".join(struct.pack("<I" if wide else "<H", value)
                                  for value in indices)
        position_view = view(positions, 34962)
        columns = tuple(zip(*vertices))
        accessors.append({"bufferView": position_view, "componentType": 5126,
                          "count": len(vertices), "type": "VEC3",
                          "min": [float(min(column)) for column in columns],
                          "max": [float(max(column)) for column in columns]})
        position_accessor = len(accessors) - 1
        index_view = view(packed_indices, 34963)
        accessors.append({"bufferView": index_view, "componentType": 5125 if wide else 5123,
                          "count": len(indices), "type": "SCALAR",
                          "min": [min(indices)], "max": [max(indices)]})
        index_accessor = len(accessors) - 1
        materials.append(material(region))
        gltf_meshes.append({"name": region, "extras": {"region": region}, "primitives": [{
            "attributes": {"POSITION": position_accessor}, "indices": index_accessor,
            "material": len(materials) - 1, "mode": 4}]})
        nodes.append({"name": region, "mesh": len(gltf_meshes) - 1,
                      "extras": {"region": region}})

    while len(binary) % 4:
        binary.append(0)
    document = {"asset": {"version": "2.0", "generator": "MERGEN live imaging"},
                "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
                "nodes": nodes, "meshes": gltf_meshes, "materials": materials,
                "accessors": accessors, "bufferViews": views,
                "buffers": [{"byteLength": len(binary)}]}
    json_chunk = _pad(json.dumps(document, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return b"".join((struct.pack("<4sII", b"glTF", 2, total),
                     struct.pack("<I4s", len(json_chunk), b"JSON"), json_chunk,
                     struct.pack("<I4s", len(binary), b"BIN\0"), bytes(binary)))

