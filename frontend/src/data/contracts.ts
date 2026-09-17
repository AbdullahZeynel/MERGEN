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
export const modules = ['imaging', 'pathology'] as const;
export type Module = (typeof modules)[number];
export const moduleKeys: Record<Module, MessageKey> = {
  imaging: 'modules.imaging',
  pathology: 'modules.pathology',
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
// ── Olculmus dogrulama figurleri ve inceleme bayraklari ──────────────────
// Bayrak dizge degil: `review_flags()` bulguyu, gerekcesini ve sayilarini
// birlikte verir; ekran gerekceyi kendi dilinde yazip sayilari buradan okur.
export const reviewFlagSchema = z.object({
  finding: z.string().min(1),
  severity: z.string().min(1),
  reason: z.string().min(1),
  message: z.string().min(1),
  evidence: z.record(z.string(), z.number()).refine((value) => Object.keys(value).length > 0, {
    message: 'Bayrak sayısız olamaz.',
  }),
});
export type ReviewFlag = z.infer<typeof reviewFlagSchema>;
export const regions = ['TC', 'WT', 'ET'] as const;
export type Region = (typeof regions)[number];
export const regionKeys: Record<Region, MessageKey> = {
  TC: 'region.TC',
  WT: 'region.WT',
  ET: 'region.ET',
};

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
    reviewFlags: z.array(reviewFlagSchema).optional(),
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

// ── Patoloji koleksiyonu (demo paketi v4) ────────────────────────────────
// Manifest kendi iddiasini tasiyor; burada yeniden turetiliyor. Ekran, sayilariyla
// celisen bir rozet cizmekten once kaydi reddeder.
export const pathologyClasses = ['A', 'O', 'G'] as const;
export type PathologyClass = (typeof pathologyClasses)[number];
export const pathologyClassKeys: Record<PathologyClass, MessageKey> = {
  A: 'pathology.classA',
  O: 'pathology.classO',
  G: 'pathology.classG',
};
const share = z.number().min(0).max(1);
const slideBase = (id: string) => `/api/demo/modules/pathology/diseases/glioma/cases/${id}/`;
export const slideSchema = z
  .object({
    id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]*$/),
    patientId: z.string().min(1),
    source: z.literal('TCGA'),
    sourceSite: z.string().min(1),
    mode: z.literal('demo'),
    status: z.literal('demo_ready'),
    split: z.string().min(1),
    whoGrade: z.string().min(1),
    tilesUsed: z.number().int().positive(),
    prediction: z.object({
      class: z.enum(pathologyClasses),
      probabilities: z.object({ A: share, O: share, G: share }),
    }),
    reference: z.object({ class: z.enum(pathologyClasses) }).optional(),
    agreesWithReference: z.boolean().optional(),
    needsExpertReview: z.boolean(),
    attentionConcentration: z.object({
      top1Share: share,
      top10Share: share,
      entropyNormalised: share,
    }),
    assets: z.object({
      attention: z.string(),
      top_tiles: z.string(),
      thumbnail: z.string().optional(),
      report: z.string().optional(),
    }),
  })
  .superRefine((slide, ctx) => {
    for (const [kind, path] of Object.entries(slide.assets))
      if (!path.startsWith(slideBase(slide.id)))
        ctx.addIssue({ code: 'custom', message: `Varlık başka bir vakaya ait: ${kind}` });
    const ranked = Object.values(slide.prediction.probabilities).sort((a, b) => b - a);
    if (slide.prediction.probabilities[slide.prediction.class] !== ranked[0])
      ctx.addIssue({ code: 'custom', message: 'Bildirilen sınıf en yüksek olasılık değil.' });
    const agrees = slide.reference && slide.prediction.class === slide.reference.class;
    if (slide.reference ? slide.agreesWithReference !== agrees : 'agreesWithReference' in slide)
      ctx.addIssue({ code: 'custom', message: 'Uyum iddiası referansla tutmuyor.' });
  });
export const slideManifestSchema = z
  .object({
    schemaVersion: z.literal(4),
    module: z.literal('pathology'),
    disease: z.literal('glioma'),
    reviewMargin: z.number().gt(0).max(1),
    model: z.object({
      id: z.string().min(1),
      version: z.string().min(1),
      ensemble: z.boolean(),
      note: z.string().min(1),
    }),
    cases: z.array(slideSchema),
  })
  .superRefine((manifest, ctx) => {
    if (new Set(manifest.cases.map((slide) => slide.id)).size !== manifest.cases.length)
      ctx.addIssue({ code: 'custom', message: 'Tekrarlanan vaka kimliği.' });
    for (const slide of manifest.cases) {
      const [first, second] = Object.values(slide.prediction.probabilities).sort((a, b) => b - a);
      if (slide.needsExpertReview !== first - second < manifest.reviewMargin)
        ctx.addIssue({ code: 'custom', message: 'Çekimserlik bayrağı eşikle tutmuyor.' });
    }
  });
export type SlideRecord = z.infer<typeof slideSchema>;
export type SlideManifest = z.infer<typeof slideManifestSchema>;

// ── Olculmus dogrulama figurleri ──────────────────────────────────────────
const volumeTable = z.object({
  TC: z.number().int().nonnegative(),
  WT: z.number().int().nonnegative(),
  ET: z.number().int().nonnegative(),
});
const scoreTable = z.object({
  TC: z.number().nonnegative().nullable(),
  WT: z.number().nonnegative().nullable(),
  ET: z.number().nonnegative().nullable(),
});
export const figureSchema = z
  .object({
    id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]*$/),
    kind: z.literal('figure'),
    caseId: z.string().min(1),
    source: z.string().min(1),
    split: z.string().min(1),
    ruleVersion: z.string().min(1),
    modelId: z.string().min(1),
    modelVersion: z.string().min(1),
    selectionReason: z.string().min(1),
    whoGrade: z.string().min(1),
    diagnosis: z.string().min(1),
    idh: z.string().min(1),
    regionVolumes: z
      .object({ reference: volumeTable.optional(), prediction: volumeTable.optional() })
      .optional(),
    dice: scoreTable.optional(),
    hd95Mm: scoreTable.optional(),
    reviewFlags: z.array(reviewFlagSchema),
    sliceShown: z.number().int().nonnegative(),
    figure: z.string(),
    figureLayout: z.string().min(1),
  })
  .superRefine((figure, ctx) => {
    // Referanssiz skor gosterilmez: AGENTS.md 6. madde.
    if ((figure.dice || figure.hd95Mm) && !figure.regionVolumes?.reference)
      ctx.addIssue({ code: 'custom', message: 'Referans hacmi olmadan skor gösterilemez.' });
    if (figure.figure !== `/api/demo/modules/imaging/diseases/glioma/examples/${figure.id}/figure`)
      ctx.addIssue({ code: 'custom', message: 'Figür yolu kendi kaydına ait değil.' });
  });
export type FigureRecord = z.infer<typeof figureSchema>;
export const validationSchema = z.object({
  schemaVersion: z.union([z.literal(3), z.literal(4)]),
  examples: z.array(figureSchema).default([]),
});
