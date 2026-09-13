import type { CaseRecord } from '../data/contracts';

// Contract-only fixtures; no patient results or fabricated medical scores.
export const makeCase = (id: string): CaseRecord => ({
  id,
  source: 'UCSF-PDGM',
  mode: 'demo',
  status: 'demo_ready',
  shape: [240, 240, 155],
  modality: 'FLAIR',
  genomics: null,
  overlays: ['prediction', 'ground_truth'],
  previews: [
    { axis: 'axial', index: 77, src: `/api/demo/cases/${id}/slices/axial/77` },
    { axis: 'coronal', index: 120, src: `/api/demo/cases/${id}/slices/coronal/120` },
    { axis: 'sagittal', index: 120, src: `/api/demo/cases/${id}/slices/sagittal/120` },
  ],
});

import type {
  GenomicsCase,
  GenomicsExplanation,
  GenomicsResult,
} from '../data/genomics';

// Sözleşme testleri için; gerçek demo paketindeki IDH1 kaydının biçimini izler.
export const makeGenomicsCase = (
  id = 'IDH1-R132H',
  gene = 'IDH1',
  proteinChange = 'p.R132H',
): GenomicsCase => ({
  schemaVersion: 3,
  module: 'genomics',
  disease: 'glioma-variant-pathogenicity',
  id,
  caseId: id,
  source: 'UniProtKB',
  mode: 'demo',
  status: 'demo_ready',
  modelId: 'mergen-glioma-variant-xgb',
  modelVersion: 'v1',
  inputKind: 'variant',
  hasPrediction: true,
  hasGroundTruth: false,
  gene,
  proteinChange,
  reports: ['result', 'explanation', 'input'],
});

export const makeGenomicsResult = (): GenomicsResult => ({
  schemaVersion: 1,
  module: 'genomics',
  disease: 'glioma-variant-pathogenicity',
  mode: 'demo',
  modelId: 'mergen-glioma-variant-xgb',
  modelVersion: 'v1',
  hasPrediction: true,
  hasGroundTruth: false,
  variant: { gene: 'IDH1', proteinChange: 'p.R132H' },
  prediction: {
    pathogenicityProbability: 0.999686,
    class: 'pathogenic',
    decisionThreshold: 0.5,
  },
  features: { esm_llr: -0.204378366, cgga_missense_frekans: 0.465034965 },
  featureOrder: ['esm_llr', 'cgga_missense_frekans'],
  notes: ['cosmic_frekans_log eğitimde sabit 0.0 idi.'],
});

export const makeGenomicsExplanation = (): GenomicsExplanation => ({
  method: 'TreeSHAP (xgboost pred_contribs)',
  space: 'margin',
  link: 'logit',
  baseValue: 1,
  rawMargin: 3.5,
  additivityError: 0,
  additivityTolerance: 0.0001,
  contributions: { cgga_missense_frekans: 2, esm_llr: 0.5 },
  topFeatures: [
    { feature: 'cgga_missense_frekans', contribution: 2 },
    { feature: 'esm_llr', contribution: 0.5 },
  ],
});
