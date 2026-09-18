import { z } from 'zod';
import type { MessageKey } from '../i18n/messages';
// --- Canli is siniri ---------------------------------------------------------
// Demo siniriyla ayni katilik, canli yol icin. Iki kural burada zorlanir:
// govdedeki her yol isin kendi kimligine baglanir (bir is baska bir isin
// varligina isaret edemez) ve referans etiketi hicbir kosulda kabul edilmez —
// canli vakada ground truth yoktur, `true` gelirse sinir reddeder.

export const liveJobStatus = z.enum([
  'queued',
  'claimed',
  'running',
  'completed',
  'failed',
  'cancelled',
]);
export type LiveJobStatus = z.infer<typeof liveJobStatus>;
export const liveStatusKeys: Record<LiveJobStatus, MessageKey> = {
  queued: 'status.queued',
  claimed: 'status.claimed',
  running: 'status.running',
  completed: 'status.completed',
  failed: 'status.failed',
  cancelled: 'status.cancelled',
};

const jobId = z.string().regex(/^[a-f0-9]{32}$/);
const slug = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
// backend/live_contracts.py icindeki ResultAsset ile ayni: SafePath ve kind.
const resultAsset = z.object({
  path: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._/-]*$/),
  kind: z.enum(['report-json', 'report-pdf', 'prediction-nifti', 'prediction-glb', 'slice', 'overlay']),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  size: z.number().int().nonnegative(),
});
const requiredKinds = ['report-json', 'prediction-nifti', 'prediction-glb'] as const;

export const liveResultSchema = z
  .object({
    schemaVersion: z.literal(1),
    jobId,
    module: z.literal('imaging'),
    disease: z.literal('glioma'),
    modelId: slug,
    modelVersion: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/),
    hasPrediction: z.literal(true),
    hasGroundTruth: z.literal(false),
    assets: z.array(resultAsset).min(1).max(64),
  })
  .superRefine((result, ctx) => {
    const paths = result.assets.map((asset) => asset.path);
    if (new Set(paths).size !== paths.length)
      ctx.addIssue({ code: 'custom', message: 'Tekrarlanan sonuç varlığı.' });
    const kinds = new Set(result.assets.map((asset) => asset.kind));
    for (const kind of requiredKinds)
      if (!kinds.has(kind))
        ctx.addIssue({ code: 'custom', message: 'Zorunlu sonuç varlığı eksik.' });
  });
export type LiveResult = z.infer<typeof liveResultSchema>;

export const liveJobSchema = z
  .object({
    jobId,
    module: z.literal('imaging'),
    disease: z.literal('glioma'),
    status: liveJobStatus,
    createdAt: z.number().int().nonnegative(),
    updatedAt: z.number().int().nonnegative(),
    result: liveResultSchema.optional(),
    downloadUrl: z.string().optional(),
    assetUrls: z.record(z.string(), z.string()).optional(),
    errorCode: slug.optional(),
  })
  .superRefine((job, ctx) => {
    const finished = job.status === 'completed';
    const carriesResult = job.result !== undefined;
    // Yarim bir "tamamlandi" ya da tamamlanmadan gelen sonuc, arayuzde bitmis
    // bir is gibi okunur. Ikisi birlikte gelir ya da hic gelmez.
    if (finished !== carriesResult)
      ctx.addIssue({ code: 'custom', message: 'Sonuç yalnız tamamlanan işle gelir.' });
    if (job.errorCode !== undefined && job.status !== 'failed')
      ctx.addIssue({ code: 'custom', message: 'Hata kodu yalnız başarısız işte bulunur.' });
    if (!job.result) {
      if (job.downloadUrl !== undefined || job.assetUrls !== undefined)
        ctx.addIssue({ code: 'custom', message: 'Tamamlanmayan işin indirme bağlantısı olmaz.' });
      return;
    }
    if (job.result.jobId !== job.jobId)
      ctx.addIssue({ code: 'custom', message: 'İş ve sonuç kimliği uyuşmuyor.' });
    if (job.result.module !== job.module || job.result.disease !== job.disease)
      ctx.addIssue({ code: 'custom', message: 'İş ve sonuç profili uyuşmuyor.' });
    if (job.downloadUrl !== `/api/live/jobs/${job.jobId}/download`)
      ctx.addIssue({ code: 'custom', message: 'İndirme bağlantısı işe ait değil.' });
    const expected = new Map(
      job.result.assets.map((asset) => [
        asset.path,
        `/api/live/jobs/${job.jobId}/assets/${asset.path}`,
      ]),
    );
    const given = Object.entries(job.assetUrls ?? {});
    if (given.length !== expected.size)
      ctx.addIssue({ code: 'custom', message: 'Varlık bağlantıları sonuçla örtüşmüyor.' });
    for (const [path, url] of given)
      if (expected.get(path) !== url)
        ctx.addIssue({ code: 'custom', message: 'Varlık bağlantısı işe ait değil.' });
  });
export type LiveJob = z.infer<typeof liveJobSchema>;

// Runner'in `report.json`'u (sema 2, mergen_imaging/runner.py). Sonuc ZIP'inin
// icindeki bu dosya arayuze bolge hacimlerini ve inceleme bayraklarini verir.
// Bayragin metni degil, *gerekcesi ve sayilari* okunur: metin sunucuda tek
// dilde uretiliyor, arayuz iki dilli.
export const reviewFlagSchema = z.object({
  finding: z.string(),
  severity: z.string(),
  reason: z.string(),
  message: z.string(),
  evidence: z.object({
    tumor_core_voxels: z.number().int().nonnegative(),
    enhancing_voxels: z.number().int().nonnegative(),
    enhancing_threshold: z.number().int().nonnegative(),
  }),
});
export type ReviewFlag = z.infer<typeof reviewFlagSchema>;

export const liveReportSchema = z.object({
  schemaVersion: z.literal(2),
  status: z.literal('research-output'),
  modelId: slug,
  modelVersion: z.string().min(1),
  rule: z.object({
    id: z.string(),
    version: z.string(),
    tcMin: z.number().int().nonnegative(),
    etMin: z.number().int().nonnegative(),
    minComponentVoxels: z.number().int().nonnegative(),
  }),
  regionVolumes: z.object({
    TC: z.number().int().nonnegative(),
    WT: z.number().int().nonnegative(),
    ET: z.number().int().nonnegative(),
  }),
  reviewFlags: z.array(reviewFlagSchema),
  notice: z.string().min(1),
}).superRefine((report, ctx) => {
  // Cekirdek ve kontrast tutan bolge butun tumorun icindedir; disari tasan bir
  // sayi ekranda sessizce yanlis bir hacim gosterirdi.
  const { TC, WT, ET } = report.regionVolumes;
  if (TC > WT || ET > WT)
    ctx.addIssue({ code: 'custom', message: 'Bölge hacimleri bütün tümörü aşıyor.' });
});
export type LiveReport = z.infer<typeof liveReportSchema>;
