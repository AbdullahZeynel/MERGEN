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
  previews: [
    { axis: 'axial', index: 77, src: `/demo/${id}/axial.png` },
    { axis: 'coronal', index: 120, src: `/demo/${id}/coronal.png` },
    { axis: 'sagittal', index: 120, src: `/demo/${id}/sagittal.png` },
  ],
});
