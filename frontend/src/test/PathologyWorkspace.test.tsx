import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PathologyWorkspace } from '../components/PathologyWorkspace';
import type { SlideRecord } from '../data/contracts';
import { makeSlide, slideModel } from './fixtures';
import { renderWithLanguage } from './render';

const show = (slide: SlideRecord, language: 'tr' | 'en' = 'tr', model = slideModel) =>
  renderWithLanguage(
    <PathologyWorkspace slide={slide} model={model} reviewMargin={0.45} />,
    language,
  );

describe('pathology workspace', () => {
  it('names the predicted subtype and marks it among the three probabilities', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByText('MODEL TAHMİNİ')).toBeVisible();
    const list = screen.getByRole('list');
    expect(list).toHaveTextContent('Glioblastom · IDH-wildtype');
    expect(list).toHaveTextContent('%90');
    expect(list).toHaveTextContent('%5');
    // Tahmin edilen sinif satirinda isaretli; rozet sayilarla ayni yerde.
    const predicted = list.querySelector('li.predicted');
    expect(predicted).toHaveTextContent('Glioblastom · IDH-wildtype');
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
    // Yanlis siniflama hata degil: uyari/alarm rolu almaz.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // Tahmin de referans da okunur kalir: biri ustte, biri olasilik listesinde.
    expect(screen.getAllByText('Glioblastom · IDH-wildtype')).toHaveLength(2);
    expect(screen.getAllByText('Astrositom · IDH-mutant, 1p/19q korunmuş')).toHaveLength(2);
  });

  it('flags an abstaining slide with the margin that produced the flag', () => {
    show(
      makeSlide('TEST-SLIDE-1', {
        prediction: { class: 'G', probabilities: { A: 0.3, O: 0.3, G: 0.4 } },
        reference: { class: 'G' },
        agreesWithReference: true,
        needsExpertReview: true,
      }),
    );
    const band = screen.getByRole('region', { name: 'Uzman incelemesi gerekir' });
    expect(band).toHaveTextContent('0,45');
  });

  it('leaves a confident slide unflagged', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.queryByText('Uzman incelemesi gerekir')).not.toBeInTheDocument();
  });

  it('reports how concentrated the attention is and on how many tiles', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByText('Attention yoğunluğu')).toBeVisible();
    expect(screen.getByText('En yüksek kare').nextElementSibling).toHaveTextContent('%4');
    expect(screen.getByText('İlk 10 kare').nextElementSibling).toHaveTextContent('%24');
    expect(screen.getByText('Normalize entropi').nextElementSibling).toHaveTextContent('0,65');
    expect(screen.getByText('Değerlendirilen kare').nextElementSibling).toHaveTextContent('4.096');
  });

  it('points every image at the slide it belongs to', () => {
    show(makeSlide('TEST-SLIDE-1'));
    const base = '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-1';
    expect(screen.getByAltText(/TEST-SLIDE-1 slaytında attention/)).toHaveAttribute(
      'src',
      `${base}/images/attention`,
    );
    expect(screen.getByAltText(/en yüksek attention'lı kareleri/)).toHaveAttribute(
      'src',
      `${base}/images/top_tiles`,
    );
  });

  it('handles a missing slide image instead of leaving a broken preview', () => {
    show(makeSlide('TEST-SLIDE-1'));
    fireEvent.error(screen.getByAltText(/TEST-SLIDE-1 slaytında attention/));
    expect(screen.getByRole('heading', { name: 'Slayt görüntüsü yüklenemedi' })).toBeVisible();
    // Diger cerceve etkilenmez.
    expect(screen.getByAltText(/en yüksek attention'lı kareleri/)).toBeVisible();
  });

  it('says the demo probabilities come from a single network, not the product ensemble', () => {
    show(makeSlide('TEST-SLIDE-1'));
    expect(screen.getByText(/tek bir ağdan gelir \(mil_v1\)/)).toBeVisible();
    show(makeSlide('TEST-SLIDE-2'), 'tr', { ...slideModel, ensemble: true, version: 'cv_v1' });
    expect(screen.getByText(/ürün topluluğundan gelir \(cv_v1\)/)).toBeVisible();
  });

  it('links the case record and the slide context in the reader language', () => {
    show(makeSlide('TEST-SLIDE-1'), 'en');
    expect(screen.getByRole('link', { name: /Case report/ })).toHaveAttribute(
      'href',
      '/api/demo/modules/pathology/diseases/glioma/cases/TEST-SLIDE-1/report',
    );
    expect(screen.getByText('Contributing site')).toBeVisible();
    expect(screen.getByText('Test Site')).toBeVisible();
    expect(screen.queryByText('MODEL TAHMİNİ')).not.toBeInTheDocument();
  });
});
