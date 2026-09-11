#!/usr/bin/env python3
"""
Klasör düzenleyici — macOS'tan gelen zip artıklarını temizler.

Ne yapar:
  * __MACOSX klasörlerini, ._* resource fork dosyalarını ve .DS_Store'ları siler
  * 'X.txt/X.txt' biçiminde iç içe kalmış dosyaları bir üst dizine taşır
  * __pycache__ klasörlerini temizler

Önce ne yapacağını gösterir:
    python duzenle.py            # sadece rapor (hiçbir şey silinmez)
    python duzenle.py --uygula   # gerçekten uygula
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
ATLA = {".venv", ".git"}
COP_ADLAR = {".DS_Store", "__MACOSX", "__pycache__", ".Spotlight-V100", ".Trashes"}


def gezinilecek(kok: Path):
    for dizin, alt_dizinler, dosyalar in os.walk(kok):
        alt_dizinler[:] = [d for d in alt_dizinler if d not in ATLA]
        yield Path(dizin), list(alt_dizinler), dosyalar


def cop_topla():
    silinecek = []
    for dizin, alt_dizinler, dosyalar in gezinilecek(KOK):
        for d in alt_dizinler:
            if d in COP_ADLAR:
                silinecek.append(dizin / d)
        for f in dosyalar:
            if f in COP_ADLAR or f.startswith("._"):
                silinecek.append(dizin / f)
    return silinecek


def icice_topla():
    """veri/X.txt/X.txt → veri/X.txt olacak adayları bulur."""
    tasinacak = []
    veri = KOK / "veri"
    if not veri.is_dir():
        return tasinacak
    for alt in sorted(veri.iterdir()):
        if not alt.is_dir() or alt.name in ATLA | COP_ADLAR:
            continue
        ic = alt / alt.name
        if ic.is_file():
            tasinacak.append((ic, alt))
    return tasinacak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uygula", action="store_true",
                    help="değişiklikleri gerçekten uygula (varsayılan: sadece raporla)")
    args = ap.parse_args()

    cop = cop_topla()
    icice = icice_topla()

    print(f"Kök: {KOK}\n")
    print(f"Silinecek artık: {len(cop)}")
    for p in cop[:20]:
        print(f"   - {p.relative_to(KOK)}")
    if len(cop) > 20:
        print(f"   … ve {len(cop) - 20} tane daha")

    print(f"\nDüzleştirilecek iç içe dosya: {len(icice)}")
    for ic, kapsayici in icice:
        print(f"   {kapsayici.relative_to(KOK)}/{ic.name}  ->  {kapsayici.relative_to(KOK)}")

    if not args.uygula:
        print("\n(Deneme modu — hiçbir şey değişmedi. Uygulamak için: python duzenle.py --uygula)")
        return 0

    for p in cop:
        if not p.exists():
            continue          # üst klasörüyle birlikte zaten gitmiş
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        except OSError as exc:
            print(f"   silinemedi: {p} ({exc})", file=sys.stderr)

    for ic, kapsayici in icice:
        gecici = kapsayici.with_name(kapsayici.name + ".__tasiniyor__")
        try:
            shutil.move(str(ic), str(gecici))       # dosyayı geçici ada al
            shutil.rmtree(kapsayici)                # boşalan klasörü sil
            gecici.rename(kapsayici)                # dosyayı klasörün adıyla koy
            print(f"   düzleştirildi: {kapsayici.relative_to(KOK)}")
        except OSError as exc:
            print(f"   taşınamadı: {ic} ({exc})", file=sys.stderr)

    print("\nTamam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
