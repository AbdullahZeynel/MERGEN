import { expect, it } from 'vitest';
import { parseMesh } from '../data/mesh';

it('rejects invalid coordinates and face indices before WebGL upload', () => {
  expect(() => parseMesh({ ET: { vertices: [[0, 0, NaN]], faces: [[0, 0, 0]] } })).toThrow();
  expect(() => parseMesh({ ET: { vertices: [[0, 0, 0]], faces: [[0, 1, 0]] } })).toThrow();
  expect(() => parseMesh({})).toThrow();
  expect(
    parseMesh({
      ET: {
        vertices: [
          [0, 0, 0],
          [1, 0, 0],
          [0, 1, 0],
        ],
        faces: [[0, 1, 2]],
      },
    }).ET?.faces,
  ).toHaveLength(1);
});
