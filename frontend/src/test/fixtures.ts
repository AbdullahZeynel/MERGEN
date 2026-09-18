import type {
  DemoCase,
  LiveJob,
  LiveReport,
  LiveResult,
  ReviewFlag,
} from '../data/contracts';

// Contract-only fixtures; no patient results or fabricated medical scores.
export const makeCase = (id: string): DemoCase => ({
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

// Canli is fixture'i: sozlesme icindir, hasta sonucu ya da uydurma skor tasimaz.
const LIVE_JOB_ID = 'a'.repeat(32);
const DIGEST = '0'.repeat(64);

export const makeLiveResult = (jobId: string = LIVE_JOB_ID): LiveResult => ({
  schemaVersion: 1,
  jobId,
  module: 'imaging',
  disease: 'glioma',
  modelId: 'mergen-uwcse',
  modelVersion: 'v3',
  hasPrediction: true,
  hasGroundTruth: false,
  assets: [
    { path: 'report.json', kind: 'report-json', sha256: DIGEST, size: 512 },
    { path: 'prediction.nii.gz', kind: 'prediction-nifti', sha256: DIGEST, size: 131072 },
    { path: 'prediction.glb', kind: 'prediction-glb', sha256: DIGEST, size: 262144 },
  ],
});

export const makeLiveJob = (jobId: string = LIVE_JOB_ID): LiveJob => {
  const result = makeLiveResult(jobId);
  return {
    jobId,
    module: 'imaging',
    disease: 'glioma',
    status: 'completed',
    createdAt: 1_758_000_000,
    updatedAt: 1_758_000_120,
    result,
    downloadUrl: `/api/live/jobs/${jobId}/download`,
    assetUrls: Object.fromEntries(
      result.assets.map((asset) => [asset.path, `/api/live/jobs/${jobId}/assets/${asset.path}`]),
    ),
  };
};

export const makeLiveReport = (): LiveReport => ({
  schemaVersion: 2,
  status: 'research-output',
  modelId: 'mergen-uwcse',
  modelVersion: 'v3',
  rule: { id: 'uwcse', version: 'v3', tcMin: 250, etMin: 100, minComponentVoxels: 50 },
  regionVolumes: { TC: 12_400, WT: 48_900, ET: 5_100 },
  reviewFlags: [],
  notice: 'Research prototype; not for clinical use.',
});

export const makeReviewFlag = (): ReviewFlag => ({
  finding: 'tumor_core',
  severity: 'low_confidence',
  reason: 'non_enhancing_tumor',
  message: 'Sunucudan gelen tek dilli metin.',
  evidence: { tumor_core_voxels: 900, enhancing_voxels: 120, enhancing_threshold: 500 },
});
