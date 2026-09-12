import { manifestSchema, type DataSource } from './contracts';

export const demoSource: DataSource = {
  async listCases(signal) {
    const response = await fetch('/api/demo/cases', { signal, cache: 'no-cache' });
    if (!response.ok) throw new Error('Demo servisine ulaşılamadı. API ve MCP bağlantısını kontrol edin.');
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
