import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ValidationDialog } from '../components/ValidationDialog';
import { lockedTest } from '../data/metrics';
import { makeFigure, makeFlag } from './fixtures';
import { withLanguage } from './render';

afterEach(() => vi.unstubAllGlobals());

const score = (value: number) =>
  new Intl.NumberFormat('tr', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(value);

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
    const [segmentation, pathology] = screen.getAllByRole('table');
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

  it('lists a measured figure with its volumes, its scores and its rule', async () => {
    show();
    const figure = await screen.findByRole('img', { name: /TEST-FIGURE-1/ });
    expect(figure).toHaveAttribute(
      'src',
      '/api/demo/modules/imaging/diseases/glioma/examples/TEST-FIGURE-1/figure',
    );
    const table = screen.getAllByRole('table')[2];
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
    expect(screen.getAllByRole('table')).toHaveLength(2);
  });
});
