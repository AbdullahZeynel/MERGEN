import { describe, it, expect } from 'vitest';
import { manifestSchema } from '../data/contracts';
import { makeCase } from './fixtures';

describe('demo boundary validation', () => {
  it('rejects external assets, mismatched cases and out-of-bounds slices', () => {
    for (const patch of [
      { src: 'https://example.com/scan.png' },
      { src: '/demo/OTHER/axial.png' },
      { index: 155 },
    ]) {
      const c = makeCase('TEST-0001');
      Object.assign(c.previews[0], patch);
      expect(manifestSchema.safeParse({ version: 2, cases: [c] }).success).toBe(false);
    }
  });
  it('rejects duplicate case identities and duplicate axes', () => {
    const c = makeCase('TEST-0001');
    expect(manifestSchema.safeParse({ version: 2, cases: [c, c] }).success).toBe(false);
    c.previews[1].axis = 'axial';
    expect(manifestSchema.safeParse({ version: 2, cases: [c] }).success).toBe(false);
  });
  it('accepts only case-bound content-addressed GLB meshes', () => {
    const c = makeCase('TEST-0001');
    const digest = 'a'.repeat(64);
    c.mesh = `/api/demo/cases/${c.id}/mesh/${digest}.glb`;
    expect(manifestSchema.safeParse({ version: 2, cases: [c] }).success).toBe(true);
    c.mesh = `/api/demo/cases/OTHER/mesh/${digest}.glb`;
    expect(manifestSchema.safeParse({ version: 2, cases: [c] }).success).toBe(false);
    c.mesh = `/api/demo/cases/${c.id}/mesh/not-a-digest.glb`;
    expect(manifestSchema.safeParse({ version: 2, cases: [c] }).success).toBe(false);
  });
});
