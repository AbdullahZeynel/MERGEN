import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { makeCase } from './fixtures';
import { withLanguage } from './render';

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  document.documentElement.removeAttribute('lang');
  delete document.documentElement.dataset.theme;
  document.documentElement.style.removeProperty('color-scheme');
});
const cases = [makeCase('TEST-0001'), makeCase('TEST-0002')];
function mount(payload: unknown = { version: 2, cases }, { firstVisit = false } = {}) {
  // Ilk ziyaret tanitimi bir modal; cogu test onu gormemis bir ziyaretci varsayar.
  if (!firstVisit) window.localStorage.setItem('mergen-guide', 'answered');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    withLanguage(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    ),
  );
  return userEvent.setup();
}

describe('case workspace', () => {
  it('switches theme and remembers the preference', async () => {
    window.localStorage.setItem('mergen-theme', 'light');
    const user = mount();
    const toggle = screen.getByRole('button', { name: 'Koyu temaya geç' });
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(window.localStorage.getItem('mergen-theme')).toBe('dark');
    expect(toggle).toHaveAccessibleName('Açık temaya geç');
  });

  it('switches case context and keeps the deferred assistant hidden', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    expect(screen.queryByRole('button', { name: /Asistan/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Koronal' }));
    await user.click(screen.getByRole('button', { name: /TEST-0002/ }));
    expect(screen.getByRole('heading', { name: 'TEST-0002' })).toBeVisible();
    expect(screen.getByAltText(/TEST-0002 FLAIR/)).toHaveAttribute(
      'src',
      '/api/demo/cases/TEST-0002/slices/axial/77',
    );
    expect(screen.queryByRole('complementary', { name: 'MERGEN Asistan' })).not.toBeInTheDocument();
  });
  it('vaka listesini raydan açıp kapatır ve seçimde geniş ekranda açık bırakır', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    const liste = () => screen.getByRole('complementary', { name: 'Vakalar' });
    expect(liste()).toHaveClass('open');
    const gizle = screen.getByRole('button', { name: 'Vaka listesini gizle' });
    expect(gizle).toHaveAttribute('aria-expanded', 'true');
    await user.click(gizle);
    expect(liste()).toHaveClass('collapsed');
    const goster = screen.getByRole('button', { name: 'Vaka listesini göster' });
    expect(goster).toHaveAttribute('aria-expanded', 'false');
    await user.click(goster);
    expect(liste()).toHaveClass('open');
    // Geniş ekranda liste çalışma alanının üstüne binmiyor; seçim onu kapatmamalı.
    await user.click(screen.getByRole('button', { name: /TEST-0002/ }));
    expect(liste()).toHaveClass('open');
  });

  it('never puts a demo record on the live path', async () => {
    // Canli mod kendi ekranini surer ve once erisim kodu ister; hazir vaka,
    // kesiti ya da vaka basligi o ekranda gorunemez.
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    await user.click(screen.getByRole('button', { name: 'Canlı analiz' }));
    await screen.findByLabelText('Erişim kodu');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'TEST-0001' })).not.toBeInTheDocument();
    expect(screen.getByText('Canlı modda hazır vaka listesi yoktur')).toBeVisible();
    expect(screen.getByText('Canlı veriler yalnız oturum süresince tutulur')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Hazır demo' }));
    await screen.findByRole('heading', { name: 'TEST-0001' });
  });
  it('filters imaging cases without inventing results', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    await user.type(screen.getByRole('textbox', { name: 'Vaka ara' }), '0002');
    expect(screen.queryByRole('button', { name: /TEST-0001/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /TEST-0002/ })).toBeVisible();
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Vaka durumunu filtrele' }),
      'processing',
    );
    expect(screen.getByText('Eşleşen vaka bulunamadı.')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Henüz vaka yok' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'TEST-0001' })).not.toBeInTheDocument();
  });
  it('shows malformed and empty packages explicitly', async () => {
    mount({ version: 99, cases });
    expect(await screen.findByRole('alert')).toHaveTextContent('Demo paketi okunamadı');
    // Durum satırı istek başarısızken hazır olduğunu iddia etmiyor.
    expect(screen.getByText('Demo servisine ulaşılamadı')).toBeVisible();
  });
  it('shows a genuine empty archive', async () => {
    mount({ version: 2, cases: [] });
    expect(await screen.findByRole('heading', { name: 'Henüz vaka yok' })).toBeVisible();
  });
  it('handles a missing image instead of leaving a broken preview', async () => {
    mount();
    const image = await screen.findByAltText(/TEST-0001 FLAIR/);
    fireEvent.error(image);
    expect(screen.getByRole('heading', { name: 'Kesit görüntüsü yüklenemedi' })).toBeVisible();
  });
  it('navigates all slices, clamps bounds and remembers each axis', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    const slider = screen.getByRole('slider', { name: 'Kesit seç' });
    fireEvent.change(slider, { target: { value: '155' } });
    expect(screen.getByRole('button', { name: 'Sonraki kesit' })).toBeDisabled();
    expect(screen.getByAltText(/FLAIR/)).toHaveAttribute(
      'src',
      '/api/demo/cases/TEST-0001/slices/axial/154',
    );
    await user.click(screen.getByRole('button', { name: 'Koronal' }));
    expect(slider).toHaveValue('121');
    fireEvent.change(slider, { target: { value: '1' } });
    expect(screen.getByRole('button', { name: 'Önceki kesit' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Aksiyel' }));
    expect(slider).toHaveValue('155');
    fireEvent.keyDown(screen.getByLabelText('Kesit görüntüsü; ok tuşlarıyla gezin'), {
      key: 'ArrowLeft',
    });
    expect(slider).toHaveValue('154');
  });
  it('invites once from the rail and remembers either answer', async () => {
    const user = mount(undefined, { firstVisit: true });
    await screen.findByRole('heading', { name: 'TEST-0001' });
    // Davet bir modal degil: sayfa kullanilabilir kalir, baloncuk rayin yaninda durur.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText('Kısa bir tanıtım ister misiniz?')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Şimdi değil' }));
    expect(screen.queryByText('Kısa bir tanıtım ister misiniz?')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('mergen-guide')).toBe('answered');
    // Dugme kalir; tur her zaman oradan acilir.
    expect(screen.getByRole('button', { name: 'Tanıtımı başlat' })).toBeVisible();
  });

  it('walks the real page: spotlights each area, spins the model, ends at the data sources', async () => {
    const user = mount(undefined, { firstVisit: true });
    await screen.findByRole('heading', { name: 'TEST-0001' });
    const spins: boolean[] = [];
    window.addEventListener('mergen:tour-spin', (e) => spins.push((e as CustomEvent).detail.on));
    await user.click(screen.getByRole('button', { name: 'Başlat' }));
    const seen: string[] = [];
    for (let guard = 0; guard < 12; guard += 1) {
      const dialog = screen.getByRole('dialog');
      const title = dialog.querySelector('h2')!.textContent!;
      seen.push(title);
      // Spot gercek bir hedefe bagli: veri kaynaklari adiminda ust cubuktaki dugme.
      if (title === 'Veri kaynakları ve gizlilik') {
        expect(document.querySelector('[data-tour="data-sources"]')).not.toBeNull();
      }
      const next = screen.queryByRole('button', { name: 'İleri' });
      if (!next) break;
      await user.click(next);
    }
    expect(seen[0]).toBe('Vaka listesi');
    expect(seen).toEqual(expect.arrayContaining([
      'Veri kaynağı', 'Vaka bağlamı', '2D kesit görüntüleyici', 'Segmentasyon katmanları',
      '3D segmentasyon', 'Veri kaynakları ve gizlilik',
    ]));
    expect(seen[seen.length - 1]).toBe('Veri kaynakları ve gizlilik');
    // 3D adimina girince model doner, cikinca durur.
    expect(spins).toEqual([true, false]);
    await user.click(screen.getByRole('button', { name: 'Başla' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('mergen-guide')).toBe('answered');
  });

  it('opens the case list for its first step even when it was collapsed', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    await user.click(screen.getByRole('button', { name: 'Vaka listesini gizle' }));
    expect(document.getElementById('case-sidebar')).toHaveClass('collapsed');
    await user.click(screen.getByRole('button', { name: 'Tanıtımı başlat' }));
    expect(document.getElementById('case-sidebar')).toHaveClass('open');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('names the dataset, its licence and the de-identification in one place', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    // Aciklama kaydirmadan ulasilabilir olmali: ust cubukta ve alt bilgide.
    const entries = screen.getAllByRole('button', { name: 'Veri kaynakları ve gizlilik' });
    expect(entries).toHaveLength(2);
    expect(entries[0].closest('.topbar')).not.toBeNull();
    await user.click(entries[0]);
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('UCSF-PDGM');
    expect(dialog).toHaveTextContent('CC BY 4.0');
    expect(dialog).toHaveTextContent('etik kurulunca onaylanmış');
    expect(dialog).toHaveTextContent('skull-stripped');
    // Kafatasi cikarma TCIA'nin isi degil; yanlis atif geri gelmesin.
    expect(dialog.textContent).not.toMatch(/Archive tarafından kimliksizleştir/);
    expect(dialog).toHaveTextContent('klinik kararda kullanılamaz');
    // Atif bir DOI'ye gitmeli; metin olarak kalan bir alinti atif sayilmaz.
    expect(screen.getByRole('link', { name: /10\.7937/ })).toHaveAttribute(
      'href',
      'https://doi.org/10.7937/tcia.bdgf-8v37',
    );
  });

  it('does not claim nothing is uploaded while the live path takes uploads', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    await user.click(screen.getAllByRole('button', { name: 'Veri kaynakları ve gizlilik' })[0]);
    const dialog = await screen.findByRole('dialog');
    // Iddia hazir demoyla sinirli olmali; canli yol kendi verisiyle calisiyor.
    expect(dialog).toHaveTextContent('Hazır demo vakalarında hiçbir veri yüklenmez');
    expect(dialog.textContent).not.toMatch(/Bu gösterimde hasta verisi yüklenmez/);
    // Yukleme kabul eden yol, ne kadar tutuldugunu da soylemeli.
    expect(dialog).toHaveTextContent('Canlı analiz yolu bundan ayrıdır');
    expect(dialog).toHaveTextContent('yalnız oturum süresince tutulur');
    expect(dialog).toHaveTextContent('silinir');
  });

  it('switches the interface language and remembers it', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    expect(document.documentElement).toHaveAttribute('lang', 'tr');
    await user.click(screen.getByRole('button', { name: 'Switch interface language to English' }));
    expect(document.documentElement).toHaveAttribute('lang', 'en');
    expect(window.localStorage.getItem('mergen-language')).toBe('en');
    // Ceviri yalnizca dugmeyi degil, calisma alaninin metnini de degistirmeli.
    expect(screen.getByRole('button', { name: 'Prediction' })).toBeVisible();
    expect(screen.getByText('Research use only, not for clinical decisions', { exact: false }))
      .toBeVisible();
    expect(screen.queryByText('Tahmin')).not.toBeInTheDocument();
  });

  it('never shows the reader where the data is served from', async () => {
    mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    // Hekime gore metin: ic mimari ekranda yer almaz.
    for (const leak of ['MCP', 'VPS', 'spool', 'dispatcher']) {
      expect(document.body.textContent).not.toContain(leak);
    }
  });

  it('keeps prediction and reference overlays explicitly separate', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    const prediction = screen.getByRole('button', { name: 'Tahmin' });
    const reference = screen.getByRole('button', { name: 'Referans' });
    expect(prediction).toHaveAttribute('aria-pressed', 'true');
    expect(reference).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByAltText('Model tahmini segmentasyon maskesi')).toBeVisible();
    expect(screen.queryByAltText('Referans segmentasyon maskesi')).not.toBeInTheDocument();
    await user.click(prediction);
    await user.click(reference);
    expect(screen.queryByAltText('Model tahmini segmentasyon maskesi')).not.toBeInTheDocument();
    expect(screen.getByAltText('Referans segmentasyon maskesi')).toBeVisible();
  });
});
