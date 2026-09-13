import { describe, expect, it } from 'vitest';
import {
  genomicsCaseSchema,
  genomicsExplanationSchema,
  genomicsManifestSchema,
  genomicsResultSchema,
} from '../data/genomics';
import { makeGenomicsCase, makeGenomicsExplanation, makeGenomicsResult } from './fixtures';

const manifest = (cases = [makeGenomicsCase()]) => ({
  schemaVersion: 3 as const,
  module: 'genomics' as const,
  disease: 'glioma-variant-pathogenicity' as const,
  decisionThreshold: 0.5,
  cases,
});

describe('genomik sözleşmesi', () => {
  it('geçerli manifesti kabul eder', () => {
    expect(genomicsManifestSchema.safeParse(manifest()).success).toBe(true);
  });

  it('tekrarlanan vaka kimliğini reddeder', () => {
    const iki = [makeGenomicsCase(), makeGenomicsCase()];
    expect(genomicsManifestSchema.safeParse(manifest(iki)).success).toBe(false);
  });

  it('id ile caseId tutarsızlığını reddeder', () => {
    const bozuk = { ...makeGenomicsCase(), caseId: 'BASKA' };
    expect(genomicsManifestSchema.safeParse(manifest([bozuk])).success).toBe(false);
  });

  it('canlı sonucu hazır demo koleksiyonunda kabul etmez', () => {
    const canli = { ...makeGenomicsResult(), mode: 'live' };
    expect(genomicsResultSchema.safeParse(canli).success).toBe(false);
  });

  it('referans etiketi iddiasını reddeder', () => {
    const bozuk = { ...makeGenomicsResult(), hasGroundTruth: true };
    expect(genomicsResultSchema.safeParse(bozuk).success).toBe(false);
  });

  it('olasılık aralığını zorlar', () => {
    const bozuk = makeGenomicsResult();
    bozuk.prediction.pathogenicityProbability = 1.4;
    expect(genomicsResultSchema.safeParse(bozuk).success).toBe(false);
  });

  it('geçersiz protein değişimini reddeder', () => {
    const bozuk = { ...makeGenomicsCase(), proteinChange: 'R132H' };
    expect(genomicsCaseSchema.safeParse(bozuk).success).toBe(false);
  });

  it('SHAP toplamsallığı tutmuyorsa reddeder', () => {
    const bozuk = { ...makeGenomicsExplanation(), rawMargin: 9 };
    expect(genomicsExplanationSchema.safeParse(bozuk).success).toBe(false);
  });

  it('SHAP uzayı margin değilse reddeder', () => {
    const bozuk = { ...makeGenomicsExplanation(), space: 'probability' };
    expect(genomicsExplanationSchema.safeParse(bozuk).success).toBe(false);
  });

  it('doğru açıklamayı kabul eder', () => {
    expect(genomicsExplanationSchema.safeParse(makeGenomicsExplanation()).success).toBe(true);
  });
});
