from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'mcp'))
from PIL import Image  # noqa: E402

from prepare_demo_v4 import TILE_COLUMNS, TILE_PX, build  # noqa: E402
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
        self.calibration = self.write_calibration()

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

    def write_slide(self, case_id, info, images=('attention.jpg', 'top_tiles.jpg'),
                    sheet=(TILE_COLUMNS, 2)):
        case_dir = self.wsi / case_id
        case_dir.mkdir(exist_ok=True)
        (case_dir / 'case_info.json').write_text(json.dumps(info))
        for name in images:
            if name == 'top_tiles.jpg':
                # A real montage: the generator measures this file.
                columns, rows = sheet
                Image.new('RGB', (columns * TILE_PX, rows * TILE_PX), 'white').save(
                    case_dir / name, 'JPEG')
            else:
                (case_dir / name).write_bytes(f'{name}-{case_id}'.encode())

    def write_figure(self, case_id, info):
        case_dir = self.mri / case_id
        case_dir.mkdir(exist_ok=True)
        (case_dir / 'case_info.json').write_text(json.dumps(info))
        (case_dir / 'overlay.png').write_bytes(f'figure-{case_id}'.encode())

    def write_calibration(self, threshold=0.45, metric='top2_gap_on_raw_ensemble_probs',
                          name='calibration.json') -> Path:
        path = self.root / name
        path.write_text(json.dumps({
            'abstention': {'metric': metric, 'chosen_threshold': threshold},
        }), encoding='utf-8')
        return path

    def build(self, output=None):
        return build(self.package, self.wsi, self.mri, output or self.output, self.calibration)

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


class ProductPredictionTests(DemoV4Tests):
    """The product model is the ensemble; the map is the single network."""

    HEADER = 'patient_id,label,pred,p_A,p_O,p_G\n'

    def write_predictions(self, rows, name='predictions_test.csv') -> Path:
        path = self.root / name
        path.write_text(self.HEADER + ''.join(rows), encoding='utf-8')
        return path

    def build_with(self, rows):
        return build(self.package, self.wsi, self.mri, self.output, self.calibration,
                     self.write_predictions(rows))

    def test_the_case_is_reported_with_the_ensemble_probabilities(self):
        self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'))
        # Tek ag O demis; urun toplulugu ayni sinifi baska olasilikla veriyor.
        self.build_with(['TCGA-AA-0001,O,O,0.3000,0.4000,0.3000\n'])
        store = DemoStore(self.output)
        collection = store.collections[('pathology', 'glioma')]
        case = collection['cases']['test_TCGA-AA-0001']
        self.assertEqual(case['predictionSource'], 'ensemble_cv_v1')
        self.assertEqual(case['prediction']['probabilities'],
                         {'A': 0.3, 'O': 0.4, 'G': 0.3})
        self.assertEqual(case['singleModel']['probabilities'], {'A': 0.02, 'O': 0.96, 'G': 0.02})
        self.assertEqual(case['modelVersion'], 'ensemble_cv_v1')
        # Cekimserlik urun olasiliklarindan yeniden hesaplanir: fark 0,1 < 0,45.
        self.assertTrue(case['needsExpertReview'])
        # Harita her zaman tek agdan gelir ve kayit bunu soyler.
        self.assertEqual(case['attention'], {'modelId': 'mergen-wsi-attention-mil',
                                             'modelVersion': 'mil_v1',
                                             'tilesEvaluated': 4096, 'scale': 'raw_weight'})
        manifest = json.loads((self.output / 'pathology/glioma/manifest.json').read_text())
        self.assertEqual((manifest['model']['version'], manifest['model']['ensemble']),
                         ('ensemble_cv_v1', True))
        self.assertNotIn('note', manifest['model'])
        # Paketin tasidigi aciklama haritayi cizen aga aittir, karari verene degil.
        self.assertEqual(manifest['attentionModel'], {
            'id': 'mergen-wsi-attention-mil', 'version': 'mil_v1', 'ensemble': False,
            'note': 'Example MIL, single network'})

    def test_a_case_with_no_ensemble_row_keeps_the_single_network(self):
        self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'))
        self.build_with(['TCGA-ZZ-9999,O,O,0.1000,0.8000,0.1000\n'])
        case = DemoStore(self.output).collections[('pathology', 'glioma')]['cases'][
            'test_TCGA-AA-0001']
        self.assertEqual(case['predictionSource'], 'mil_v1')
        self.assertNotIn('singleModel', case)

    def test_a_prediction_file_that_disagrees_with_the_case_is_refused(self):
        self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'))
        with self.assertRaisesRegex(ValueError, 'disagrees with the case reference'):
            self.build_with(['TCGA-AA-0001,G,G,0.1000,0.1000,0.8000\n'])

    def test_a_malformed_prediction_file_is_refused(self):
        self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'))
        for rows, message in (
            (['TCGA-AA-0001,O,O,0.3000,0.2000,0.3000\n'], 'sum to one'),
            (['TCGA-AA-0001,O,A,0.3000,0.4000,0.3000\n'], 'highest probability'),
            (['TCGA-AA-0001,O,O,0.3000,0.4000,0.3000\n'] * 2, 'Repeated patient'),
        ):
            with self.subTest(rows=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.build_with(rows)
        path = self.root / 'bad.csv'
        path.write_text('patient_id,pred\nTCGA-AA-0001,O\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Unexpected prediction columns'):
            build(self.package, self.wsi, self.mri, self.output, self.calibration, path)


class ReviewMarginTests(DemoV4Tests):
    """The abstention threshold is a measured number, not a constant we carry."""

    def test_the_manifest_flags_at_the_threshold_the_registry_measured(self):
        # Fark 0,50: 0,45 esiginde bayrak kapali, 0,60 esiginde acik. Esigi
        # koda gomen bir surum ikisinde de ayni bayragi yazardi.
        self.write_slide('test_TCGA-AA-0001', slide_info(
            'TCGA-AA-0001', probabilities={'A': 0.25, 'O': 0.75, 'G': 0.00}))
        for threshold, flagged in ((0.45, False), (0.6, True)):
            with self.subTest(threshold=threshold):
                self.calibration = self.write_calibration(
                    threshold, name=f'calibration-{threshold}.json')
                output = self.root / f'out-{threshold}'
                self.build(output)
                manifest = json.loads(
                    (output / 'pathology/glioma/manifest.json').read_text())
                self.assertEqual(manifest['reviewMargin'], threshold)
                case = next(item for item in manifest['cases']
                            if item['id'] == 'test_TCGA-AA-0001')
                self.assertEqual(case['needsExpertReview'], flagged)

    def test_refuses_a_threshold_measured_on_another_quantity(self):
        self.calibration = self.write_calibration(metric='max_probability')
        with self.assertRaisesRegex(ValueError, 'another quantity'):
            self.build()

    def test_refuses_a_calibration_file_without_a_usable_threshold(self):
        for payload, message in (
            ({}, 'no abstention block'),
            ({'abstention': {'metric': 'top2_gap_on_raw_ensemble_probs'}}, 'Invalid abstention'),
            ({'abstention': {'metric': 'top2_gap_on_raw_ensemble_probs',
                             'chosen_threshold': 0}}, 'Invalid abstention'),
        ):
            with self.subTest(message=message):
                path = self.root / 'broken.json'
                path.write_text(json.dumps(payload), encoding='utf-8')
                self.calibration = path
                with self.assertRaisesRegex(ValueError, message):
                    self.build(self.root / f'out-{message[:6]}')


class TileSheetTests(DemoV4Tests):
    """The sheet of top tiles is numbered on screen, so its layout is measured."""

    def test_records_the_layout_it_measured(self):
        self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'))
        self.build()
        store = DemoStore(self.output)
        case = store.collections[('pathology', 'glioma')]['cases']['test_TCGA-AA-0001']
        self.assertEqual(case['tileGrid'], {
            'tilePx': TILE_PX, 'columns': TILE_COLUMNS, 'rows': 2, 'count': TILE_COLUMNS * 2,
            'ordering': 'attention_desc', 'micronsPerPixel': 0.5})

    def test_refuses_a_sheet_that_is_not_that_montage(self):
        for sheet in ((TILE_COLUMNS + 1, 2), (TILE_COLUMNS - 1, 1)):
            self.write_slide('test_TCGA-AA-0001', slide_info('TCGA-AA-0001'), sheet=sheet)
            with self.assertRaisesRegex(ValueError, 'montage'):
                self.build()
        # A sheet whose sides are not whole tiles is refused as well.
        case_dir = self.wsi / 'test_TCGA-AA-0001'
        Image.new('RGB', (TILE_COLUMNS * TILE_PX, TILE_PX + 7), 'white').save(
            case_dir / 'top_tiles.jpg', 'JPEG')
        with self.assertRaisesRegex(ValueError, 'montage'):
            self.build()

    def test_refuses_more_cells_than_the_slide_had_tiles(self):
        # Otherwise an empty cell would be numbered as if a tile were there.
        info = slide_info('TCGA-AA-0001') | {'n_tiles_used': 6}
        self.write_slide('test_TCGA-AA-0001', info)
        with self.assertRaisesRegex(ValueError, 'more tiles than the slide used'):
            self.build()


if __name__ == '__main__':
    unittest.main()
