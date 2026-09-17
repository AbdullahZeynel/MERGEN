from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'mcp'))
from prepare_demo_v4 import build  # noqa: E402
from demo_store import DemoStore  # noqa: E402


def slide_info(patient, split='test', reference='O', predicted='O', probabilities=None):
    """Synthetic export record; the classes test the contract, not a model."""
    return {
        'patient_id': patient, 'split': split, 'true_class': reference,
        'predicted_class': predicted, 'correct': predicted == reference,
        'who_grade': 'G2', 'source_site': f'Example Center {patient[-1]}',
        'probabilities': probabilities or {'A': 0.02, 'O': 0.96, 'G': 0.02},
        'n_tiles_used': 4096,
        'attention_concentration': {'top1_share': 0.1, 'top10_share': 0.3,
                                    'entropy_normalised': 0.6},
        'model': 'Example MIL, single network',
        'files': {'attention.jpg': 'heat map', 'top_tiles.jpg': 'top tiles'},
    }


FLAG = {'finding': 'tumor_core', 'severity': 'low_confidence',
        'reason': 'non_enhancing_tumor', 'message': 'Gerekçe metni.',
        'evidence': {'tumor_core_voxels': 94522, 'enhancing_voxels': 0}}


def figure_info(case_id, reference={'TC': 0, 'WT': 40, 'ET': 0}, dice=None, hd95=None,
                flags=()):
    return {
        'case_id': case_id, 'selection_reason': 'çekirdeksiz — model doğru sustu',
        'split': 'locked test', 'who_grade': '3', 'diagnosis': 'Example diagnosis',
        'idh': 'mutated (NOS)', 'reference_voxels': reference,
        'predicted_voxels': {'TC': 0, 'WT': 42, 'ET': 0},
        'dice': dice if dice is not None else {'TC': 1.0, 'WT': 0.95, 'ET': 1.0},
        'hd95_mm': hd95 if hd95 is not None else {'TC': None, 'WT': 2.0, 'ET': None},
        'review_flags': list(flags), 'model': 'Example rule', 'slice_shown': 102,
        'files': {'overlay.png': 'FLAIR, T1c, referans ve tahmin yan yana'},
    }


class DemoV4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package, self.wsi = self.root / 'package', self.root / 'wsi'
        self.mri, self.output = self.root / 'mri', self.root / 'demo-v4'
        self.wsi.mkdir()
        self.mri.mkdir()
        # The export ships an index file next to the case folders.
        (self.wsi / 'INDEX.json').write_text('[]')
        self.write_package()
        self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'))
        self.write_slide('val_TCGA-BB-0002', slide_info(
            'TCGA-BB-0002', split='val', reference='O', predicted='A',
            probabilities={'A': 0.53, 'O': 0.46, 'G': 0.01}))
        self.write_figure('UCSF-PDGM-0231', figure_info('UCSF-PDGM-0231'))

    def write_package(self, case_id='MRI-1'):
        collection = self.package / 'imaging/glioma'
        slices = collection / f'cases/{case_id}/slices/axial'
        slices.mkdir(parents=True)
        (slices / '0.png').write_bytes(b'slice-bytes')
        (self.package / 'catalog.json').write_text(json.dumps({
            'schemaVersion': 3,
            'collections': [{'module': 'imaging', 'disease': 'glioma',
                             'manifest': 'imaging/glioma/manifest.json'}],
        }))
        (collection / 'manifest.json').write_text(json.dumps({
            'schemaVersion': 3, 'module': 'imaging', 'disease': 'glioma',
            'cases': [{
                'schemaVersion': 3, 'id': case_id, 'shape': [2, 2, 2],
                'previews': [{'axis': 'axial', 'index': 0,
                              'src': ('/api/demo/modules/imaging/diseases/glioma/cases/'
                                      f'{case_id}/slices/axial/0')}],
            }],
        }))

    def write_slide(self, case_id, info, images=('attention.jpg', 'top_tiles.jpg')):
        case_dir = self.wsi / case_id
        case_dir.mkdir(exist_ok=True)
        (case_dir / 'case_info.json').write_text(json.dumps(info))
        for name in images:
            (case_dir / name).write_bytes(f'{name}-{case_id}'.encode())

    def write_figure(self, case_id, info):
        case_dir = self.mri / case_id
        case_dir.mkdir(exist_ok=True)
        (case_dir / 'case_info.json').write_text(json.dumps(info))
        (case_dir / 'overlay.png').write_bytes(f'figure-{case_id}'.encode())

    def build(self, output=None):
        return build(self.package, self.wsi, self.mri, output or self.output)

    def test_produces_a_package_the_store_accepts(self):
        summary = self.build()
        self.assertEqual((summary['slideCases'], summary['examples'], summary['imagingCases']),
                         (2, 1, 1))
        store = DemoStore(self.output)
        self.assertEqual(store.catalog()['collections'], [
            {'module': 'imaging', 'disease': 'glioma', 'caseCount': 1},
            {'module': 'pathology', 'disease': 'glioma', 'caseCount': 2},
        ])
        attention = store.asset('test_TCGA-AA-0001', 'attention', module='pathology',
                                disease='glioma')
        self.assertEqual(base64.b64decode(attention['base64']),
                         b'attention.jpg-test_TCGA-AA-0001')
        report = json.loads(base64.b64decode(store.asset(
            'test_TCGA-AA-0001', 'report', module='pathology', disease='glioma')['base64']))
        self.assertEqual(report['sourceCaseInfo']['patient_id'], 'TCGA-AA-0001')
        figure = store.example('UCSF-PDGM-0231', module='imaging', disease='glioma')
        self.assertEqual(base64.b64decode(figure['base64']), b'figure-UCSF-PDGM-0231')
        self.assertEqual(base64.b64decode(store.asset('MRI-1', 'slice', 'axial', 0,
                                                      module='imaging',
                                                      disease='glioma')['base64']),
                         b'slice-bytes')

    def test_the_numbers_decide_review_and_disagreement(self):
        summary = self.build()
        self.assertEqual((summary['slidesNeedingReview'], summary['slidesAgainstReference']),
                         (1, 1))
        cases = {case['id']: case for case in json.loads(
            (self.output / 'pathology/glioma/manifest.json').read_text())['cases']}
        certain, uncertain = cases['test_TCGA-AA-0001'], cases['val_TCGA-BB-0002']
        self.assertEqual((certain['needsExpertReview'], certain['agreesWithReference']),
                         (False, True))
        self.assertEqual((uncertain['needsExpertReview'], uncertain['agreesWithReference']),
                         (True, False))
        self.assertEqual(uncertain['reference']['class'], 'O')

    def test_figures_stay_out_of_the_case_list(self):
        self.build()
        manifest = json.loads((self.output / 'imaging/glioma/manifest.json').read_text())
        self.assertEqual([case['id'] for case in manifest['cases']], ['MRI-1'])
        self.assertEqual([example['id'] for example in manifest['examples']],
                         ['UCSF-PDGM-0231'])
        self.assertEqual(manifest['examples'][0]['hd95Mm'], {'TC': None, 'WT': 2.0, 'ET': None})
        self.assertEqual(manifest['examples'][0]['ruleVersion'], 'uwcse-v3')
        self.assertFalse((self.output / 'imaging/glioma/cases/UCSF-PDGM-0231').exists())

    def test_refuses_a_class_that_is_not_the_top_probability(self):
        self.write_slide('test_TCGA-AA-0001', slide_info(
            'TCGA-AA-0001', reference='A', predicted='A',
            probabilities={'A': 0.02, 'O': 0.96, 'G': 0.02}))
        with self.assertRaisesRegex(ValueError, 'not the highest probability'):
            self.build()

    def test_refuses_a_correctness_flag_that_disagrees(self):
        info = slide_info('TCGA-AA-0001')
        info['correct'] = False
        self.write_slide('test_TCGA-AA-0001', info)
        with self.assertRaisesRegex(ValueError, 'disagrees with its own reference'):
            self.build()

    def test_refuses_a_folder_that_does_not_match_its_patient(self):
        self.write_slide('test_TCGA-ZZ-9999', slide_info('TCGA-AA-0001'))
        with self.assertRaisesRegex(ValueError, 'do not match'):
            self.build()

    def test_refuses_slides_from_different_models(self):
        info = slide_info('TCGA-AA-0001')
        info['model'] = 'Example MIL, five-fold ensemble'
        self.write_slide('test_TCGA-AA-0001', info)
        with self.assertRaisesRegex(ValueError, 'different models'):
            self.build()

    def test_carries_a_review_flag_with_its_reason_and_numbers(self):
        self.write_figure('UCSF-PDGM-0440', figure_info('UCSF-PDGM-0440', flags=[FLAG]))
        self.build()
        manifest = json.loads((self.output / 'imaging/glioma/manifest.json').read_text())
        flagged = next(item for item in manifest['examples'] if item['id'] == 'UCSF-PDGM-0440')
        self.assertEqual(flagged['reviewFlags'], [FLAG])
        for broken in ('tumor_core', {**FLAG, 'reason': ''}, {**FLAG, 'evidence': {}}):
            self.write_figure('UCSF-PDGM-0440', figure_info('UCSF-PDGM-0440', flags=[broken]))
            with self.assertRaisesRegex(ValueError, 'Invalid review flags'):
                self.build(self.root / f'out-{len(broken)}')

    def test_refuses_a_score_without_reference_volumes(self):
        self.write_figure('UCSF-PDGM-0231', figure_info('UCSF-PDGM-0231', reference=None))
        with self.assertRaisesRegex(ValueError, 'without reference volumes'):
            self.build()

    def test_refuses_a_slide_and_an_mri_case_sharing_an_identifier(self):
        self.package = self.root / 'shared-package'
        self.write_package(case_id='TCGA-AA-0001')
        with self.assertRaisesRegex(ValueError, 'share an identifier'):
            self.build()

    def test_does_not_publish_partial_output(self):
        self.write_slide('test_TCGA-CC-0003', slide_info('TCGA-CC-0003'),
                         images=('attention.jpg',))
        with self.assertRaisesRegex(ValueError, 'Missing top_tiles.jpg'):
            self.build()
        self.assertFalse(self.output.exists())
        self.assertEqual([path.name for path in self.output.parent.iterdir()
                          if path.name.startswith('.demo-v4')], [])

    def test_refuses_an_existing_output(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, 'Output already exists'):
            self.build()


if __name__ == '__main__':
    unittest.main()
