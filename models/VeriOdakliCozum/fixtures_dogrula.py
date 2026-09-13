"""
Fixture dizilerini kaynağıyla karşılaştırır.

`fixtures/*.fasta` dosyaları bu depoya bir kez alınır ve SHA-256'larıyla
kayıtlıdır. Bu betik dizileri UniProt'tan yeniden indirip birebir aynı olup
olmadığını söyler. Ağ yoksa açık şekilde atlar; sessizce "geçti" demez.

    python -m VeriOdakliCozum.fixtures_dogrula
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import config

FIXTURE_DIZINI = config.PROJE_KOKU / "fixtures"
VARYANT_KATALOGU = FIXTURE_DIZINI / "varyantlar.json"


def dizi_oku(yol: Path) -> str:
    return "".join(s.strip() for s in yol.read_text(encoding="utf-8").splitlines()
                   if s.strip() and not s.startswith(">"))


def yerel_kontrol() -> list[str]:
    """Ağ gerektirmez: uzunluk, vahşi tip harfi ve checksum tutuyor mu?"""
    katalog = json.loads(VARYANT_KATALOGU.read_text(encoding="utf-8"))
    hatalar: list[str] = []
    for kayit in katalog["variants"]:
        k = kayit["kaynak"]
        yol = FIXTURE_DIZINI / k["dosya"]
        if not yol.is_file():
            hatalar.append(f"{kayit['caseId']}: {k['dosya']} yok")
            continue
        dizi = dizi_oku(yol)
        if len(dizi) != k["uzunluk"]:
            hatalar.append(f"{kayit['caseId']}: uzunluk {len(dizi)} != {k['uzunluk']}")
        poz = k["vahsiTipPozisyon"]
        if not 1 <= poz <= len(dizi) or dizi[poz - 1] != k["vahsiTipAmino"]:
            hatalar.append(f"{kayit['caseId']}: {poz}. pozisyon {k['vahsiTipAmino']} değil")
        if hashlib.sha256(dizi.encode()).hexdigest() != k["diziSha256"]:
            hatalar.append(f"{kayit['caseId']}: dizi sha256 uyuşmuyor")
        if hashlib.sha256(yol.read_bytes()).hexdigest() != k["dosyaSha256"]:
            hatalar.append(f"{kayit['caseId']}: dosya sha256 uyuşmuyor")
    return hatalar


def kaynak_kontrol() -> tuple[list[str], list[str]]:
    """UniProt'tan indirip karşılaştırır. (hatalar, atlananlar) döner."""
    import urllib.error
    import urllib.request

    katalog = json.loads(VARYANT_KATALOGU.read_text(encoding="utf-8"))
    hatalar: list[str] = []
    atlanan: list[str] = []
    gorulen: dict[str, str] = {}
    for kayit in katalog["variants"]:
        k = kayit["kaynak"]
        if k["dosya"] in gorulen:
            continue
        gorulen[k["dosya"]] = "denendi"
        try:
            with urllib.request.urlopen(k["url"], timeout=30) as yanit:
                uzak = yanit.read().decode()
        except (urllib.error.URLError, OSError) as exc:
            atlanan.append(f"{k['dosya']}: indirilemedi ({type(exc).__name__})")
            continue
        uzak_dizi = "".join(s.strip() for s in uzak.splitlines()
                            if s.strip() and not s.startswith(">"))
        yerel_dizi = dizi_oku(FIXTURE_DIZINI / k["dosya"])
        if uzak_dizi != yerel_dizi:
            hatalar.append(
                f"{k['dosya']}: UniProt ile fark var "
                f"(yerel {len(yerel_dizi)} aa, uzak {len(uzak_dizi)} aa)"
            )
    return hatalar, atlanan


def main() -> int:
    hatalar = yerel_kontrol()
    print("Yerel kontrol:", "temiz" if not hatalar else f"{len(hatalar)} hata")
    for h in hatalar:
        print("  ", h)

    uzak_hata, atlanan = kaynak_kontrol()
    if atlanan:
        print("Kaynak kontrolü ATLANDI (ağ yok):")
        for a in atlanan:
            print("  ", a)
        print("   Ağı olan bir makinede tekrar çalıştırın; bu kontrol geçmiş sayılmaz.")
    else:
        print("Kaynak kontrolü:", "temiz" if not uzak_hata else f"{len(uzak_hata)} hata")
    for h in uzak_hata:
        print("  ", h)
    return 1 if (hatalar or uzak_hata) else 0


if __name__ == "__main__":
    raise SystemExit(main())
