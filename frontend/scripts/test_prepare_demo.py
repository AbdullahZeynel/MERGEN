from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_demo import DEFAULT_CASES, selected_cases
from mesh_glb import mesh_glb_bytes, write_mesh_glb
from migrate_demo_meshes import migrate


class CaseSelectionTests(unittest.TestCase):
    def test_default_keeps_reviewed_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(selected_cases(Path(temp), None, False), list(DEFAULT_CASES))

    def test_all_cases_is_sorted_and_ignores_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "UCSF-PDGM-0007").mkdir()
            (root / "UCSF-PDGM-0004").mkdir()
            (root / "notes.txt").write_text("ignored")
            self.assertEqual(selected_cases(root, None, True),
                             ["UCSF-PDGM-0004", "UCSF-PDGM-0007"])

    def test_selection_modes_are_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                selected_cases(Path(temp), ["UCSF-PDGM-0004"], True)


class MeshGlbTests(unittest.TestCase):
    mesh = {
        'ET': {
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            'faces': [[0, 1, 2]],
        },
        'BRAIN': {
            'vertices': [[-1, -1, -1], [2, -1, -1], [-1, 2, -1]],
            'faces': [[0, 1, 2]],
        },
    }

    def test_writes_valid_glb_header_and_region_metadata(self):
        payload = mesh_glb_bytes(self.mesh)
        magic, version, total = struct.unpack_from('<4sII', payload)
        self.assertEqual((magic, version, total), (b'glTF', 2, len(payload)))
        json_length, kind = struct.unpack_from('<I4s', payload, 12)
        self.assertEqual(kind, b'JSON')
        document = json.loads(payload[20:20 + json_length])
        self.assertEqual(document['asset']['version'], '2.0')
        self.assertEqual([node['name'] for node in document['nodes']], ['ET', 'BRAIN'])
        self.assertEqual(document['buffers'][0]['byteLength'],
                         len(payload) - (20 + json_length + 8))
        self.assertTrue(all(view['byteOffset'] % 4 == 0 for view in document['bufferViews']))

    def test_filename_is_the_payload_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path, digest = write_mesh_glb(self.mesh, Path(temp))
            self.assertEqual(path.name, f'mesh-{digest}.glb')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_rejects_out_of_bounds_faces(self):
        broken = {'ET': {'vertices': [[0, 0, 0]], 'faces': [[0, 1, 0]]}}
        with self.assertRaisesRegex(ValueError, 'Invalid faces'):
            mesh_glb_bytes(broken)

    def test_migrates_a_copy_and_removes_legacy_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / 'source', root / 'output'
            case_dir = source / 'imaging/glioma/cases/CASE-1'
            case_dir.mkdir(parents=True)
            (source / 'catalog.json').write_text(json.dumps({
                'schemaVersion': 3,
                'collections': [{'module': 'imaging', 'disease': 'glioma',
                                 'manifest': 'imaging/glioma/manifest.json'}],
            }))
            manifest = {
                'schemaVersion': 3, 'module': 'imaging', 'disease': 'glioma',
                'cases': [{'id': 'CASE-1', 'mesh':
                           '/api/demo/modules/imaging/diseases/glioma/cases/CASE-1/mesh'}],
            }
            (source / 'imaging/glioma/manifest.json').write_text(json.dumps(manifest))
            (case_dir / 'mesh_ensemble.json').write_text(json.dumps(self.mesh))
            self.assertEqual(migrate(source, output), 1)
            migrated = json.loads((output / 'imaging/glioma/manifest.json').read_text())
            mesh_ref = migrated['cases'][0]['mesh']
            self.assertRegex(mesh_ref, r'/mesh/[0-9a-f]{64}\.glb$')
            self.assertFalse((output / 'imaging/glioma/cases/CASE-1/mesh_ensemble.json').exists())
            self.assertEqual(len(list((output / 'imaging/glioma/cases/CASE-1').glob('mesh-*.glb'))), 1)
            self.assertTrue((source / 'imaging/glioma/cases/CASE-1/mesh_ensemble.json').exists())

    def test_failed_migration_does_not_publish_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / 'source', root / 'output'
            (source / 'imaging/glioma/cases/CASE-1').mkdir(parents=True)
            (source / 'catalog.json').write_text(json.dumps({
                'schemaVersion': 3,
                'collections': [{'module': 'imaging', 'disease': 'glioma',
                                 'manifest': 'imaging/glioma/manifest.json'}],
            }))
            (source / 'imaging/glioma/manifest.json').write_text(json.dumps({
                'schemaVersion': 3, 'module': 'imaging', 'disease': 'glioma',
                'cases': [{'id': 'CASE-1'}],
            }))
            with self.assertRaisesRegex(ValueError, 'Legacy mesh is missing'):
                migrate(source, output)
            self.assertFalse(output.exists())

    def test_rejects_manifest_outside_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / 'source', root / 'output'
            source.mkdir()
            outside = root / 'outside.json'
            outside.write_text('{}')
            (source / 'catalog.json').write_text(json.dumps({
                'schemaVersion': 3,
                'collections': [{'module': 'imaging', 'disease': 'glioma',
                                 'manifest': '../outside.json'}],
            }))
            with self.assertRaisesRegex(ValueError, 'escapes package root'):
                migrate(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
