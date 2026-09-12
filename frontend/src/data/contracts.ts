import { z } from 'zod';

export const caseStatus = z.enum([
  'demo_ready',
  'draft',
  'queued',
  'processing',
  'completed',
  'failed',
]);
export type CaseStatus = z.infer<typeof caseStatus>;
export type SourceMode = 'demo' | 'live';
export const statusLabels: Record<CaseStatus, string> = {
  demo_ready: 'Hazır demo',
  draft: 'Girdi bekliyor',
  queued: 'Kuyrukta',
  processing: 'İşleniyor',
  completed: 'Tamamlandı',
  failed: 'Başarısız',
};
export const axes = ['axial', 'coronal', 'sagittal'] as const;
export type Axis = (typeof axes)[number];
export const axisLabels: Record<Axis, string> = {
  axial: 'Aksiyel',
  coronal: 'Koronal',
  sagittal: 'Sagittal',
};
const assetPath = z.string().regex(/^\/demo\/[A-Za-z0-9_/-]+\.png$/);
const preview = z.object({
  axis: z.enum(axes),
  index: z.number().int().nonnegative(),
  src: assetPath,
});
export const caseSchema = z
  .object({
    id: z.string().regex(/^[A-Za-z0-9_-]+$/),
    source: z.literal('UCSF-PDGM'),
    mode: z.literal('demo'),
    status: z.literal('demo_ready'),
    shape: z.tuple([
      z.number().int().positive(),
      z.number().int().positive(),
      z.number().int().positive(),
    ]),
    modality: z.literal('FLAIR'),
    previews: z.array(preview).length(3),
    genomics: z.literal(null),
  })
  .superRefine((item, ctx) => {
    if (new Set(item.previews.map((p) => p.axis)).size !== 3)
      ctx.addIssue({ code: 'custom', message: 'Üç farklı eksen gerekli.' });
    for (const p of item.previews) {
      const dimension = { axial: 2, coronal: 1, sagittal: 0 }[p.axis];
      if (p.index >= item.shape[dimension])
        ctx.addIssue({ code: 'custom', message: 'Kesit boyut dışında.' });
      if (!p.src.startsWith(`/demo/${item.id}/`))
        ctx.addIssue({ code: 'custom', message: 'Vaka ve görüntü uyuşmuyor.' });
    }
  });
export const manifestSchema = z
  .object({ version: z.literal(1), cases: z.array(caseSchema) })
  .superRefine((manifest, ctx) => {
    if (new Set(manifest.cases.map((c) => c.id)).size !== manifest.cases.length)
      ctx.addIssue({ code: 'custom', message: 'Tekrarlanan vaka kimliği.' });
  });
export type CaseRecord = z.infer<typeof caseSchema>;
export interface DataSource {
  listCases(signal?: AbortSignal): Promise<CaseRecord[]>;
}
