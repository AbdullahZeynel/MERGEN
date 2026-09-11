"""
Ön İşleme Modülü
=================

Birleştirilmiş veri tablosunun temizliği, etiket normalizasyonu,
protein değişim ifadelerinin (HGVSp) ayrıştırılması ve UniProt'tan
referans dizilim çekme görevlerini üstlenir.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

import pandas as pd
import requests

from .. import config

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MC3 SIFT/PolyPhen string parser'ı
# ---------------------------------------------------------------------------
def _vep_skor_ayikla(metin: str) -> tuple[str | None, float | None]:
    """
    MC3'ün VEP-anotasyonlu SIFT/PolyPhen string'ini parse eder.

    Örnekler:
        "deleterious(0.01)"            → ("deleterious", 0.01)
        "tolerated_low_confidence(0.49)" → ("tolerated_low_confidence", 0.49)
        "probably_damaging(0.999)"     → ("probably_damaging", 0.999)
        ""                              → (None, None)
    """
    if not isinstance(metin, str) or metin in ("", ".", "nan"):
        return None, None
    m = re.match(r"^([a-zA-Z_]+)\(([\d.]+)\)$", metin.strip())
    if m:
        try:
            return m.group(1), float(m.group(2))
        except ValueError:
            return m.group(1), None
    return metin.strip(), None

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


# ---------------------------------------------------------------------------
# Etiket normalizasyonu
# ---------------------------------------------------------------------------
def ikili_etiket_uret(klinik_anlam: str) -> int | None:
    """
    ClinVar / CIVIC klinik anlam metnini ikili etikete dönüştürür.

    * 1 ⇒ Patojenik (Pathogenic / Likely pathogenic)
    * 0 ⇒ Benign (Benign / Likely benign)
    * None ⇒ Belirsiz (Uncertain significance vb.) — eğitim setinden çıkarılır
    """
    if not isinstance(klinik_anlam, str):
        return None
    metin = klinik_anlam.strip()
    if any(p.lower() in metin.lower() for p in config.PATOJENIK_ETIKETLER):
        return 1
    if any(b.lower() in metin.lower() for b in config.BENIGN_ETIKETLER):
        return 0
    return None


# ---------------------------------------------------------------------------
# UniProt referans dizilim çekme
# ---------------------------------------------------------------------------
@lru_cache(maxsize=256)
def uniprot_dizilim_cek(gen_sembol: str) -> str | None:
    """
    Bir gen sembolü için UniProt'tan kanonik insan protein dizilimi çeker.
    Sonuç önbelleğe alınır (LRU); kapalı çalışmalarda her gen bir kez sorgulanır.
    """
    try:
        yanit = requests.get(
            config.UNIPROT_API,
            params={
                "query": f"gene:{gen_sembol} AND organism_id:9606 AND reviewed:true",
                "format": "tsv",
                "fields": "accession,sequence,length",
                "size": 1,
            },
            headers={"User-Agent": "MERGEN-Pipeline/1.0"},
            timeout=30,
        )
        yanit.raise_for_status()
        satirlar = yanit.text.strip().splitlines()
        if len(satirlar) >= 2:
            _, dizilim, *_ = satirlar[1].split("\t")
            return dizilim
    except Exception as exc:
        LOG.debug("UniProt çekme hatası %s: %s", gen_sembol, exc)
    return None


# ---------------------------------------------------------------------------
# Üst seviye ön işleme
# ---------------------------------------------------------------------------
def veriyi_hazirla(ham: pd.DataFrame) -> pd.DataFrame:
    """
    Ham birleştirilmiş tabloyu modelleme için hazırlar:

    1. HGVSp parser'ından geçirir (yt_aa, mut_aa, pozisyon kolonları)
    2. Belirsiz klinik anlamlı varyantları atar
    3. UniProt'tan her gen için kanonik dizilimi çeker
    4. Eksik dizilim/parse durumlarını filtreler
    """
    df = ham.copy()

    parse = df["protein_degisim"].apply(hgvsp_ayristir)
    df["wt_aa"] = parse.apply(lambda x: x[0] if x else None)
    df["pozisyon_aa"] = parse.apply(lambda x: x[1] if x else None)
    df["mut_aa"] = parse.apply(lambda x: x[2] if x else None)
    df = df.dropna(subset=["wt_aa", "mut_aa", "pozisyon_aa"]).copy()
    df["pozisyon_aa"] = df["pozisyon_aa"].astype(int)

    df["etiket"] = df["klinik_anlam"].apply(ikili_etiket_uret)
    df = df.dropna(subset=["etiket"]).copy()
    df["etiket"] = df["etiket"].astype(int)

    LOG.info("Etiketleme sonrası boyut: %d (Patojenik=%d, Benign=%d)",
             len(df), int(df["etiket"].sum()), int((df["etiket"] == 0).sum()))

    # UniProt dizilimlerini ekle — başarısız olanlar referans diziye 'X' atanır
    genler = df["gen"].dropna().unique().tolist()
    dizilim_map: dict[str, str] = {}
    for g in genler:
        s = uniprot_dizilim_cek(g)
        if s:
            dizilim_map[g] = s
    df["protein_dizilim"] = df["gen"].map(dizilim_map)

    # Çekilemeyen genler için minimal sentetik kontekst (mutasyon dolayında ±20 'X')
    eksik = df["protein_dizilim"].isna()
    if eksik.any():
        LOG.warning("Dizilim çekilemeyen varyant sayısı: %d (sentetik kontekst kullanılacak)",
                    int(eksik.sum()))
    df.loc[eksik, "protein_dizilim"] = df.loc[eksik].apply(
        lambda r: ("X" * (r["pozisyon_aa"] - 1)) + r["wt_aa"] + ("X" * 50), axis=1
    )

    # WT amino asidin diziye uyduğunu doğrula; uymuyorsa pozisyonu güncelle
    def _wt_dogrula(r: pd.Series) -> bool:
        idx = int(r["pozisyon_aa"]) - 1
        s = r["protein_dizilim"]
        return 0 <= idx < len(s) and (s[idx] == r["wt_aa"] or s[idx] == "X")

    gecerli = df.apply(_wt_dogrula, axis=1)
    if (~gecerli).any():
        LOG.info("WT-dizilim uyuşmazlığı olan %d kayıt çıkarıldı.", int((~gecerli).sum()))
    df = df[gecerli].reset_index(drop=True)

    # MC3'ün gömülü SIFT / PolyPhen skorlarını parse et (varsa)
    if "SIFT" in df.columns:
        ayri = df["SIFT"].astype(str).apply(_vep_skor_ayikla)
        df["sift_skor"] = ayri.apply(lambda x: x[1])
    if "PolyPhen" in df.columns:
        ayri = df["PolyPhen"].astype(str).apply(_vep_skor_ayikla)
        df["polyphen_skor"] = ayri.apply(lambda x: x[1])

    LOG.info("Ön işlemeden geçen son satır sayısı: %d", len(df))
    return df
