import { describe, expect, it } from 'vitest';
import { slideManifestSchema, validationSchema } from '../data/contracts';
import { makeFigure, makeSlide, makeSlideManifest } from './fixtures';

const parse = (cases: unknown[]) => slideManifestSchema.safeParse(makeSlideManifest(cases as never));

describe('pathology package validation', () => {
  it('accepts a package whose every claim holds', () => {
    expect(parse([makeSlide('TEST-SLIDE-1'), makeSlide('TEST-SLIDE-2')]).success).toBe(true);
  });

  it('refuses an abstention flag the declared margin does not support', () => {
    // Esik 0,45; ilk iki olasilik arasi 0,85 → cekimser olamaz.
    expect(parse([makeSlide('TEST-SLIDE-1', { needsExpertReview: true })]).success).toBe(false);
    // Ve tersi: fark esigin altindayken bayrak dusurulemez.
    const close = makeSlide('TEST-SLIDE-1', {
      prediction: { class: 'G', probabilities: { A: 0.3, O: 0.3, G: 0.4 } },
    });
    expect(parse([close]).success).toBe(false);
    close.needsExpertReview = true;
    expect(parse([close]).success).toBe(true);
  });

  it('refuses an agreement claim the reference does not support', () => {
    const lying = makeSlide('TEST-SLIDE-1', { reference: { class: 'A' } });
    expect(parse([lying]).success).toBe(false);
    lying.agreesWithReference = false;
    expect(parse([lying]).success).toBe(true);
  });

  it('refuses an agreement claim with no reference at all', () => {
    const orphan = makeSlide('TEST-SLIDE-1');
    delete orphan.reference;
    expect(parse([orphan]).success).toBe(false);
  });

  it('refuses an asset that belongs to another slide', () => {
    const stolen = makeSlide('TEST-SLIDE-1');
    stolen.assets.attention =
      '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-2/images/attention';
    expect(parse([stolen]).success).toBe(false);
  });

  it('refuses a reported class that is not the highest probability', () => {
    const wrong = makeSlide('TEST-SLIDE-1', {
      prediction: { class: 'A', probabilities: { A: 0.05, O: 0.05, G: 0.9 } },
    });
    expect(parse([wrong]).success).toBe(false);
  });

  it('refuses a repeated slide identity', () => {
    const slide = makeSlide('TEST-SLIDE-1');
    expect(parse([slide, slide]).success).toBe(false);
  });
});

describe('measured figure validation', () => {
  const wrap = (examples: unknown[]) =>
    validationSchema.safeParse({ schemaVersion: 4, examples });

  it('accepts a measured figure and a package with no figures at all', () => {
    expect(wrap([makeFigure('TEST-FIGURE-1')]).success).toBe(true);
    const empty = validationSchema.safeParse({ schemaVersion: 3 });
    expect(empty.success && empty.data.examples).toEqual([]);
  });

  it('refuses a score with no reference volume behind it', () => {
    // AGENTS.md 6. madde: referanssiz skor gosterilmez.
    const unbacked = makeFigure('TEST-FIGURE-1', {
      regionVolumes: { prediction: { TC: 1100, WT: 3900, ET: 950 } },
    });
    expect(wrap([unbacked]).success).toBe(false);
  });

  it('refuses a figure image that belongs to another record', () => {
    const stolen = makeFigure('TEST-FIGURE-1', {
      figure: '/api/demo/modules/imaging/diseases/glioma/examples/TEST-FIGURE-2/figure',
    });
    expect(wrap([stolen]).success).toBe(false);
  });

  it('keeps a flag with its reason and its numbers, not a bare string', () => {
    const flagless = makeFigure('TEST-FIGURE-1', {
      reviewFlags: [{ finding: 'tumor_core' } as never],
    });
    expect(wrap([flagless]).success).toBe(false);
  });
});
