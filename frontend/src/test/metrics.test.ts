import { describe, expect, it } from 'vitest';
import { lockedTest, lockedTestSchema } from '../data/metrics';

describe('locked test numbers', () => {
  it('parses the committed registry extract', () => {
    expect(lockedTest.split).toBe('locked test');
    expect(lockedTest.segmentation.n).toBeGreaterThan(0);
    expect(lockedTest.pathology.models).toBeGreaterThan(1);
  });

  it('refuses a number that sits outside its own interval', () => {
    const broken = structuredClone(lockedTest) as { segmentation: { dice: { TC: { value: number } } } };
    broken.segmentation.dice.TC.value = 0.99;
    expect(lockedTestSchema.safeParse(broken).success).toBe(false);
  });
});
