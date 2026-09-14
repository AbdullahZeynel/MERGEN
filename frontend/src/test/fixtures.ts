import type { CaseRecord } from '../data/contracts';

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
