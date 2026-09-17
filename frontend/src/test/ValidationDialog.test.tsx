import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ValidationDialog } from '../components/ValidationDialog';
import { lockedTest } from '../data/metrics';
import { makeFigure, makeFlag } from './fixtures';
import { withLanguage } from './render';

afterEach(() => vi.unstubAllGlobals());

const score = (value: number) =>
  new Intl.NumberFormat('tr', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(value);
const percent = (value: number) =>
  new Intl.NumberFormat('tr', { style: 'percent', maximumFractionDigits: 1 }).format(value);

function show(payload: unknown = { schemaVersion: 4, examples: [makeFigure('TEST-FIGURE-1')] }, ok = true) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok, json: async () => payload }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    withLanguage(
      <QueryClientProvider client={client}>
        <ValidationDialog onClose={() => {}} />
      </QueryClientProvider>,
    ),
  );
}

describe('validation and limits', () => {
  it('shows the locked-test numbers the registry extract carries', () => {
    show();
    const segmentation = screen.getByRole('table', { name: /UWCSE v3/ });
    const pathology = screen.getByRole('table', { name: /5-fold topluluk/ });
    const dice = lockedTest.segmentation.dice.Mean;
    expect(segmentation).toHaveTextContent(score(dice.value));
    expect(segmentation).toHaveTextContent(`${score(dice.low)} – ${score(dice.high)}`);
    const macro = lockedTest.pathology.metrics.macroF1;
    expect(pathology).toHaveTextContent(score(macro.value));
    expect(pathology).toHaveTextContent(`${score(macro.low)} – ${score(macro.high)}`);
  });

  it('keeps the optimistic validation scores out of the tables', () => {
    show();
    // Doğrulama bölmesi skoru (0,886) yalnizca uyarinin icinde gecebilir;
    // olcut tablosunda gorunmesi urun iddiasi diye okunur.
    for (const table of screen.getAllByRole('table')) {
      expect(table.textContent).not.toContain('0,886');
    }
    expect(screen.getByText(/0,886 ürün iddiası değildir/)).toBeVisible();
  });

  it('never separates the three warnings from the numbers', () => {
    show();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Doğrulama bölmesi şişkindir');
    expect(dialog).toHaveTextContent('Ortalama Dice tek başına yanıltıcıdır');
    expect(dialog).toHaveTextContent('Smoke test performans ölçümü değildir');
    expect(dialog).toHaveTextContent(score(lockedTest.pathology.metrics.auroc.value));
  });

  it('shows the three classes behind the macro average, with their case counts', () => {
    show();
    // Makro-F1 tek basina hangi sinifin zorlandigini soylemez; ekran raporun
    // sinif tablosunu tasimali ve sayilari kayit defterinden almalidir.
    const table = screen.getByRole('table', { name: /Sınıf bazlı/ });
    for (const row of lockedTest.pathology.perClass) {
      const cells = within(table).getByRole('row', { name: new RegExp(`\\(${row.class}\\)`) });
      expect(cells).toHaveTextContent(String(row.n));
      expect(cells).toHaveTextContent(score(row.precision));
      expect(cells).toHaveTextContent(score(row.recall));
      expect(cells).toHaveTextContent(score(row.f1));
    }
    // Sinif sayilari bolme buyuklugunu tutmali: 38 + 25 + 50 = 113.
    const total = lockedTest.pathology.perClass.reduce((sum, row) => sum + row.n, 0);
    expect(total).toBe(lockedTest.pathology.n);
  });

  it('states what the abstention threshold caught and what it missed', () => {
    show();
    const dialog = screen.getByRole('dialog');
    const { threshold, coverage, accuracyKept, errorsCaught, errorsTotal } =
      lockedTest.pathology.abstention;
    expect(dialog).toHaveTextContent(`(${threshold.toString().replace('.', ',')})`);
    expect(dialog).toHaveTextContent(percent(coverage));
    expect(dialog).toHaveTextContent(score(accuracyKept));
    // Bayragin sinirini yazmayan bir ekran onu guvenlik agi diye okutur.
    expect(dialog).toHaveTextContent(`${errorsTotal} hatanın ${errorsCaught} tanesi`);
    expect(dialog).toHaveTextContent('güvenlik ağı değil');
  });

  it('lists a measured figure with its volumes, its scores and its rule', async () => {
    show();
    const figure = await screen.findByRole('img', { name: /TEST-FIGURE-1/ });
    expect(figure).toHaveAttribute(
      'src',
      '/api/demo/modules/imaging/diseases/glioma/examples/TEST-FIGURE-1/figure',
    );
    const table = screen.getByRole('table', { name: 'TEST-FIGURE-1' });
    expect(table).toHaveTextContent('1.000');
    expect(table).toHaveTextContent('1.100');
    expect(table).toHaveTextContent('0,910');
    expect(table).toHaveTextContent('2,50');
    // Olculmeyen bolge bos birakilmaz, olculmedigi yazilir.
    expect(table).toHaveTextContent('ölçülmedi');
    expect(screen.getByText(/uwcse-v3/)).toBeVisible();
  });

  it('shows a figure flag with its reason and numbers', async () => {
    show({ schemaVersion: 4, examples: [makeFigure('TEST-FIGURE-1', { reviewFlags: [makeFlag()] })] });
    expect(await screen.findByText(/Tümör kontrast tutmuyor/)).toBeVisible();
    expect(screen.getByText('Çekirdek').nextElementSibling).toHaveTextContent('812 voxel');
  });

  it('says a package carries no figures instead of showing an empty section', async () => {
    show({ schemaVersion: 4, examples: [] });
    expect(await screen.findByText('Bu demo paketinde doğrulama figürü yok.')).toBeVisible();
  });

  it('reports a failed figure request without hiding the numbers', async () => {
    show(undefined, false);
    expect(await screen.findByRole('alert')).toHaveTextContent('Doğrulama figürleri alınamadı.');
    // Kilitli test sayilari figurlerden bagimsiz: ekranda kalir.
    expect(screen.getByRole('table', { name: /UWCSE v3/ })).toBeVisible();
    expect(screen.getByRole('table', { name: /5-fold topluluk/ })).toBeVisible();
    expect(screen.getByRole('table', { name: /Sınıf bazlı/ })).toBeVisible();
  });
});
