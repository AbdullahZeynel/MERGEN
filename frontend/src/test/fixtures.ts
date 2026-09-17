import type { CaseRecord, FigureRecord, ReviewFlag, SlideRecord } from '../data/contracts';

// Contract-only fixtures; no patient results or fabricated medical scores.
export const makeCase = (id: string): CaseRecord => ({
  id,
  source: 'UCSF-PDGM',
  mode: 'demo',
  status: 'demo_ready',
  shape: [240, 240, 155],
  modality: 'FLAIR',
  overlays: ['prediction', 'ground_truth'],
  previews: [
    { axis: 'axial', index: 77, src: `/api/demo/cases/${id}/slices/axial/77` },
    { axis: 'coronal', index: 120, src: `/api/demo/cases/${id}/slices/coronal/120` },
    { axis: 'sagittal', index: 120, src: `/api/demo/cases/${id}/slices/sagittal/120` },
  ],
});

// Asagidaki sayilar sozlesme fixture'i: olcum degil, semanin sinandigi
// uydurma degerler. Gercek sayilar model kayit defterinden gelir.
const slideBase = (id: string) => `/api/demo/modules/pathology/diseases/glioma/cases/${id}`;

export const makeSlide = (id: string, patch: Partial<SlideRecord> = {}): SlideRecord => ({
  id,
  patientId: id,
  source: 'TCGA',
  sourceSite: 'Test Site',
  mode: 'demo',
  status: 'demo_ready',
  split: 'test',
  whoGrade: 'G4',
  tilesUsed: 4096,
  modelId: 'mergen-wsi-attention-mil',
  modelVersion: 'ensemble_cv_v1',
  prediction: { class: 'G', probabilities: { A: 0.05, O: 0.05, G: 0.9 } },
  predictionSource: 'ensemble_cv_v1',
  attention: {
    modelId: 'mergen-wsi-attention-mil',
    modelVersion: 'mil_v1',
    tilesEvaluated: 4096,
    scale: 'raw_weight',
  },
  reference: { class: 'G' },
  agreesWithReference: true,
  needsExpertReview: false,
  attentionConcentration: { top1Share: 0.04, top10Share: 0.24, entropyNormalised: 0.65 },
  tileGrid: {
    tilePx: 224,
    columns: 6,
    rows: 2,
    count: 12,
    ordering: 'attention_desc',
    micronsPerPixel: 0.5,
  },
  assets: {
    attention: `${slideBase(id)}/images/attention`,
    top_tiles: `${slideBase(id)}/images/top_tiles`,
    report: `${slideBase(id)}/report`,
  },
  ...patch,
});

export const slideModel = {
  id: 'mergen-wsi-attention-mil',
  version: 'ensemble_cv_v1',
  ensemble: true,
};

export const makeSlideManifest = (cases: SlideRecord[]) => ({
  schemaVersion: 4,
  module: 'pathology',
  disease: 'glioma',
  reviewMargin: 0.45,
  model: slideModel,
  attentionModel: {
    id: 'mergen-wsi-attention-mil',
    version: 'mil_v1',
    ensemble: false,
    note: 'Tek ağ; haritayı bu ağ çizer.',
  },
  cases,
});

export const makeFlag = (patch: Partial<ReviewFlag> = {}): ReviewFlag => ({
  finding: 'tumor_core',
  severity: 'low_confidence',
  reason: 'non_enhancing_tumor',
  message: 'Paketin kendi metni.',
  evidence: { tumor_core_voxels: 812, enhancing_voxels: 12, enhancing_threshold: 250 },
  ...patch,
});

export const makeFigure = (id: string, patch: Partial<FigureRecord> = {}): FigureRecord => ({
  id,
  kind: 'figure',
  caseId: id,
  source: 'UCSF-PDGM',
  split: 'locked test',
  ruleVersion: 'uwcse-v3',
  modelId: 'mergen-uwcse',
  modelVersion: 'v3',
  selectionReason: 'typical',
  whoGrade: '4',
  diagnosis: 'Glioblastoma, IDH-wildtype',
  idh: 'wildtype',
  regionVolumes: {
    reference: { TC: 1000, WT: 4000, ET: 900 },
    prediction: { TC: 1100, WT: 3900, ET: 950 },
  },
  dice: { TC: 0.91, WT: 0.93, ET: null },
  hd95Mm: { TC: 2.5, WT: 3.5, ET: null },
  reviewFlags: [],
  sliceShown: 100,
  figure: `/api/demo/modules/imaging/diseases/glioma/examples/${id}/figure`,
  figureLayout: 'FLAIR, T1c, reference and prediction side by side',
  ...patch,
});
