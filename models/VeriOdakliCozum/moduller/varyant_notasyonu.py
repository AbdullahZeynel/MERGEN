"""
Varyant Notasyonu (HGVSp) Ayrıştırma
=====================================

Protein değişim ifadesini (WT, pozisyon, MUT) üçlüsüne çevirir. Modül
bilinçli olarak bağımlılıksızdır: hem eğitim ön işlemesi (``on_isleme``) hem
canlı çıkarım adaptörü (``cikarim``) aynı tanımı kullanır, ama çıkarım yolu
pandas ve requests yüklemek zorunda kalmaz.

Tanım ``on_isleme.py`` içinden değiştirilmeden taşındı.
"""

from __future__ import annotations

import re

from .. import config


# HGVSp_Short formatı (örn. "p.R132H"); referans-konum-mutant
HGVSP_DESEN = re.compile(r"^p\.([A-Z])(\d+)([A-Z])$")

# 3-harfli kodları 1-harfliye eşle (HGVSp_Long destek için)
UCLU_TO_TEKLI = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Glu": "E", "Gln": "Q", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}


# ---------------------------------------------------------------------------
# Protein değişim parser'ı
# ---------------------------------------------------------------------------
def hgvsp_ayristir(degisim: str) -> tuple[str, int, str] | None:
    """
    'p.R132H' veya 'p.Arg132His' biçimini (WT, pozisyon, MUT) tuple'ına ayırır.

    Returns
    -------
    tuple[str, int, str] | None
        Standart amino asitler dışı (örn. Ter, dup) durumlarda ``None``.
    """
    if not isinstance(degisim, str):
        return None

    m = HGVSP_DESEN.match(degisim)
    if m:
        wt, poz, mut = m.group(1), int(m.group(2)), m.group(3)
        if wt in config.STANDART_AA and mut in config.STANDART_AA:
            return wt, poz, mut
        return None

    # 3-harfli format
    m3 = re.match(r"^p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$", degisim)
    if m3:
        wt3, poz, mut3 = m3.group(1), int(m3.group(2)), m3.group(3)
        wt = UCLU_TO_TEKLI.get(wt3)
        mut = UCLU_TO_TEKLI.get(mut3)
        if wt and mut:
            return wt, poz, mut
    return None
