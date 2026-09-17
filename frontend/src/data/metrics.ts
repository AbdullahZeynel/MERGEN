import { z } from 'zod';
import raw from './lockedTest.json';

// ── Kilitli test sayilari ────────────────────────────────────────────────
// `frontend/scripts/locked_test_metrics.py` model kayit defterinden uretir,
// `test_locked_test_metrics.py` surukleme olursa duser. Ekran yine de kendi
// tarafinda dogruluyor: araligi disina dusen bir sayi cizilmez.
const interval = z
  .object({ value: z.number(), low: z.number(), high: z.number() })
  .refine((item) => item.low <= item.value && item.value <= item.high, {
    message: 'Sayı kendi güven aralığının dışında.',
  });
export type Interval = z.infer<typeof interval>;
export const lockedTestSchema = z.object({
  split: z.literal('locked test'),
  segmentation: z.object({
    source: z.string().min(1),
    variant: z.string().min(1),
    n: z.number().int().positive(),
    nValForWeights: z.number().int().positive(),
    dice: z.object({ TC: interval, WT: interval, ET: interval, Mean: interval }),
  }),
  pathology: z.object({
    source: z.string().min(1),
    models: z.number().int().positive(),
    n: z.number().int().positive(),
    metrics: z.object({
      macroF1: interval,
      balancedAccuracy: interval,
      auroc: interval,
      mcc: interval,
    }),
  }),
});
export type LockedTest = z.infer<typeof lockedTestSchema>;

// Dosyayi `frontend/scripts/locked_test_metrics.py` yaziyor. Burada bir kez
// dogrulaniyor: bozuk ya da elle duzeltilmis bir dosya sessizce ekrana cikmasin.
export const lockedTest = lockedTestSchema.parse(raw);
