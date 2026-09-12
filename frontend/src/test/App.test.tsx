import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { makeCase } from './fixtures';

afterEach(() => vi.unstubAllGlobals());
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
  it('switches all case context without retaining the previous preview or assistant case', async () => {
    const user = mount();
    await screen.findByRole('heading', { name: 'TEST-0001' });
    await user.click(screen.getByRole('button', { name: 'Asistanı aç' }));
    await user.click(screen.getByRole('button', { name: 'Koronal' }));
    await user.click(screen.getByRole('button', { name: /TEST-0002/ }));
    expect(screen.getByRole('heading', { name: 'TEST-0002' })).toBeVisible();
    expect(screen.getByAltText(/TEST-0002 FLAIR/)).toHaveAttribute(
      'src',
      '/api/demo/cases/TEST-0002/slices/axial/77',
    );
    expect(
      within(screen.getByRole('complementary', { name: 'MERGEN Asistan' })).getByText('TEST-0002'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Mesaj gönder' })).toBeDisabled();
    await user.keyboard('{Escape}');
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
});
