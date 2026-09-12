import { manifestSchema, type DataSource } from './contracts';

export const demoSource: DataSource = {
  async listCases(signal) {
    const response = await fetch('/demo/manifest.json', { signal, cache: 'no-cache' });
    if (!response.ok) throw new Error('Demo vaka paketi yüklenemedi.');
    const result = manifestSchema.safeParse(await response.json());
    if (!result.success) throw new Error('Demo vaka paketi beklenen biçimde değil.');
    return result.data.cases;
  },
};

// F4: Implement the same interface with the authenticated backend contract.
// Never fall back to demo records when a live request fails.
export const liveSource: DataSource = {
  async listCases() {
    throw new Error(
      'Canlı analiz bağlantısı henüz kurulmadı. Hazır vakalara demo modundan ulaşabilirsiniz.',
    );
  },
};
