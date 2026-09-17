import { describe, expect, it } from 'vitest';
import { dictionaries, en, tr, type MessageKey } from '../i18n/messages';
import { translate } from '../i18n';

const placeholders = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();

describe('interface dictionaries', () => {
  it('cover the same keys in both languages', () => {
    // `en` tipi zaten Record<MessageKey, string>; bu kontrol fazlaligi degil:
    // fazladan bir anahtarin sessizce kalmasini da engeller.
    expect(Object.keys(en).sort()).toEqual(Object.keys(tr).sort());
  });

  it('carry the same placeholders in every translation', () => {
    // Cevirisinde {count} dusen bir dizge ekranda sessizce yanlis okunur.
    for (const key of Object.keys(tr) as MessageKey[]) {
      expect(placeholders(en[key]), key).toEqual(placeholders(tr[key]));
    }
  });

  it('leave no message empty', () => {
    for (const [language, dictionary] of Object.entries(dictionaries)) {
      for (const [key, value] of Object.entries(dictionary)) {
        expect(value.trim(), `${language}:${key}`).not.toBe('');
      }
    }
  });

  it('fills placeholders and keeps an unknown one visible', () => {
    expect(translate('tr', 'viewer.sliceOf', { index: 3, count: 155 })).toBe('Kesit 3 / 155');
    expect(translate('en', 'viewer.sliceOf', { index: 3, count: 155 })).toBe('Slice 3 of 155');
    // Eksik degisken sessizce bosluga donusmez; yer tutucu gorunur kalir.
    expect(translate('en', 'viewer.sliceOf', { index: 3 })).toContain('{count}');
  });
});
