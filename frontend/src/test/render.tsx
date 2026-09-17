import { render } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { LanguageProvider } from '../i18n';
import type { Language } from '../i18n/messages';

/** Dil saglayicisi altinda render eder; varsayilan Turkce, jsdom'un diline bagli degil. */
export function renderWithLanguage(ui: ReactElement, language: Language = 'tr') {
  return render(<LanguageProvider initial={language}>{ui}</LanguageProvider>);
}

export function withLanguage(children: ReactNode, language: Language = 'tr') {
  return <LanguageProvider initial={language}>{children}</LanguageProvider>;
}
