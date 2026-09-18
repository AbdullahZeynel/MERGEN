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
const decision = () => screen.getByRole('region', { name: 'Sınıf olasılıkları' });
const tiles = () => screen.getByRole('region', { name: "En yüksek attention'lı kareler" });
const reading = () => screen.getByRole('region', { name: 'Isı haritası nasıl okunur' });

describe('the decision, the way the report states it', () => {
  it('names the model decision, the reference and whether they agree', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = decision();
    expect(within(panel).getByRole('heading', { name: /Glioblastom · IDH-wildtype/ })).toBeVisible();
    expect(panel).toHaveTextContent('5-fold topluluk');
    expect(panel).toHaveTextContent('Patoloji referansı');
    expect(within(panel).getByText('DOĞRU')).toBeVisible();
    // Rapordaki gibi olasiliklar 0–1 arasi uc ondalikla yazilir.
    const list = within(panel).getByRole('list');
    expect(list).toHaveTextContent('0,900');
    expect(list).toHaveTextContent('0,050');
  });

  it('marks the reference class on its own row', () => {
    show(makeSlide('TEST-SLIDE-1', { reference: { class: 'A' }, agreesWithReference: false }));
    const rows = within(decision()).getAllByRole('listitem');
    const marked = rows.filter((row) => within(row).queryByLabelText('patoloji referansı'));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent('Astrositom · IDH-mutant, 1p/19q korunmuş');
  });

  it('writes a wrong call as a result, not as a failure', () => {
    show(makeSlide('TEST-SLIDE-1', { reference: { class: 'A' }, agreesWithReference: false }));
    expect(within(decision()).getByText('HATALI')).toBeVisible();
    expect(screen.getByText(/bir arıza değil/)).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('puts the case context on one line the way the figure captions do', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = decision();
    expect(panel).toHaveTextContent('WHO derecesi G4');
    expect(panel).toHaveTextContent('Test Site');
    expect(panel).toHaveTextContent('kilitli test kümesi');
    expect(panel).toHaveTextContent('4.096');
  });

  it('says plainly when a case comes from the validation split', () => {
    show(makeSlide('TEST-SLIDE-1', { split: 'val', predictionSource: 'mil_v1' }));
    const panel = decision();
    expect(panel).toHaveTextContent('doğrulama bölmesi');
    expect(panel).toHaveTextContent(/ürün iddiası değildir/);
    expect(panel).toHaveTextContent('tek ağ');
  });

  it('draws the top-2 gap against the threshold and states what the flag is worth', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = decision();
    expect(panel).toHaveTextContent('Top-2 farkı');
    expect(panel).toHaveTextContent('Bayrak kapalı');
    expect(panel).toHaveTextContent('olasılık farkı 0,850');
    expect(panel).toHaveTextContent('eşiği 0,45');
    // Rapordaki sinir: bir guvenlik agi degil, siralama yardimi.
    expect(panel).toHaveTextContent('22 hatanın 7');
    expect(panel).toHaveTextContent(/güvenlik ağı değil/);
  });

  it('raises the flag when the gap falls under the threshold', () => {
    show(
      makeSlide('TEST-SLIDE-1', {
        prediction: { class: 'G', probabilities: { A: 0.3, O: 0.3, G: 0.4 } },
        needsExpertReview: true,
      }),
    );
    expect(decision()).toHaveTextContent('Bayrak açık');
    expect(screen.getByRole('region', { name: 'Uzman incelemesi gerekir' })).toHaveTextContent(
      '0,45',
    );
  });
});

describe('the heat map, and what it is not', () => {
  it('carries the three statements the report insists on', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = reading();
    expect(within(panel).getByText(/segmentasyonu değildir/)).toBeVisible();
    expect(within(panel).getByText(/bulgu haritası değildir/)).toBeVisible();
    expect(within(panel).getByText(/hangi karelere daha fazla ağırlık verdiğinin/)).toBeVisible();
  });

  it('names the scale it was drawn with and how many tiles it covers', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(reading()).toHaveTextContent('4.096 kare · renk = ham attention ağırlığı');
    // Ham agirlik olcegi okunmaz bir harita verir; ekran bunu saklamıyor.
    expect(reading()).toHaveTextContent(/ölçeğin alt ucunda/);
    // Uyari goruntunun ustunde durur: yan paneldeki bir cumle, ekranin
    // ortasindaki resmi raporun figuru gibi okutmayi engellemiyor.
    expect(screen.getByText('HAM AĞIRLIK RENDERI · OKUNAKLI DEĞİL')).toBeVisible();
  });

  it('switches its caption when the package carries the percentile rendering', () => {
    show(
      makeSlide('TEST-SLIDE-1', {
        attention: {
          modelId: 'mergen-wsi-attention-mil',
          modelVersion: 'mil_v1',
          tilesEvaluated: 8192,
          scale: 'within_slide_percentile',
        },
      }),
    );
    expect(reading()).toHaveTextContent('8.192 kare · renk = slayt içi attention yüzdeliği');
    expect(reading()).not.toHaveTextContent(/ölçeğin alt ucunda/);
    expect(screen.queryByText('HAM AĞIRLIK RENDERI · OKUNAKLI DEĞİL')).toBeNull();
  });

  it('separates the network that drew the map from the model that decided', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(reading()).toHaveTextContent(/tek ağdan \(mil_v1\) gelir/);
    expect(reading()).toHaveTextContent(/karar 5-fold topluluk tarafından verilir/);
  });
});

describe('the tiles that carried the decision', () => {
  it('numbers every cell of the declared montage in attention order', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = tiles();
    const cells = within(panel).getAllByRole('img');
    expect(cells).toHaveLength(12);
    expect(cells[0]).toHaveAccessibleName('1. kare');
    expect(cells[11]).toHaveAccessibleName('12. kare');
    expect(cells[0].style.backgroundSize).toBe('600% 200%');
    expect(cells[0].style.backgroundPosition.replace(/\s+/g, ' ')).toBe('0% 0%');
    expect(cells[11].style.backgroundPosition.replace(/\s+/g, ' ')).toBe('100% 100%');
    expect(panel).toHaveTextContent('224 px kare · 0,5 µm/px ≈ 112 µm');
    expect(panel).toHaveTextContent('azalan sırada numaralandı');
  });

  it('shows the sheet whole when the package declares no layout', () => {
    const slide = makeSlide('TEST-SLIDE-1');
    delete slide.tileGrid;
    show(slide);
    expect(within(tiles()).getByAltText(/en yüksek attention'lı kareleri/)).toBeVisible();
    expect(tiles()).not.toHaveTextContent('azalan sırada numaralandı');
  });

  it('only numbers a sheet whose size matches the declared layout', () => {
    const grid = {
      tilePx: 224,
      columns: 6,
      rows: 2,
      count: 12,
      ordering: 'attention_desc' as const,
      micronsPerPixel: 0.5,
    };
    expect(gridFitsSheet(grid, 1344, 448)).toBe(true);
    expect(gridFitsSheet(grid, 1344, 672)).toBe(false);
    expect(gridFitsSheet(grid, 1120, 448)).toBe(false);
  });
});

describe('slide statistics and provenance', () => {
  it('refuses to present the concentration numbers as a confidence signal', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const panel = screen.getByRole('region', { name: 'Attention yoğunluğu' });
    // Rapor bunu kilitli testte olctu: dogru ve hatali vakalari ayirmiyorlar.
    expect(panel).toHaveTextContent(/güvenilirlik göstergesi değildir/);
    expect(panel).toHaveTextContent('p=0,36');
    expect(within(panel).getByText('En yüksek kare').nextElementSibling).toHaveTextContent('%4');
  });

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
    expect(within(tiles()).getAllByRole('img')).toHaveLength(12);
  });

  it('links the case record and reads in the reader language', () => {
    show(makeSlide('TEST-SLIDE-1'), 'en');
    expect(screen.getByRole('link', { name: /Case report/ })).toHaveAttribute(
      'href',
      '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-1/report',
    );
    expect(screen.getByRole('region', { name: 'Class probabilities' })).toHaveTextContent(
      'locked test split',
    );
    expect(screen.getByText(/not a pixel-level tumour segmentation/)).toBeVisible();
    expect(screen.queryByText('DOĞRU')).not.toBeInTheDocument();
  });
});
