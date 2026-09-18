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

// Canli yol bir vaka listesi degil, tek bir oturum ve tek bir istir; sozlesmesi
// data/liveClient.ts, ekrani components/LiveWorkspace.tsx icindedir. Burasi
// yalniz hazir demo paketini okur.
