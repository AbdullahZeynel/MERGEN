import {
  manifestSchema,
  slideManifestSchema,
  validationSchema,
  type DataSource,
  type FigureRecord,
  type SlideManifest,
} from './contracts';

const PATHOLOGY_CASES = '/api/demo/modules/pathology/diseases/glioma/cases';
const IMAGING_CASES = '/api/demo/modules/imaging/diseases/glioma/cases';

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

/** Patoloji koleksiyonu; slaytlar manifestin kendi iddialariyla birlikte gelir. */
export interface SlideSource {
  listSlides(signal?: AbortSignal): Promise<SlideManifest>;
}

export const demoSlides: SlideSource = {
  async listSlides(signal) {
    const response = await fetch(PATHOLOGY_CASES, { signal, cache: 'no-cache' });
    if (!response.ok) throw new Error('Demo servisine ulaşılamadı. API ve MCP bağlantısını kontrol edin.');
    // Manifest kendi esigini, referans uyumunu ve varlik yollarini tasiyor;
    // sema hepsini yeniden turetiyor. Uymayan paket okunmaz sayilir.
    const result = slideManifestSchema.safeParse(await response.json());
    if (!result.success) throw new Error('Patoloji koleksiyonu beklenen biçimde değil.');
    return result.data;
  },
};

// M6: Slayt yukleme ve canli cikarim ayri bir karara bagli (#49). Demo
// slaytlari canli modda gosterilmez.
export const liveSlides: SlideSource = {
  async listSlides() {
    throw new Error('Canlı patoloji yolu henüz bağlanmadı.');
  },
};

/** Olculmus dogrulama figurleri; vaka listesiyle ayni uctan gelir. */
export async function listValidationFigures(signal?: AbortSignal): Promise<FigureRecord[]> {
  const response = await fetch(IMAGING_CASES, { signal, cache: 'no-cache' });
  if (!response.ok) throw new Error('Doğrulama figürleri alınamadı.');
  const result = validationSchema.safeParse(await response.json());
  if (!result.success) throw new Error('Doğrulama figürleri beklenen biçimde değil.');
  return result.data.examples;
}
