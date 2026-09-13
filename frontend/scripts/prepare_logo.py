"""Takim logosunu ray isaretine ve favicon'a donusturur.

Kaynak (`Sosyal Medya PP 3 (2).png`) Git disindadir: siyah zemin uzerine beyaz
kartal cizimi, alfa kanali yok. Parlaklik kanalini alfaya tasiyip RGB'yi beyaza sabitleriz;
kenar yumusatmasi korunur ve isaret lacivert ray uzerinde temiz durur.

    python frontend/scripts/prepare_logo.py "$HOME/Assets/Sosyal Medya PP 3 (2).png"

Pillow gerekir (frontend/scripts/requirements-demo.txt icinde).
"""

import pathlib
import sys

from PIL import Image, ImageDraw, ImageOps

ESIK = 12  # Siyah zemini ayirmak icin parlaklik esigi.
ISARET_GENISLIK = 192  # Rayda 46px gosterilir; yuksek DPI icin dort kat.
FAVICON_KENAR = 64
FAVICON_BOSLUK = 4
BENIMSEME_KENAR = 240  # README rozeti; GitHub'da 110px gosterilir.
BENIMSEME_BOSLUK = 34
BENIMSEME_YARICAP = 52
LACIVERT = (17, 26, 44, 255)  # --navy


def isareti_uret(kaynak: pathlib.Path) -> Image.Image:
    parlaklik = ImageOps.grayscale(Image.open(kaynak).convert('RGB'))
    kutu = parlaklik.point(lambda v: 255 if v > ESIK else 0).getbbox()
    if kutu is None:
        raise SystemExit(f'Kaynakta cizim bulunamadi: {kaynak}')
    alfa = parlaklik.crop(kutu)
    beyaz = Image.new('L', alfa.size, 255)
    isaret = Image.merge('RGBA', (beyaz, beyaz, beyaz, alfa))
    yukseklik = round(ISARET_GENISLIK * alfa.height / alfa.width)
    return isaret.resize((ISARET_GENISLIK, yukseklik), Image.LANCZOS)


def favicon_uret(isaret: Image.Image) -> Image.Image:
    # Sekme arka plani acik da olabilir koyu da; lacivert zemin ikisinde de okunur.
    ikon = Image.new('RGBA', (FAVICON_KENAR, FAVICON_KENAR), LACIVERT)
    # Isaret genise yatik; kare ikonda genislige gore olceklenir.
    kenar = FAVICON_KENAR - 2 * FAVICON_BOSLUK
    icerik = isaret.resize((kenar, round(kenar * isaret.height / isaret.width)), Image.LANCZOS)
    ikon.paste(
        icerik,
        ((FAVICON_KENAR - icerik.width) // 2, (FAVICON_KENAR - icerik.height) // 2),
        icerik,
    )
    return ikon


def readme_rozeti(isaret: Image.Image) -> Image.Image:
    """Beyaz cizim seffaf PNG olarak README'nin acik zemininde gorunmez;
    bu yuzden koseleri yuvarlatilmis lacivert bir plaka uzerine basiyoruz."""
    kenar = BENIMSEME_KENAR
    plaka = Image.new('RGBA', (kenar, kenar), (0, 0, 0, 0))
    ImageDraw.Draw(plaka).rounded_rectangle(
        (0, 0, kenar - 1, kenar - 1), radius=BENIMSEME_YARICAP, fill=LACIVERT
    )
    ic = kenar - 2 * BENIMSEME_BOSLUK
    icerik = isaret.resize((ic, round(ic * isaret.height / isaret.width)), Image.LANCZOS)
    plaka.paste(icerik, ((kenar - icerik.width) // 2, (kenar - icerik.height) // 2), icerik)
    return plaka


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    hedef = pathlib.Path(__file__).resolve().parent.parent / 'public'
    kok = pathlib.Path(__file__).resolve().parent.parent.parent
    isaret = isareti_uret(pathlib.Path(sys.argv[1]))
    isaret.save(hedef / 'ergenekon-logo.png', optimize=True)
    favicon_uret(isaret).save(hedef / 'favicon.png', optimize=True)
    rozet = kok / 'docs' / 'images' / 'logo.png'
    rozet.parent.mkdir(parents=True, exist_ok=True)
    readme_rozeti(isaret).save(rozet, optimize=True)
    print(f'ergenekon-logo.png {isaret.width}x{isaret.height}, '
          f'favicon.png {FAVICON_KENAR}px, docs/images/logo.png {BENIMSEME_KENAR}px')


if __name__ == '__main__':
    main()
