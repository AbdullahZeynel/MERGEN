import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { makeCase } from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  document.documentElement.style.removeProperty('color-scheme');
});
const cases = [makeCase('TEST-0001'), makeCase('TEST-0002')];
function mount(payload: unknown = { version: 2, cases }) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
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
  it('filters cases and does not invent a genomic result', async () => {
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
    await user.click(screen.getByRole('button', { name: 'Genomik analiz' }));
    expect(screen.getByRole('heading', { name: 'Bu vakaya ait genomik sonuç yok' })).toBeVisible();
  });
  it('shows malformed and empty packages explicitly', async () => {
    mount({ version: 99, cases });
    expect(await screen.findByRole('alert')).toHaveTextContent('Demo paketi okunamadı');
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
  it('keeps prediction and reference overlays explicitly separate', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    const prediction = screen.getByRole('button', { name: 'Tahmin' });
    const reference = screen.getByRole('button', { name: 'Referans' });
    expect(prediction).toHaveAttribute('aria-pressed', 'true');
    expect(reference).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByAltText('Ensemble tahmin maskesi')).toBeVisible();
    expect(screen.queryByAltText('Referans segmentasyon maskesi')).not.toBeInTheDocument();
    await user.click(prediction);
    await user.click(reference);
    expect(screen.queryByAltText('Ensemble tahmin maskesi')).not.toBeInTheDocument();
    expect(screen.getByAltText('Referans segmentasyon maskesi')).toBeVisible();
  });
});
