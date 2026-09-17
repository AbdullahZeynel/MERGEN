import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PathologyWorkspace, gridFitsSheet } from '../components/PathologyWorkspace';
import type { SlideRecord } from '../data/contracts';
import { makeSlide, slideModel } from './fixtures';
import { renderWithLanguage } from './render';

const show = (slide: SlideRecord, language: 'tr' | 'en' = 'tr', model = slideModel) =>
  renderWithLanguage(
    <PathologyWorkspace slide={slide} model={model} reviewMargin={0.45} />,
    language,
  );
const probabilities = () => screen.getByRole('region', { name: 'Sınıf olasılıkları' });
const tiles = () => screen.getByRole('region', { name: "En yüksek attention'lı kareler" });

describe('pathology decision', () => {
  it('names the predicted subtype and marks it among the three probabilities', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = probabilities();
    expect(within(panel).getByRole('heading', { name: /Glioblastom · IDH-wildtype/ })).toBeVisible();
    const list = within(panel).getByRole('list');
    expect(list).toHaveTextContent('%90');
    expect(list).toHaveTextContent('%5');
    expect(list.querySelector('li.predicted')).toHaveTextContent('Glioblastom · IDH-wildtype');
  });

  it('keeps the reference label separate from the prediction', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByText('Referans etiket')).toBeVisible();
    expect(screen.getByText('Referansla uyuşuyor')).toBeVisible();
    expect(screen.queryByText('Referansla uyuşmuyor')).not.toBeInTheDocument();
  });

  it('shows a misclassified slide as a result, not as a failure', () => {
    show(makeSlide('TEST-SLIDE-1', { reference: { class: 'A' }, agreesWithReference: false }));
    expect(screen.getByText('Referansla uyuşmuyor')).toBeVisible();
    expect(screen.getByText(/bir arıza değil/)).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getAllByText('Glioblastom · IDH-wildtype')).toHaveLength(2);
    expect(screen.getAllByText('Astrositom · IDH-mutant, 1p/19q korunmuş')).toHaveLength(2);
  });

  it('draws the abstention rule instead of hiding it behind a flag', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const meter = probabilities();
    // Kesin vakada pay 0,85: esigin ustunde ve sayilarla birlikte yazili.
    expect(meter).toHaveTextContent('Eşiğin üstünde');
    expect(meter).toHaveTextContent('olasılık farkı 0,85');
    expect(meter).toHaveTextContent('eşiği 0,45');
    expect(screen.queryByText('Uzman incelemesi gerekir')).not.toBeInTheDocument();
  });

  it('flags an abstaining slide with the margin that produced the flag', () => {
    show(
      makeSlide('TEST-SLIDE-1', {
        prediction: { class: 'G', probabilities: { A: 0.3, O: 0.3, G: 0.4 } },
        needsExpertReview: true,
      }),
    );
    expect(probabilities()).toHaveTextContent('Eşiğin altında');
    expect(screen.getByRole('region', { name: 'Uzman incelemesi gerekir' })).toHaveTextContent(
      '0,45',
    );
  });
});

describe('attention read-out', () => {
  it('says what the colours mean and that the scale is per slide', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const card = screen.getByRole('region', { name: 'Attention yoğunluğu' });
    expect(within(card).getByText(/her slaytta kendi içinde normalize/)).toBeVisible();
    expect(within(card).getByText('düşük')).toBeVisible();
    expect(within(card).getByText('yüksek')).toBeVisible();
  });

  it('reports the concentration numbers and reads the top ten back in words', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const card = screen.getByRole('region', { name: 'Attention yoğunluğu' });
    expect(within(card).getByText('En yüksek kare').nextElementSibling).toHaveTextContent('%4');
    expect(within(card).getByText('İlk 10 kare').nextElementSibling).toHaveTextContent('%24');
    expect(within(card).getByText('Normalize entropi').nextElementSibling).toHaveTextContent('0,65');
    expect(within(card).getByText('Değerlendirilen kare').nextElementSibling).toHaveTextContent(
      '4.096',
    );
    // 4096 karenin 10'u disinda kalan 4086 kare.
    expect(within(card).getByText(/kalanı 4.086 kareye dağılmış/)).toBeVisible();
  });

  it('never claims a diagnosis for the heat map', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByText(/tanı değildir, tümör sınırı çizmez/)).toBeVisible();
  });
});

describe('top attention tiles', () => {
  it('numbers every cell of the declared montage in attention order', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = tiles();
    const cells = within(panel).getAllByRole('img');
    expect(cells).toHaveLength(12);
    expect(cells[0]).toHaveAccessibleName('1. kare');
    expect(cells[11]).toHaveAccessibleName('12. kare');
    // Hucre montajdan kendi karesini kesiyor: ilk sol ust, sonuncu sag alt.
    expect(cells[0].style.backgroundSize).toBe('600% 200%');
    expect(cells[0].style.backgroundPosition.replace(/\s+/g, ' ')).toBe('0% 0%');
    expect(cells[11].style.backgroundPosition.replace(/\s+/g, ' ')).toBe('100% 100%');
    expect(cells[0].style.backgroundImage).toContain(
      '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-1/images/top_tiles',
    );
    expect(panel).toHaveTextContent('224 px kare · 0,5 µm/px ≈ 112 µm');
    expect(panel).toHaveTextContent('azalan sırada numaralandı');
  });

  it('shows the sheet whole when the package declares no layout', () => {
    const slide = makeSlide('TEST-SLIDE-1');
    delete slide.tileGrid;
    show(slide);
    const panel = tiles();
    // Sirasi bilinmeyen bir sayfaya sira numarasi uydurulmaz.
    expect(within(panel).getByAltText(/en yüksek attention'lı kareleri/)).toBeVisible();
    expect(panel).not.toHaveTextContent('azalan sırada numaralandı');
    expect(within(panel).queryByText('1')).not.toBeInTheDocument();
  });

  it('only numbers a sheet whose size matches the declared layout', () => {
    const grid = { tilePx: 224, columns: 6, rows: 2, count: 12, ordering: 'attention_desc' as const, micronsPerPixel: 0.5 };
    expect(gridFitsSheet(grid, 1344, 448)).toBe(true);
    expect(gridFitsSheet(grid, 1344, 672)).toBe(false);
    expect(gridFitsSheet(grid, 1120, 448)).toBe(false);
  });
});

describe('slide context', () => {
  it('points the slide image at the case it belongs to', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByAltText(/TEST-SLIDE-1 slaytında attention/)).toHaveAttribute(
      'src',
      '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-1/images/attention',
    );
  });

  it('handles a missing slide image instead of leaving a broken preview', () => {
    show(makeSlide('TEST-SLIDE-1'));
    fireEvent.error(screen.getByAltText(/TEST-SLIDE-1 slaytında attention/));
    expect(screen.getByRole('heading', { name: 'Slayt görüntüsü yüklenemedi' })).toBeVisible();
    // Kareler etkilenmez.
    expect(within(tiles()).getAllByRole('img')).toHaveLength(12);
  });

  it('says the demo probabilities come from a single network, not the product ensemble', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByText(/tek bir ağdan gelir \(mil_v1\)/)).toBeVisible();
    show(makeSlide('TEST-SLIDE-2'), 'tr', { ...slideModel, ensemble: true, version: 'cv_v1' });
    expect(screen.getByText(/ürün topluluğundan gelir \(cv_v1\)/)).toBeVisible();
  });

  it('links the case record and names the provenance in the reader language', () => {
    show(makeSlide('TEST-SLIDE-1'), 'en');
    expect(screen.getByRole('link', { name: /Case report/ })).toHaveAttribute(
      'href',
      '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-1/report',
    );
    expect(screen.getByText('Contributing site')).toBeVisible();
    expect(screen.getByText('Test Site')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Class probabilities' })).toHaveTextContent(
      'Above the threshold',
    );
    expect(screen.queryByText('MODEL TAHMİNİ')).not.toBeInTheDocument();
  });
});
