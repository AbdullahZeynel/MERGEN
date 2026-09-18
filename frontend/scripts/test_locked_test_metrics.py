"""The numbers on the validation screen must still be the registry's numbers."""

import json
import unittest
from pathlib import Path

import locked_test_metrics as metrics


class LockedTestMetrics(unittest.TestCase):
    def setUp(self):
        self.committed = json.loads(metrics.TARGET.read_text(encoding='utf-8'))

    def test_committed_file_is_what_the_registry_says_today(self):
        # Re-measure a model and this fails until the file is regenerated; a
        # stale score cannot sit on the screen unnoticed.
        self.assertEqual(self.committed, metrics.derive())

    def test_every_cited_source_file_exists(self):
        for section in ('segmentation', 'pathology'):
            path = metrics.REPO / self.committed[section]['source']
            self.assertTrue(path.is_file(), path)

    def test_refuses_a_validation_split_as_a_product_claim(self):
        # The validation split is optimistic by construction (best epoch chosen
        # on it). Pointing the deriver at it must raise, not quietly produce a
        # nicer number.
        original = metrics.PATHOLOGY
        val = 'models/registry/mergen-wsi-attention-mil/results/mil_v1/eval_val.json'
        self.assertTrue((metrics.REPO / val).is_file())
        metrics.PATHOLOGY = val
        try:
            with self.assertRaises(ValueError):
                metrics.pathology()
        finally:
            metrics.PATHOLOGY = original

    def test_reports_the_product_configuration_not_a_single_network(self):
        segmentation = self.committed['segmentation']
        self.assertEqual(segmentation['variant'], 'V4_UWCSE_Full')
        raw = json.loads((metrics.REPO / segmentation['source']).read_text(encoding='utf-8'))
        # The ablations and the single networks are all in the same file; the
        # screen must not be showing one of those by accident.
        for other in ('nnUNet', 'SwinUNETR', 'V0_Naive'):
            self.assertNotEqual(
                round(raw['variants'][other]['Mean']['mean'], metrics.PLACES),
                segmentation['dice']['Mean']['value'],
            )
        self.assertEqual(self.committed['pathology']['models'], 5)

    def test_class_rows_are_counted_from_the_confusion_matrix(self):
        rows = self.committed['pathology']['perClass']
        raw = json.loads((metrics.REPO / metrics.PATHOLOGY).read_text(encoding='utf-8'))
        matrix = raw['metrics']['confusion_matrix']
        for index, row in enumerate(rows):
            with self.subTest(klass=row['class']):
                self.assertEqual(row['n'], sum(matrix[index]))
                self.assertEqual(row['f1'],
                                 round(raw['metrics']['per_class_f1'][row['class']],
                                       metrics.PLACES))
        self.assertEqual(sum(row['n'] for row in rows), self.committed['pathology']['n'])

    def test_refuses_class_counts_that_do_not_add_up_to_the_split(self):
        # A matrix that lost a case must not quietly produce a smaller table;
        # the screen would then print class counts that contradict n=113.
        original = metrics._load
        raw = json.loads((metrics.REPO / metrics.PATHOLOGY).read_text(encoding='utf-8'))
        raw['metrics']['confusion_matrix'][0][0] -= 1
        metrics._load = lambda path: raw if path == metrics.PATHOLOGY else original(path)
        try:
            with self.assertRaises(ValueError):
                metrics.per_class()
        finally:
            metrics._load = original

    def test_the_abstention_readout_is_the_locked_test_one(self):
        block = self.committed['pathology']['abstention']
        raw = json.loads((metrics.REPO / block['source']).read_text(encoding='utf-8'))
        readout = raw['abstention']['test_readout']
        # Dogrulama bolmesinin rakamlari daha guzeldir; ekrana o gecerse
        # bayragin gercek davranisi gizlenmis olur.
        self.assertEqual(block['coverage'], round(readout['coverage'], metrics.PLACES))
        self.assertNotEqual(block['coverage'],
                            round(raw['abstention']['val']['coverage'], metrics.PLACES))
        self.assertEqual(block['threshold'], raw['abstention']['chosen_threshold'])
        self.assertLessEqual(block['errorsCaught'], block['errorsTotal'])

    def test_keeps_every_number_inside_its_own_interval(self):
        for section in ('segmentation', 'pathology'):
            table = self.committed[section].get('dice') or self.committed[section]['metrics']
            for name, interval in table.items():
                with self.subTest(section=section, metric=name):
                    self.assertLessEqual(interval['low'], interval['value'])
                    self.assertLessEqual(interval['value'], interval['high'])


if __name__ == '__main__':
    unittest.main()
