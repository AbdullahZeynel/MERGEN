import { z } from 'zod';
import type { MessageKey } from '../i18n/messages';

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
export const statusKeys: Record<CaseStatus, MessageKey> = {
  demo_ready: 'status.demo_ready',
  draft: 'status.draft',
  queued: 'status.queued',
  processing: 'status.processing',
  completed: 'status.completed',
  failed: 'status.failed',
};
export const axes = ['axial', 'coronal', 'sagittal'] as const;
export type Axis = (typeof axes)[number];
export const axisKeys: Record<Axis, MessageKey> = {
  axial: 'axis.axial',
  coronal: 'axis.coronal',
  sagittal: 'axis.sagittal',
};
const assetPath = z
  .string()
  .regex(/^\/api\/demo\/cases\/[A-Za-z0-9_-]+\/slices\/(axial|coronal|sagittal)\/\d+$/);
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
    overlays: z.array(z.enum(['prediction', 'ground_truth'])).optional(),
    brainContext: z.literal('mr-foreground-envelope').optional(),
    mesh: z
      .string()
      .regex(/^\/api\/demo\/cases\/[A-Za-z0-9_-]+\/mesh(?:\/[0-9a-f]{64}\.glb)?$/)
      .optional(),
  })
  .superRefine((item, ctx) => {
    if (item.mesh && !item.mesh.startsWith(`/api/demo/cases/${item.id}/mesh`))
      ctx.addIssue({ code: 'custom', message: 'Vaka ve mesh uyuşmuyor.' });
    if (new Set(item.previews.map((p) => p.axis)).size !== 3)
      ctx.addIssue({ code: 'custom', message: 'Üç farklı eksen gerekli.' });
    for (const p of item.previews) {
      const dimension = { axial: 2, coronal: 1, sagittal: 0 }[p.axis];
      if (p.index >= item.shape[dimension])
        ctx.addIssue({ code: 'custom', message: 'Kesit boyut dışında.' });
      if (p.src !== `/api/demo/cases/${item.id}/slices/${p.axis}/${p.index}`)
        ctx.addIssue({ code: 'custom', message: 'Vaka ve görüntü uyuşmuyor.' });
    }
  });
export const manifestSchema = z
  .object({ version: z.literal(2), cases: z.array(caseSchema) })
  .superRefine((manifest, ctx) => {
    if (new Set(manifest.cases.map((c) => c.id)).size !== manifest.cases.length)
      ctx.addIssue({ code: 'custom', message: 'Tekrarlanan vaka kimliği.' });
  });
export type CaseRecord = z.infer<typeof caseSchema>;
export interface DataSource {
  listCases(signal?: AbortSignal): Promise<CaseRecord[]>;
}
