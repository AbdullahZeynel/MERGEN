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

  it('never silently substitutes demo records for a disconnected live source', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    await user.click(screen.getByRole('button', { name: 'Canlı analiz' }));
    await screen.findByRole('heading', { name: 'Canlı bağlantı henüz kurulmadı' });
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'TEST-0001' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Hazır demolara dön' }));
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
  it('asks once whether the visitor wants the tour and remembers the answer', async () => {
    const user = mount(undefined, { firstVisit: true });
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Kısa bir tanıtım ister misiniz?');
    await user.click(screen.getByRole('button', { name: 'Evet, göster' }));
    expect(screen.getByRole('heading', { name: 'Vaka listesi' })).toBeVisible();
    // Dort adim, sonuncusunda bitis dugmesi.
    for (const next of ['2D kesit görüntüleyici', '3D segmentasyon', 'Veri ve sınırlar']) {
      await user.click(screen.getByRole('button', { name: 'İleri' }));
      expect(screen.getByRole('heading', { name: next })).toBeVisible();
    }
    await user.click(screen.getByRole('button', { name: 'Başla' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('mergen-guide')).toBe('answered');
  });

  it('takes no for an answer and does not ask again', async () => {
    const user = mount(undefined, { firstVisit: true });
    await screen.findByRole('dialog');
    await user.click(screen.getByRole('button', { name: 'Hayır, doğrudan başla' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('mergen-guide')).toBe('answered');
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
    expect(dialog).toHaveTextContent('kimliksizleştirilmiştir');
    expect(dialog).toHaveTextContent('klinik kararda kullanılamaz');
    // Atif bir DOI'ye gitmeli; metin olarak kalan bir alinti atif sayilmaz.
    expect(screen.getByRole('link', { name: /10\.7937/ })).toHaveAttribute(
      'href',
      'https://doi.org/10.7937/tcia.bdgf-8v37',
    );
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
