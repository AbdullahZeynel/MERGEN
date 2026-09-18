"""Build demo package v4: a pathology collection and the measured MRI figures.

No inference and no model runs here. Slide images, MRI figures and the numbers
beside them are copied from the frozen evidence export, and the imaging
collection is copied from an existing package. Every claim the export makes
about itself (declared class, correctness, scores) is recomputed or refused, and
the export's folder names must agree with the records inside them. The resulting
package is intentionally Git-ignored.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image

CASE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
COLLECTION_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
CLASSES = ('A', 'O', 'G')
REGIONS = ('TC', 'WT', 'ET')
SPLITS = ('train', 'val', 'test', 'locked test')
# `review_flags()` in models/imaging/uwcse_ensemble.py writes these fields.
FLAG_FIELDS = ('finding', 'severity', 'reason', 'message')
# Top-two probability gap under which the slide is handed to an expert. The
# number is not ours to choose: it was fitted on validation data and read out
# once on the locked test, and the validation screen quotes that read-out. So a
# package that decides with the ensemble reads the threshold from the same
# registry file rather than carrying a copy that can drift away from it.
REVIEW_MARGIN_METRIC = 'top2_gap_on_raw_ensemble_probs'
SLIDE_MODEL = {'id': 'mergen-wsi-attention-mil', 'version': 'mil_v1', 'ensemble': False}
# The product model is the five-fold ensemble; its per-case probabilities live in
# the registry next to the metrics they were read out with. The attention map is
# a different thing: it comes from the single network that can expose one, and
# the record says so rather than letting the reader assume both are the ensemble.
ENSEMBLE_MODEL = {'id': 'mergen-wsi-attention-mil', 'version': 'ensemble_cv_v1', 'ensemble': True}
PREDICTION_SOURCES = ('ensemble_cv_v1', 'mil_v1')
PREDICTION_COLUMNS = ('patient_id', 'label', 'pred', 'p_A', 'p_O', 'p_G')
# `heatmap_review.py` colours each tile by its raw attention weight. The weights
# sum to one over thousands of tiles, so almost every tile lands at the bottom of
# the scale; the report's figures rank the tiles within the slide instead. The
# package says which rendering it carries so the screen can describe it honestly.
ATTENTION_SCALES = ('raw_weight', 'within_slide_percentile')
FIGURE_MODEL = {'id': 'mergen-uwcse', 'version': 'v3', 'ruleVersion': 'uwcse-v3'}
SLIDE_IMAGES = {'attention': 'attention.jpg', 'top_tiles': 'top_tiles.jpg',
                'thumbnail': 'thumbnail.jpg'}
# The top-tile sheet is a montage, not a picture: `heatmap_review.py` sorts the
# tiles by attention, takes the top k and pastes them row by row into a
# six-column sheet of 224 px tiles read at 0.5 µm/px. The interface may only
# number the cells if the sheet really has that shape, so it is measured here
# and the layout travels with the record.
TILE_PX = 224
TILE_COLUMNS = 6
TILE_MICRONS_PER_PIXEL = 0.5
TILE_ORDERING = 'attention_desc'
ATTENTION_FIELDS = {'top1_share': 'top1Share', 'top10_share': 'top10Share',
                    'entropy_normalised': 'entropyNormalised'}


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path.name}')
    return value


def _text(value, case_id: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'Missing {field}: {case_id}')
    return value


def _tile_grid(sheet_path: Path, case_id: str, tiles_used: int) -> dict:
    """Measure the top-tile sheet; refuse to describe a sheet of another shape."""
    with Image.open(sheet_path) as sheet:
        width, height = sheet.size
    if width % TILE_PX or height % TILE_PX or width // TILE_PX != TILE_COLUMNS or height == 0:
        raise ValueError(f'Top tiles are not a {TILE_COLUMNS}x{TILE_PX} px montage: {case_id}')
    rows = height // TILE_PX
    count = TILE_COLUMNS * rows
    # A cell the slide never filled would be numbered as a tile; refuse that.
    if count > tiles_used:
        raise ValueError(f'Top tile sheet claims more tiles than the slide used: {case_id}')
    return {'tilePx': TILE_PX, 'columns': TILE_COLUMNS, 'rows': rows, 'count': count,
            'ordering': TILE_ORDERING, 'micronsPerPixel': TILE_MICRONS_PER_PIXEL}


def read_slide_predictions(path: Path) -> dict:
    """Per-case probabilities of the product ensemble, keyed by patient id."""
    import csv

    with path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows or tuple(rows[0]) != PREDICTION_COLUMNS:
        raise ValueError(f'Unexpected prediction columns: {path.name}')
    table = {}
    for row in rows:
        patient = row['patient_id']
        if patient in table:
            raise ValueError(f'Repeated patient in predictions: {patient}')
        probabilities = {name: float(row[f'p_{name}']) for name in CLASSES}
        if abs(sum(probabilities.values()) - 1) > 0.01:
            raise ValueError(f'Prediction probabilities do not sum to one: {patient}')
        declared = row['pred']
        if declared not in CLASSES or probabilities[declared] != max(probabilities.values()):
            raise ValueError(f'Declared class is not the highest probability: {patient}')
        table[patient] = {'probabilities': probabilities, 'predicted': declared,
                          'reference': row['label'] or None}
    return table


def read_review_margin(path: Path) -> float:
    """The abstention threshold the registry measured, not a number we picked."""
    calibration = _json(path).get('abstention')
    if not isinstance(calibration, dict):
        raise ValueError(f'Calibration file carries no abstention block: {path.name}')
    if calibration.get('metric') != REVIEW_MARGIN_METRIC:
        raise ValueError(f'Abstention is measured on another quantity: {path.name}')
    margin = calibration.get('chosen_threshold')
    if type(margin) is not float or not 0 < margin <= 1:
        raise ValueError(f'Invalid abstention threshold: {path.name}')
    return margin


def _case_dirs(root: Path) -> list[Path]:
    """Only directories are cases; the export also carries an INDEX.json."""
    return sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name)


def _no_symlinks(root: Path) -> None:
    if root.is_symlink() or any(path.is_symlink() for path in root.rglob('*')):
        raise ValueError(f'Source must not contain symlinks: {root.name}')


def _probabilities(raw, case_id: str) -> dict:
    if (not isinstance(raw, dict) or set(raw) != set(CLASSES)
            or any(type(value) not in (int, float) or not 0 <= value <= 1
                   for value in raw.values())
            or abs(sum(raw.values()) - 1) > 0.01):
        raise ValueError(f'Invalid class probabilities: {case_id}')
    return {name: float(raw[name]) for name in CLASSES}


def _attention(raw, case_id: str) -> dict:
    if (not isinstance(raw, dict) or set(raw) != set(ATTENTION_FIELDS)
            or any(type(raw[field]) not in (int, float) or not 0 <= raw[field] <= 1
                   for field in ATTENTION_FIELDS)):
        raise ValueError(f'Invalid attention concentration: {case_id}')
    return {renamed: float(raw[field]) for field, renamed in ATTENTION_FIELDS.items()}


def _volumes(raw, case_id: str, side: str) -> dict:
    if (not isinstance(raw, dict) or set(raw) != set(REGIONS)
            or any(type(count) is not int or count < 0 for count in raw.values())):
        raise ValueError(f'Invalid {side} volumes: {case_id}')
    return {region: raw[region] for region in REGIONS}


def _scores(raw, case_id: str, name: str, maximum=None):
    """Region score table; a region with nothing to compare against stays null."""
    if raw is None:
        return None
    if (not isinstance(raw, dict) or set(raw) != set(REGIONS)
            or any(value is not None
                   and (type(value) not in (int, float) or value < 0
                        or (maximum is not None and value > maximum))
                   for value in raw.values())):
        raise ValueError(f'Invalid {name} table: {case_id}')
    return {region: raw[region] for region in REGIONS}


def slide_record(case_id: str, info: dict, module: str, disease: str,
                 margin: float, product: dict | None = None) -> dict:
    """One prepared slide case; the export's own claims are recomputed."""
    probabilities = _probabilities(info.get('probabilities'), case_id)
    predicted = info.get('predicted_class')
    reference = info.get('true_class')
    split = _text(info.get('split'), case_id, 'split')
    patient_id = _text(info.get('patient_id'), case_id, 'patient id')
    if predicted not in CLASSES or (reference is not None and reference not in CLASSES):
        raise ValueError(f'Invalid class: {case_id}')
    if probabilities[predicted] != max(probabilities.values()):
        raise ValueError(f'Declared class is not the highest probability: {case_id}')
    if reference is not None and info.get('correct') is not (predicted == reference):
        raise ValueError(f'Source disagrees with its own reference: {case_id}')
    if split not in SPLITS:
        raise ValueError(f'Unknown split: {case_id}')
    if case_id != f'{split}_{patient_id}':
        raise ValueError(f'Case directory and patient do not match: {case_id}')
    tiles = info.get('n_tiles_used')
    if type(tiles) is not int or tiles <= 0:
        raise ValueError(f'Invalid tile count: {case_id}')
    # Up to here the export's own claims about the single network have been
    # recomputed. The product model is the five-fold ensemble, so when its
    # prediction file is given the case is reported with those probabilities and
    # the single network's stay beside them, named.
    single = {'class': predicted, 'probabilities': probabilities}
    source, model = 'mil_v1', SLIDE_MODEL
    if product is not None:
        if product['reference'] not in (None, reference):
            raise ValueError(f'Prediction file disagrees with the case reference: {case_id}')
        probabilities = product['probabilities']
        predicted = product['predicted']
        source, model = 'ensemble_cv_v1', ENSEMBLE_MODEL
    ranked = sorted(probabilities.values(), reverse=True)
    record = {
        'schemaVersion': 4, 'module': module, 'disease': disease,
        'caseId': case_id, 'id': case_id, 'patientId': patient_id,
        'source': 'TCGA', 'sourceSite': _text(info.get('source_site'), case_id, 'source site'),
        'mode': 'demo', 'status': 'demo_ready',
        'modelId': model['id'], 'modelVersion': model['version'],
        'inputKind': 'prepared-wsi-subtyping',
        'split': split, 'whoGrade': _text(info.get('who_grade'), case_id, 'WHO grade'),
        'tilesUsed': tiles,
        'prediction': {'class': predicted, 'probabilities': probabilities},
        'predictionSource': source,
        'needsExpertReview': ranked[0] - ranked[1] < margin,
        # The map comes from the single network whichever model decided the case.
        'attention': {'modelId': SLIDE_MODEL['id'], 'modelVersion': SLIDE_MODEL['version'],
                      'tilesEvaluated': tiles, 'scale': 'raw_weight'},
        'attentionConcentration': _attention(info.get('attention_concentration'), case_id),
    }
    if product is not None:
        record['singleModel'] = single
    if reference is not None:
        record['reference'] = {'class': reference}
        record['agreesWithReference'] = predicted == reference
    return record


def _flags(raw, case_id: str) -> list:
    """Review flags keep the pipeline's reason and numbers, not a bare string."""
    if not isinstance(raw, list):
        raise ValueError(f'Invalid review flags: {case_id}')
    for flag in raw:
        evidence = flag.get('evidence') if isinstance(flag, dict) else None
        if (not isinstance(flag, dict)
                or any(not isinstance(flag.get(field), str) or not flag[field]
                       for field in FLAG_FIELDS)
                or not isinstance(evidence, dict) or not evidence
                or any(not isinstance(key, str) or type(value) not in (int, float)
                       for key, value in evidence.items())):
            raise ValueError(f'Invalid review flags: {case_id}')
    return raw


def figure_record(case_id: str, info: dict, module: str, disease: str) -> dict:
    """One measured MRI figure. A score without a reference volume is refused."""
    if info.get('case_id') != case_id:
        raise ValueError(f'Figure directory and record do not match: {case_id}')
    volumes = {}
    for side, field in (('reference', 'reference_voxels'), ('prediction', 'predicted_voxels')):
        if info.get(field) is not None:
            volumes[side] = _volumes(info[field], case_id, side)
    dice = _scores(info.get('dice'), case_id, 'dice', maximum=1)
    hd95 = _scores(info.get('hd95_mm'), case_id, 'hd95Mm')
    if (dice is not None or hd95 is not None) and 'reference' not in volumes:
        raise ValueError(f'Score without reference volumes: {case_id}')
    flags = _flags(info.get('review_flags'), case_id)
    slice_shown = info.get('slice_shown')
    if type(slice_shown) is not int or slice_shown < 0:
        raise ValueError(f'Invalid slice index: {case_id}')
    record = {
        'id': case_id, 'kind': 'figure', 'caseId': case_id, 'source': 'UCSF-PDGM',
        'split': _text(info.get('split'), case_id, 'split'),
        'ruleVersion': FIGURE_MODEL['ruleVersion'],
        'modelId': FIGURE_MODEL['id'], 'modelVersion': FIGURE_MODEL['version'],
        'modelNote': _text(info.get('model'), case_id, 'model note'),
        'selectionReason': _text(info.get('selection_reason'), case_id, 'selection reason'),
        'whoGrade': _text(info.get('who_grade'), case_id, 'WHO grade'),
        'diagnosis': _text(info.get('diagnosis'), case_id, 'diagnosis'),
        'idh': _text(info.get('idh'), case_id, 'IDH status'),
        'reviewFlags': flags, 'sliceShown': slice_shown,
        'figure': f'/api/demo/modules/{module}/diseases/{disease}/examples/{case_id}/figure',
        'figureLayout': _text((info.get('files') or {}).get('overlay.png'),
                              case_id, 'figure layout'),
    }
    if volumes:
        record['regionVolumes'] = volumes
    if dice is not None:
        record['dice'] = dice
    if hd95 is not None:
        record['hd95Mm'] = hd95
    return record


def _imaging_collection(package: Path) -> tuple[Path, str]:
    """The imaging collection directory of an existing package and its disease."""
    catalog = _json(package / 'catalog.json')
    entries = catalog.get('collections')
    if catalog.get('schemaVersion') != 3 or not isinstance(entries, list):
        raise ValueError('Demo catalog schema version 3 required.')
    entry = next((item for item in entries
                  if isinstance(item, dict) and item.get('module') == 'imaging'), None)
    if (entry is None or not isinstance(entry.get('manifest'), str)
            or not isinstance(entry.get('disease'), str)
            or not COLLECTION_ID.fullmatch(entry['disease'])):
        raise ValueError('Imaging collection is missing.')
    manifest = (package / entry['manifest']).resolve(strict=True)
    if not manifest.is_relative_to(package) or not manifest.is_file():
        raise ValueError('Collection manifest escapes package root.')
    return manifest.parent, entry['disease']


def build(imaging_package: Path, wsi_cases: Path, mri_examples: Path | None,
          output: Path, calibration: Path, slide_predictions: Path | None = None) -> dict:
    imaging_package = imaging_package.resolve(strict=True)
    wsi_cases = wsi_cases.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; choose a new directory.')
    if not output.parent.is_dir():
        raise ValueError('Output parent directory does not exist.')
    _no_symlinks(imaging_package)
    _no_symlinks(wsi_cases)
    source_collection, disease = _imaging_collection(imaging_package)
    if mri_examples is not None:
        mri_examples = mri_examples.resolve(strict=True)
        _no_symlinks(mri_examples)
    predictions = read_slide_predictions(slide_predictions) if slide_predictions else {}
    # Every slide record carries a flag, so every package needs the threshold the
    # flag was measured against; there is no build without it.
    margin = read_review_margin(calibration.resolve(strict=True))

    staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}-', dir=output.parent))
    try:
        imaging = staging / 'imaging' / disease
        shutil.copytree(source_collection, imaging, symlinks=False)
        imaging_manifest = _json(imaging / 'manifest.json')
        imaging_cases = imaging_manifest.get('cases')
        if not isinstance(imaging_cases, list) or not imaging_cases:
            raise ValueError('Imaging manifest requires cases.')

        pathology = staging / 'pathology' / 'glioma'
        (pathology / 'cases').mkdir(parents=True)
        notes, slides = set(), []
        for case_dir in _case_dirs(wsi_cases):
            case_id = case_dir.name
            if not CASE_ID.fullmatch(case_id):
                raise ValueError(f'Invalid case directory: {case_id}')
            info = _json(case_dir / 'case_info.json')
            patient = info.get('patient_id')
            product = predictions.get(patient) if isinstance(patient, str) else None
            record = slide_record(case_id, info, 'pathology', 'glioma', margin, product)
            notes.add(_text(info.get('model'), case_id, 'model note'))
            target = pathology / 'cases' / case_id
            target.mkdir()
            prefix = f'/api/demo/modules/pathology/diseases/glioma/cases/{case_id}'
            assets = {}
            for kind, name in SLIDE_IMAGES.items():
                source_file = case_dir / name
                if not source_file.is_file():
                    if kind == 'thumbnail':
                        continue
                    raise ValueError(f'Missing {name}: {case_id}')
                shutil.copy2(source_file, target / name)
                assets[kind] = f'{prefix}/images/{kind}'
            assets['report'] = f'{prefix}/report'
            record['assets'] = assets
            record['tileGrid'] = _tile_grid(target / SLIDE_IMAGES['top_tiles'], case_id,
                                            record['tilesUsed'])
            (target / 'report.json').write_text(json.dumps(
                {'schemaVersion': 4, 'case': record, 'sourceCaseInfo': info},
                indent=2, ensure_ascii=False), encoding='utf-8')
            slides.append(record)
        if not slides:
            raise ValueError('No slide cases found.')
        if len(notes) != 1:
            raise ValueError('Slide cases come from different models; label them separately.')

        examples = []
        for case_dir in _case_dirs(mri_examples) if mri_examples is not None else []:
            case_id = case_dir.name
            if not CASE_ID.fullmatch(case_id):
                raise ValueError(f'Invalid figure directory: {case_id}')
            record = figure_record(case_id, _json(case_dir / 'case_info.json'),
                                   'imaging', disease)
            target = imaging / 'examples' / case_id
            target.mkdir(parents=True)
            shutil.copy2(case_dir / 'overlay.png', target / 'figure.png')
            examples.append(record)

        # A slide and an MRI record must never read as the same patient.
        shared = ({case['id'] for case in imaging_cases} | {item['id'] for item in examples}) & (
            {item['id'] for item in slides} | {item['patientId'] for item in slides})
        if shared:
            raise ValueError(f'A slide and an MRI record share an identifier: {sorted(shared)}')

        imaging_manifest['schemaVersion'] = 4
        for case in imaging_cases:
            case['schemaVersion'] = 4
        if examples:
            imaging_manifest['examples'] = examples
        (imaging / 'manifest.json').write_text(
            json.dumps(imaging_manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        (pathology / 'manifest.json').write_text(json.dumps({
            'schemaVersion': 4, 'module': 'pathology', 'disease': 'glioma',
            'reviewMargin': margin, 'classes': list(CLASSES),
            'model': ENSEMBLE_MODEL if predictions else SLIDE_MODEL,
            # The attention map can only come from a single network; naming it
            # here keeps the map and the decision from reading as one model. The
            # export's note describes that network, so it belongs to it and not
            # to the ensemble that decided the case.
            'attentionModel': {**SLIDE_MODEL, 'note': notes.pop()},
            'cases': slides,
        }, indent=2, ensure_ascii=False), encoding='utf-8')
        (staging / 'catalog.json').write_text(json.dumps({
            'schemaVersion': 3,
            'collections': [
                {'module': 'imaging', 'disease': disease,
                 'manifest': f'imaging/{disease}/manifest.json'},
                {'module': 'pathology', 'disease': 'glioma',
                 'manifest': 'pathology/glioma/manifest.json'},
            ],
        }, indent=2), encoding='utf-8')
        staging.replace(output)
        return {
            'imagingCases': len(imaging_cases),
            'examples': len(examples),
            'slideCases': len(slides),
            'slidesNeedingReview': sum(item['needsExpertReview'] for item in slides),
            'slidesAgainstReference': sum(item.get('agreesWithReference') is False
                                          for item in slides),
            'slideSites': len({item['sourceSite'] for item in slides}),
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imaging-package', type=Path, required=True,
                        help='existing demo package whose imaging collection is copied')
    parser.add_argument('--wsi-cases', type=Path, required=True,
                        help='evidence export directory holding one folder per slide case')
    parser.add_argument('--mri-examples', type=Path,
                        help='evidence export directory holding the measured MRI figures')
    parser.add_argument('--slide-predictions', type=Path,
                        help='product ensemble predictions CSV from the model registry')
    parser.add_argument('--calibration', type=Path, required=True,
                        help='calibration.json the abstention threshold was read out in')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = build(args.imaging_package, args.wsi_cases, args.mri_examples, args.output,
                    args.calibration, args.slide_predictions)
    print(f"Prepared {summary['slideCases']} slide cases "
          f"({summary['slidesAgainstReference']} against the reference, "
          f"{summary['slidesNeedingReview']} for expert review, "
          f"{summary['slideSites']} sites), {summary['examples']} MRI figures and "
          f"{summary['imagingCases']} copied imaging cases; no inference executed.")
