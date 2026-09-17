"""Derive the locked-test numbers the interface is allowed to show.

The validation section must not carry hand-typed scores. This script reads the
model registry, keeps only the product configurations on their locked test
splits, and writes `frontend/src/data/lockedTest.json`. The interface parses
that file; `test_locked_test_metrics.py` re-derives it and fails when the
committed file and the registry disagree, so a re-measured model cannot leave a
stale number on the screen.

Validation-split and smoke results are refused on purpose: they are not product
claims (see models/registry/RESULTS_SUMMARY.md).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / 'frontend/src/data/lockedTest.json'
# Product configuration of the MRI rule: stratified weights plus the TC_MIN
# floor. The other variants in the file are ablations and single networks.
SEGMENTATION = 'models/registry/mergen-uwcse/uwcse_v3/segmentation_metrics.json'
SEGMENTATION_VARIANT = 'V4_UWCSE_Full'
REGIONS = ('TC', 'WT', 'ET', 'Mean')
# Product configuration of the pathology model: the 5-fold ensemble, read once
# on the locked test split. `mil_v1` is the single network the demo slides come
# from and is reported beside it, not instead of it.
PATHOLOGY = 'models/registry/mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json'
CALIBRATION = 'models/registry/mergen-wsi-attention-mil/results/ensemble_cv_v1/calibration.json'
CLASSES = ('A', 'O', 'G')
PATHOLOGY_METRICS = {
    'macroF1': 'macro_f1',
    'balancedAccuracy': 'balanced_accuracy',
    'auroc': 'auroc_macro_ovr',
    'mcc': 'mcc',
}
PLACES = 4


def _load(relative: str) -> dict:
    return json.loads((REPO / relative).read_text(encoding='utf-8'))


def _interval(value: float, low: float | None = None, high: float | None = None) -> dict:
    out = {'value': round(float(value), PLACES)}
    if low is not None:
        out['low'] = round(float(low), PLACES)
    if high is not None:
        out['high'] = round(float(high), PLACES)
    return out


def segmentation() -> dict:
    raw = _load(SEGMENTATION)
    if raw['split'] != 'test':
        raise ValueError(f'Not a locked test split: {raw["split"]}')
    variant = raw['variants'][SEGMENTATION_VARIANT]
    return {
        'source': SEGMENTATION,
        'variant': SEGMENTATION_VARIANT,
        'n': int(raw['n']),
        'nValForWeights': int(raw['n_val_for_weights']),
        'dice': {
            region: _interval(
                variant[region]['mean'],
                variant[region]['ci95_low'],
                variant[region]['ci95_high'],
            )
            for region in REGIONS
        },
    }


def pathology() -> dict:
    raw = _load(PATHOLOGY)
    if raw['split'] != 'test':
        raise ValueError(f'Not a locked test split: {raw["split"]}')
    metrics, intervals = raw['metrics'], raw['bootstrap_ci95']
    return {
        'source': PATHOLOGY,
        'models': int(raw['n_models']),
        'n': int(metrics['n']),
        'metrics': {
            name: _interval(
                metrics[key],
                intervals.get(key, {}).get('ci95_low'),
                intervals.get(key, {}).get('ci95_high'),
            )
            for name, key in PATHOLOGY_METRICS.items()
        },
    }


def per_class() -> list:
    """Per-class precision, recall and F1 with the case count behind each one."""
    metrics = _load(PATHOLOGY)['metrics']
    matrix = metrics['confusion_matrix']
    rows = []
    for index, name in enumerate(CLASSES):
        rows.append({
            'class': name,
            'n': int(sum(matrix[index])),
            'precision': round(float(metrics['per_class_precision'][name]), PLACES),
            'recall': round(float(metrics['per_class_recall'][name]), PLACES),
            'f1': round(float(metrics['per_class_f1'][name]), PLACES),
        })
    if sum(row['n'] for row in rows) != int(metrics['n']):
        raise ValueError('Per-class counts do not add up to the split size')
    return rows


def abstention() -> dict:
    """What the abstention threshold did when it was read out on the locked test."""
    raw = _load(CALIBRATION)['abstention']
    readout = raw['test_readout']
    return {
        'source': CALIBRATION,
        'threshold': round(float(raw['chosen_threshold']), PLACES),
        'coverage': round(float(readout['coverage']), PLACES),
        'accuracyKept': round(float(readout['accuracy_kept']), PLACES),
        'accuracyAbstained': round(float(readout['accuracy_abstained']), PLACES),
        'errorsCaught': int(readout['errors_caught']),
        'errorsTotal': int(readout['errors_total']),
    }


def derive() -> dict:
    return {
        'split': 'locked test',
        'segmentation': segmentation(),
        'pathology': pathology() | {'perClass': per_class(), 'abstention': abstention()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='write frontend/src/data/lockedTest.json')
    arguments = parser.parse_args()
    text = json.dumps(derive(), indent=2, ensure_ascii=False) + '\n'
    if arguments.write:
        TARGET.write_text(text, encoding='utf-8')
        print(f'wrote {TARGET.relative_to(REPO)}')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
