import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { dictionaries, type Language, type MessageKey } from './messages';

const STORAGE_KEY = 'mergen-language';
export type Translate = (key: MessageKey, values?: Record<string, string | number>) => string;

function isLanguage(value: unknown): value is Language {
  return value === 'tr' || value === 'en';
}

export function initialLanguage(): Language {
  // Kayitli secim varsa o. Yoksa Turkce: hedef kitle Turkce ve yabanci dilli
  // bir tarayicida acilan sayfa yanlislikla Ingilizce baslamamali.
  const saved = window.localStorage?.getItem(STORAGE_KEY);
  return isLanguage(saved) ? saved : 'tr';
}

/** `{ad}` yer tutucularini doldurur; eksik anahtar yerine anahtarin kendisi. */
export function translate(
  language: Language,
  key: MessageKey,
  values?: Record<string, string | number>,
): string {
  const text = dictionaries[language][key] ?? key;
  if (!values) return text;
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}

interface LanguageValue {
  language: Language;
  setLanguage: (next: Language) => void;
  t: Translate;
}

const LanguageContext = createContext<LanguageValue | null>(null);

export function LanguageProvider({
  children,
  initial,
}: {
  children: ReactNode;
  // Testler ve ileride sunucu tarafi render icin: verilmezse kayitli secim,
  // sonra tarayici dili belirler.
  initial?: Language;
}) {
  const [language, setLanguage] = useState<Language>(() => initial ?? initialLanguage());
  useEffect(() => {
    document.documentElement.lang = language;
    document.title = translate(language, 'app.title');
    document
      .querySelector('meta[name="description"]')
      ?.setAttribute('content', translate(language, 'app.description'));
    window.localStorage?.setItem(STORAGE_KEY, language);
  }, [language]);
  const t = useCallback<Translate>((key, values) => translate(language, key, values), [language]);
  const value = useMemo(() => ({ language, setLanguage, t }), [language, t]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageValue {
  const value = useContext(LanguageContext);
  if (!value) throw new Error('LanguageProvider is missing');
  return value;
}

export function useT(): Translate {
  return useLanguage().t;
}

export type { Language, MessageKey };
