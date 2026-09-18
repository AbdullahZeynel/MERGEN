import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReviewFlagBand } from '../components/ReviewFlagBand';
import { makeFlag } from './fixtures';
import { renderWithLanguage } from './render';

describe('review flag band', () => {
  it('draws nothing when the case carries no flag', () => {
    const { container } = renderWithLanguage(<ReviewFlagBand flags={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('writes the reason in the interface language and keeps its numbers', () => {
    renderWithLanguage(<ReviewFlagBand flags={[makeFlag()]} />);
    expect(screen.getByRole('region', { name: 'İnceleme gerektiren bulgu' })).toBeVisible();
    expect(screen.getByText(/Tümör kontrast tutmuyor/)).toBeVisible();
    // Bayrak bir uyari ikonu degil: dayandigi sayilar da ekranda.
    expect(screen.getByText('Çekirdek').nextElementSibling).toHaveTextContent('812 voxel');
    expect(screen.getByText('Kontrast tutan').nextElementSibling).toHaveTextContent('12 voxel');
    expect(screen.getByText('Eşik').nextElementSibling).toHaveTextContent('250 voxel');
  });

  it('translates the reason rather than repeating the package text', () => {
    renderWithLanguage(<ReviewFlagBand flags={[makeFlag()]} />, 'en');
    expect(screen.getByText(/shows no enhancement/)).toBeVisible();
    expect(screen.queryByText('Paketin kendi metni.')).not.toBeInTheDocument();
    expect(screen.getByText('Core').nextElementSibling).toHaveTextContent('812 voxels');
  });

  it('shows an unknown reason with the package message instead of swallowing the flag', () => {
    // Yeni bir gerekce sozluge girene kadar bayrak kaybolmaz.
    renderWithLanguage(
      <ReviewFlagBand
        flags={[makeFlag({ reason: 'future_rule', evidence: { unknown_metric: 7 } })]}
      />,
    );
    expect(screen.getByText('Paketin kendi metni.')).toBeVisible();
    expect(screen.getByText('unknown_metric').nextElementSibling).toHaveTextContent('7');
  });
});
