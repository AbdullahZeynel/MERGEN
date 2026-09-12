export const regions = ['ET', 'TC_NCR', 'ED'] as const;
export type Region = (typeof regions)[number];
export type MeshData = Partial<Record<Region, { vertices: number[][]; faces: number[][] }>>;

export function parseMesh(input: unknown): MeshData {
  if (!input || typeof input !== 'object') throw new Error('Geçersiz mesh');
  const data: MeshData = {};
  for (const region of regions) {
    const item = (input as Record<string, unknown>)[region];
    if (item === undefined) continue;
    if (!item || typeof item !== 'object') throw new Error('Geçersiz bölge');
    const { vertices, faces } = item as Record<string, unknown>;
    if (
      !Array.isArray(vertices) ||
      !Array.isArray(faces) ||
      vertices.length > 500000 ||
      faces.length > 1000000
    )
      throw new Error('Geçersiz mesh boyutu');
    if (
      !vertices.every(
        (v) =>
          Array.isArray(v) &&
          v.length === 3 &&
          v.every((x) => typeof x === 'number' && Number.isFinite(x)),
      )
    )
      throw new Error('Geçersiz koordinat');
    if (
      !faces.every(
        (f) =>
          Array.isArray(f) &&
          f.length === 3 &&
          f.every((i) => Number.isInteger(i) && i >= 0 && i < vertices.length),
      )
    )
      throw new Error('Geçersiz yüzey');
    if (vertices.length && faces.length) data[region] = { vertices, faces };
  }
  if (!Object.keys(data).length) throw new Error('Görüntülenecek segmentasyon bulunamadı');
  return data;
}
