import { z } from 'zod';

/**
 * Hazır demo genomik koleksiyonu.
 *
 * Bu kayıtlar görüntü vakalarından bağımsız, kamuya açık referans
 * varyantlardır; aynı hastaya ait değildir ve öyle gösterilmemelidir.
 */
export const GENOMICS_MODULE = 'genomics';
export const GENOMICS_DISEASE = 'glioma-variant-pathogenicity';

const collectionBase = `/api/demo/modules/${GENOMICS_MODULE}/diseases/${GENOMICS_DISEASE}/cases`;

const caseId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/);
const gene = z.string().regex(/^[A-Z0-9-]{2,32}$/);
const proteinChange = z.string().regex(/^p\.[A-Z][0-9]+[A-Z]$/);

export const genomicsCaseSchema = z.object({
  schemaVersion: z.literal(3),
  module: z.literal(GENOMICS_MODULE),
  disease: z.literal(GENOMICS_DISEASE),
  id: caseId,
  caseId,
  source: z.string().min(1),
  mode: z.literal('demo'),
  status: z.literal('demo_ready'),
  modelId: z.string().min(1),
  modelVersion: z.string().min(1),
  inputKind: z.literal('variant'),
  hasPrediction: z.literal(true),
  hasGroundTruth: z.literal(false),
  gene,
  proteinChange,
  reports: z.array(z.enum(['result', 'explanation', 'input'])).min(1),
});
export type GenomicsCase = z.infer<typeof genomicsCaseSchema>;

export const genomicsManifestSchema = z
  .object({
    schemaVersion: z.literal(3),
    module: z.literal(GENOMICS_MODULE),
    disease: z.literal(GENOMICS_DISEASE),
    decisionThreshold: z.number().gt(0).lt(1),
    note: z.string().min(1).optional(),
    cases: z.array(genomicsCaseSchema).min(1),
  })
  .superRefine((manifest, ctx) => {
    if (new Set(manifest.cases.map((c) => c.id)).size !== manifest.cases.length)
      ctx.addIssue({ code: 'custom', message: 'Tekrarlanan vaka kimliği.' });
    for (const item of manifest.cases)
      if (item.id !== item.caseId)
        ctx.addIssue({ code: 'custom', message: 'Vaka kimliği tutarsız.' });
  });

export const genomicsResultSchema = z.object({
  schemaVersion: z.literal(1),
  module: z.literal(GENOMICS_MODULE),
  disease: z.literal(GENOMICS_DISEASE),
  mode: z.literal('demo'),
  modelId: z.string().min(1),
  modelVersion: z.string().min(1),
  hasPrediction: z.literal(true),
  hasGroundTruth: z.literal(false),
  variant: z.object({ gene, proteinChange }),
  prediction: z.object({
    pathogenicityProbability: z.number().min(0).max(1),
    class: z.enum(['pathogenic', 'benign']),
    decisionThreshold: z.number().gt(0).lt(1),
  }),
  features: z.record(z.string(), z.number()),
  featureOrder: z.array(z.string()).min(1),
  notes: z.array(z.string()),
});
export type GenomicsResult = z.infer<typeof genomicsResultSchema>;

/** SHAP katkıları ham margin (log-odds) uzayındadır; olasılık değildir. */
export const genomicsExplanationSchema = z
  .object({
    method: z.string().min(1),
    space: z.literal('margin'),
    link: z.literal('logit'),
    baseValue: z.number(),
    rawMargin: z.number(),
    additivityError: z.number().nonnegative(),
    additivityTolerance: z.number().positive(),
    contributions: z.record(z.string(), z.number()),
    topFeatures: z
      .array(z.object({ feature: z.string().min(1), contribution: z.number() }))
      .min(1),
  })
  .superRefine((item, ctx) => {
    const total =
      item.baseValue + Object.values(item.contributions).reduce((a, b) => a + b, 0);
    if (Math.abs(total - item.rawMargin) > Math.max(item.additivityTolerance, 1e-4))
      ctx.addIssue({ code: 'custom', message: 'SHAP toplamsallığı sağlanmıyor.' });
  });
export type GenomicsExplanation = z.infer<typeof genomicsExplanationSchema>;

async function okuJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal, cache: 'no-cache' });
  if (!response.ok) throw new Error('Genomik demo servisine ulaşılamadı.');
  return response.json();
}

export async function listGenomicsCases(signal?: AbortSignal): Promise<GenomicsCase[]> {
  const parsed = genomicsManifestSchema.safeParse(await okuJson(collectionBase, signal));
  if (!parsed.success) throw new Error('Genomik demo paketi beklenen biçimde değil.');
  return parsed.data.cases;
}

export async function loadGenomicsReport(
  id: string,
  signal?: AbortSignal,
): Promise<{ result: GenomicsResult; explanation: GenomicsExplanation }> {
  const [rawResult, rawExplanation] = await Promise.all([
    okuJson(`${collectionBase}/${encodeURIComponent(id)}/report/result`, signal),
    okuJson(`${collectionBase}/${encodeURIComponent(id)}/report/explanation`, signal),
  ]);
  const result = genomicsResultSchema.safeParse(rawResult);
  const explanation = genomicsExplanationSchema.safeParse(rawExplanation);
  if (!result.success || !explanation.success)
    throw new Error('Genomik sonuç beklenen biçimde değil.');
  return { result: result.data, explanation: explanation.data };
}
