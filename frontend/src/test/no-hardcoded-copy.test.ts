import { describe, expect, it } from 'vitest';

// Vite'in kendi mekanizmasi: node tipleri ve yeni bir bagimlilik gerekmiyor.
// Sozluk, testler ve dogrulama semalari disarida: oradaki metin ya sozlugun
// kendisi ya da kullaniciya cikmayan gelistirici mesaji.
const sources = import.meta.glob('../{*.tsx,components/**/*.tsx}', {
  query: '?raw',
  eager: true,
  import: 'default',
}) as Record<string, string>;

// Satir ici yorumlar Turkce olabilir; bakilan sey yalnizca dizgeler ve JSX metni.
const withoutComments = (source: string) =>
  source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

const TURKISH = /[çğıöşüÇĞİÖŞÜ]/;

describe('component copy', () => {
  it('is covered by the glob at all', () => {
    // Glob bosalirsa test sessizce her zaman gecer; once onu kanitla.
    expect(Object.keys(sources).length).toBeGreaterThan(5);
  });

  it('lives in the dictionary, not in the components', () => {
    // Bir bilesene dogrudan yazilan Turkce metin, dil degistiginde oldugu yerde
    // kalir ve arayuz yari Turkce olur. Asistan panelinde tam bu olmustu.
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(sources)) {
      withoutComments(source)
        .split('\n')
        .forEach((text, index) => {
          if (TURKISH.test(text)) offenders.push(`${path}:${index + 1}`);
        });
    }
    expect(offenders).toEqual([]);
  });
});
