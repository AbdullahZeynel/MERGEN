import { useMemo } from 'react';
import { useLanguage } from './i18n';

/** Sayilar ekranda arayuz diliyle yazilir: 0,790 ile 0.790 ayni sayi degil gibi okunur. */
export function useFormat() {
  const { language } = useLanguage();
  return useMemo(
    () => ({
      score: (value: number, digits = 3) =>
        new Intl.NumberFormat(language, {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        }).format(value),
      percent: (value: number) =>
        new Intl.NumberFormat(language, { style: 'percent', maximumFractionDigits: 1 }).format(value),
      count: (value: number) => new Intl.NumberFormat(language).format(value),
    }),
    [language],
  );
}
