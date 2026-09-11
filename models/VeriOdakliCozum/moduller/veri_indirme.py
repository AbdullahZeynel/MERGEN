"""
Veri İndirme Modülü
====================

TCGA (GDC), ClinVar, CIVIC ve COSMIC kaynaklarından glioma somatik
missense varyantlarını çeker, normalize eder ve ortak bir
:class:`pandas.DataFrame` hâline getirir.

Mimari notlar:
    * TCGA verileri **GDC REST API** üzerinden açık MAF dosyaları olarak
      indirilir (kimlik doğrulama gerekmez — sadece "open access" dosyalar).
    * ClinVar somatik varyantlar **NCBI E-utilities** ile aranır.
    * CIVIC kanıtları açık REST endpoint üzerinden çekilir.
    * COSMIC kapalı erişimlidir; kullanıcı yerel TSV sağladığında entegre olur,
      aksi hâlde sentetik popülasyon frekansı üretilir.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from .. import config

LOG = logging.getLogger(__name__)

ISTEK_BASLIK = {"User-Agent": "MERGEN-Pipeline/1.0 (TEKNOFEST-2026)"}
ISTEK_ZAMAN_ASIMI = 60

# ---------------------------------------------------------------------------
# Protein değişim gösterimini tek biçime indirgeme
# ---------------------------------------------------------------------------
# ClinVar "p.Arg132His" (3 harf), MAF ise "p.R132H" (1 harf) yazıyor. Etiket
# birleştirmesi ham metin üzerinden yapıldığı için ikisi hiçbir zaman
# eşleşmiyordu; birleştirmeden önce her iki taraf da bu biçime indirgeniyor.
_UCLU_TO_TEKLI = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Glu": "E", "Gln": "Q", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}
_UCLU_DESEN = re.compile(r"^p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$")
_TEKLI_DESEN = re.compile(r"^p\.([A-Z])(\d+)([A-Z])$")


def protein_degisim_normalize(degisim) -> str | None:
    """'p.Arg132His' ve 'p.R132H' → 'p.R132H'. Tanınmayan biçimde None."""
    if not isinstance(degisim, str):
        return None
    d = degisim.strip()
    if _TEKLI_DESEN.match(d):
        return d
    m = _UCLU_DESEN.match(d)
    if m:
        wt = _UCLU_TO_TEKLI.get(m.group(1))
        mut = _UCLU_TO_TEKLI.get(m.group(3))
        if wt and mut:
            return f"p.{wt}{m.group(2)}{mut}"
    return None


# ---------------------------------------------------------------------------
# TCGA — GDC API
# ---------------------------------------------------------------------------
def _gdc_maf_dosya_listesi(proje: str, limit: int | None = None) -> list[dict]:
    """Belirtilen TCGA projesinin açık MAF dosyalarını listeler."""
    limit = limit or config.GDC_MAF_DOSYA_SAYISI
    filtreler = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": [proje]}},
            {"op": "in", "content": {"field": "data_format", "value": ["MAF"]}},
            {"op": "in", "content": {"field": "access", "value": ["open"]}},
            {"op": "in", "content": {"field": "experimental_strategy", "value": ["WXS"]}},
        ],
    }
    params = {
        "filters": json.dumps(filtreler),
        "fields": "file_id,file_name,data_format,access",
        "format": "JSON",
        "size": str(limit),
    }
    yanit = requests.get(
        config.GDC_FILES_ENDPOINT, params=params,
        headers=ISTEK_BASLIK, timeout=ISTEK_ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    return yanit.json().get("data", {}).get("hits", [])


def _gdc_maf_indir(dosya_id: str, onbellek: Path) -> pd.DataFrame:
    """Tek bir MAF dosyasını indirir ve DataFrame'e dönüştürür."""
    onbellek_yolu = onbellek / f"{dosya_id}.maf.gz"
    if not onbellek_yolu.exists():
        url = f"{config.GDC_DATA_ENDPOINT}/{dosya_id}"
        yanit = requests.get(url, headers=ISTEK_BASLIK, timeout=ISTEK_ZAMAN_ASIMI, stream=True)
        yanit.raise_for_status()
        onbellek_yolu.write_bytes(yanit.content)

    ham = onbellek_yolu.read_bytes()
    # MAF dosyaları "#version" yorum satırlarıyla başlar
    if ham[:2] == b"\x1f\x8b":
        ham = gzip.decompress(ham)
    metin = ham.decode("utf-8", errors="ignore")

    yorum_disi = "\n".join(s for s in metin.splitlines() if not s.startswith("#"))
    return pd.read_csv(io.StringIO(yorum_disi), sep="\t", low_memory=False)


def tcga_missense_indir(projeler: Iterable[str] | None = None) -> pd.DataFrame:
    """
    TCGA-GBM ve TCGA-LGG için missense varyantları getirir.

    Öncelik sırası:
        1. Yerel MC3 PUBLIC MAF (varsa, hızlı ve kapsamlı)
        2. GDC API (canlı indirme)
        3. Demo veri (her ikisi de başarısızsa)
    """
    if config.MC3_YEREL_MAF.exists():
        LOG.info("Yerel MC3 PUBLIC MAF tespit edildi — okunuyor.")
        return mc3_yerel_oku(config.MC3_YEREL_MAF)

    projeler = list(projeler or config.TCGA_PROJELERI)
    birikim: list[pd.DataFrame] = []

    for proje in projeler:
        LOG.info("TCGA projesi indiriliyor: %s", proje)
        try:
            dosyalar = _gdc_maf_dosya_listesi(proje)
            for hit in dosyalar:
                try:
                    df = _gdc_maf_indir(hit["file_id"], config.ONBELLEK_DIZINI)
                except Exception as exc:
                    LOG.warning("MAF indirme hatası (%s): %s", hit["file_id"], exc)
                    continue
                df["proje"] = proje
                birikim.append(df)
                time.sleep(0.2)
        except Exception as exc:
            LOG.warning("GDC API erişilemedi (%s): %s", proje, exc)

    if not birikim:
        LOG.warning("Canlı TCGA verisi indirilemedi — demo MAF üretiliyor.")
        return _demo_tcga_maf_uret()

    maf = pd.concat(birikim, ignore_index=True)
    missense = maf[maf["Variant_Classification"] == config.HEDEF_MUTASYON_TIPI].copy()
    LOG.info("TCGA missense kayıt sayısı: %d", len(missense))
    return _maf_normalize(missense)


# ---------------------------------------------------------------------------
# Yerel MC3 PUBLIC MAF okuyucusu
# ---------------------------------------------------------------------------
def mc3_yerel_oku(yol: Path) -> pd.DataFrame:
    """
    PanCanAtlas MC3 PUBLIC MAF dosyasını okuyup TCGA-GBM ve TCGA-LGG
    missense varyantlarını süzer.

    MC3 zaten VEP ile zenginleştirilmiş olduğundan SIFT, PolyPhen, CLIN_SIG,
    COSMIC, ExAC frekansları gibi anotasyonlar kolonlarda hazır gelir.
    Bu sayede ayrı API çağrısına gerek kalmaz.
    """
    kullanilacak_kolonlar = [
        "Hugo_Symbol", "Variant_Classification", "Variant_Type",
        "Chromosome", "Start_Position", "Reference_Allele", "Tumor_Seq_Allele2",
        "Tumor_Sample_Barcode", "HGVSp_Short", "Transcript_ID",
        "SWISSPROT", "Protein_position", "Amino_acids", "SIFT", "PolyPhen",
        "IMPACT", "CLIN_SIG", "COSMIC", "ExAC_AF", "FILTER",
    ]

    # Dosya .gz olarak da açılmış hâlde de gelebiliyor; uzantıdan anla.
    LOG.info("MC3 MAF okunuyor (%s) — kolon süzgeci uygulanıyor…", yol.name)
    df = pd.read_csv(
        yol, sep="\t", compression="infer", low_memory=False,
        comment=None, usecols=lambda c: c in kullanilacak_kolonlar,
        dtype=str,
    )
    LOG.info("MC3 ham satır sayısı: %d", len(df))

    # Önce sadece missense süz
    missense = df[df["Variant_Classification"] == config.HEDEF_MUTASYON_TIPI].copy()
    if "FILTER" in missense.columns:
        missense = missense[
            missense["FILTER"].isin(["PASS", "", "."]) | missense["FILTER"].isna()
        ]
    LOG.info("Tüm TCGA missense (PASS): %d", len(missense))

    # Kohort etiketi (TSS koduyla)
    missense["tss"] = missense["Tumor_Sample_Barcode"].str[5:7]
    missense["kohort"] = missense["tss"].map(
        lambda t: "TCGA-GBM" if t in config.TCGA_GBM_TSS
        else ("TCGA-LGG" if t in config.TCGA_LGG_TSS else "TCGA-DIGER")
    )

    # CLIN_SIG'den etiket çıkar (tüm TCGA üzerinde)
    cs = missense["CLIN_SIG"].fillna("").str.lower()
    is_path_kat = cs.str.contains("pathogenic", regex=False) \
        & ~cs.str.contains("non_pathogenic", regex=False)
    is_benign_kat = cs.str.contains("benign", regex=False) \
        & ~cs.str.contains("non_benign", regex=False)

    # PATOJENIK: yalnızca glioma kohortundan (kohort-spesifik biyoloji)
    glioma_maske = missense["kohort"].isin(["TCGA-GBM", "TCGA-LGG"])
    patojenik = missense[is_path_kat & glioma_maske].copy()
    # BENIGN: tüm TCGA'dan (kohort-bağımsız polimorfizmler)
    benign = missense[is_benign_kat].copy()

    LOG.info("Patojenik (glioma): %d | Benign (tüm TCGA): %d",
             len(patojenik), len(benign))

    sonuc = pd.concat([patojenik, benign], ignore_index=True)
    return _mc3_normalize(sonuc)


def _mc3_normalize(maf: pd.DataFrame) -> pd.DataFrame:
    """MC3 kolonlarını pipeline standart şemasına indirger ve MC3 zenginliklerini
    iz kolonu olarak korur (sonra özellik çıkarımında kullanılabilir)."""
    yeniden = {
        "Hugo_Symbol": "gen",
        "HGVSp_Short": "protein_degisim",
        "Chromosome": "kromozom",
        "Start_Position": "pozisyon",
        "Reference_Allele": "ref_allel",
        "Tumor_Seq_Allele2": "mut_allel",
        "SWISSPROT": "uniprot_id",
    }
    mevcut = {k: v for k, v in yeniden.items() if k in maf.columns}
    df = maf.rename(columns=mevcut)

    df = df.dropna(subset=["gen", "protein_degisim"])
    df = df[df["protein_degisim"].astype(str).str.startswith("p.")]

    # MC3'ün zaten taşıdığı zenginlikleri sakla
    for k in ("SIFT", "PolyPhen", "CLIN_SIG", "COSMIC", "ExAC_AF", "IMPACT"):
        if k not in df.columns:
            df[k] = ""

    df["kaynak"] = "MC3"
    return df.reset_index(drop=True)


# GDC / MC3 MAF'larında popülasyon frekansı farklı adlarla gelebiliyor
AF_KOLON_ADAYLARI = ("ExAC_AF", "gnomAD_AF", "gnomAD_non_cancer_AF", "AF")

# VEP anotasyonları: etiketleme ve klasik araç karşılaştırması bunlara dayanıyor,
# bu yüzden normalize ederken korunmaları şart.
VEP_KOLONLARI = ("CLIN_SIG", "SIFT", "PolyPhen", "IMPACT", "COSMIC", "FILTER")


def _maf_normalize(maf: pd.DataFrame) -> pd.DataFrame:
    """
    MAF kolonlarını pipeline'a uygun standart şemaya indirger.

    GDC MAF'ları da VEP ile anote edilmiş geliyor (CLIN_SIG, SIFT, PolyPhen,
    gnomAD_AF…). Bunları atmak etiket üretimini imkânsız kılıyordu; artık
    MC3 ile aynı şemada taşınıyorlar.
    """
    seciliyor = {
        "Hugo_Symbol": "gen",
        "HGVSp_Short": "protein_degisim",
        "Chromosome": "kromozom",
        "Start_Position": "pozisyon",
        "Reference_Allele": "ref_allel",
        "Tumor_Seq_Allele2": "mut_allel",
        "SWISSPROT": "uniprot_id",
        "proje": "kohort",
    }
    mevcut = {k: v for k, v in seciliyor.items() if k in maf.columns}
    tasinacak = list(mevcut.keys()) + [k for k in VEP_KOLONLARI if k in maf.columns]
    # Popülasyon frekansı hangi adla geldiyse ExAC_AF'e taşı (aşağı akış bunu bekliyor)
    af_kolon = next((k for k in AF_KOLON_ADAYLARI if k in maf.columns), None)
    if af_kolon:
        tasinacak.append(af_kolon)

    df = maf[tasinacak].rename(columns=mevcut)
    if af_kolon:
        df = df.rename(columns={af_kolon: "ExAC_AF"})
    else:
        df["ExAC_AF"] = ""
    for k in VEP_KOLONLARI:
        if k not in df.columns:
            df[k] = ""

    df = df.dropna(subset=["gen", "protein_degisim"])
    df = df[df["protein_degisim"].astype(str).str.startswith("p.")]
    df["kaynak"] = "TCGA"
    return df.reset_index(drop=True)


def _demo_tcga_maf_uret() -> pd.DataFrame:
    """
    İnternet kısıtlı ortamlar için temsilî glioma varyantları üretir.
    Bu varyantlar gerçek glioma literatüründen seçilmiş bilinen mutasyonlardır.
    """
    veri = [
        ("IDH1", "p.R132H", "TCGA-LGG"),
        ("IDH1", "p.R132C", "TCGA-LGG"),
        ("IDH2", "p.R172K", "TCGA-LGG"),
        ("TP53", "p.R175H", "TCGA-GBM"),
        ("TP53", "p.R248Q", "TCGA-GBM"),
        ("TP53", "p.R273H", "TCGA-GBM"),
        ("ATRX", "p.R907C", "TCGA-LGG"),
        ("EGFR", "p.A289V", "TCGA-GBM"),
        ("EGFR", "p.G598V", "TCGA-GBM"),
        ("PTEN", "p.R130G", "TCGA-GBM"),
        ("PIK3CA", "p.E545K", "TCGA-GBM"),
        ("PIK3CA", "p.H1047R", "TCGA-GBM"),
        ("BRAF", "p.V600E", "TCGA-LGG"),
        ("NF1", "p.R1276Q", "TCGA-GBM"),
        ("CIC", "p.R215W", "TCGA-LGG"),
    ]
    df = pd.DataFrame(veri, columns=["gen", "protein_degisim", "kohort"])
    df["kaynak"] = "TCGA-demo"
    return df


# ---------------------------------------------------------------------------
# ClinVar — NCBI E-utilities (somatik etiketli)
# ---------------------------------------------------------------------------
def clinvar_etiket_cek(genler: Iterable[str]) -> pd.DataFrame:
    """
    NCBI E-utilities üzerinden somatik etiketli ClinVar varyantlarını çeker.

    Çıktı kolonları: gen, protein_degisim, klinik_anlam, kaynak
    """
    kayitlar: list[dict] = []
    for gen in genler:
        try:
            kayitlar.extend(_clinvar_gen_icin(gen))
            time.sleep(0.34)  # NCBI rate-limit (≤3 istek/sn)
        except Exception as exc:
            LOG.warning("ClinVar erişim hatası (%s): %s", gen, exc)

    if not kayitlar:
        LOG.warning("ClinVar boş döndü — demo etiketleri kullanılacak.")
        return _demo_clinvar_etiketleri()

    df = pd.DataFrame(kayitlar)
    df["kaynak"] = "ClinVar"
    return df


def _clinvar_gen_icin(gen: str, maks: int | None = None) -> list[dict]:
    """
    Tek gen için ClinVar varyantlarını döndürür.

    Not: eskiden sorguya ``somatic[origin]`` ekleniyordu. ClinVar kayıtlarının
    neredeyse tamamı germline köken etiketli olduğundan bu süzgeç her gen için
    boş sonuç döndürüyordu — pipeline da sessizce demo etiketlerine düşüyordu.
    Köken süzgeci kaldırıldı; sınıflandırma zaten esummary'den okunuyor.
    """
    maks = maks or config.CLINVAR_GEN_BASINA
    arama = requests.get(
        f"{config.CLINVAR_API}/esearch.fcgi",
        params={
            "db": "clinvar",
            "term": f"{gen}[gene] AND missense variant[molecular consequence]",
            "retmode": "json",
            "retmax": maks,
        },
        headers=ISTEK_BASLIK, timeout=ISTEK_ZAMAN_ASIMI,
    )
    arama.raise_for_status()
    idler = arama.json().get("esearchresult", {}).get("idlist", [])
    if not idler:
        return []

    sonuc: dict = {}
    for i in range(0, len(idler), 100):          # NCBI'yi tek istekte boğma
        parca = idler[i:i + 100]
        ozet = requests.get(
            f"{config.CLINVAR_API}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(parca), "retmode": "json"},
            headers=ISTEK_BASLIK, timeout=ISTEK_ZAMAN_ASIMI,
        )
        ozet.raise_for_status()
        sonuc.update(ozet.json().get("result", {}))
        time.sleep(0.34)

    cikti: list[dict] = []
    for vid in idler:
        kayit = sonuc.get(vid, {})
        kl_anl = (kayit.get("germline_classification", {}) or {}).get("description") \
                 or (kayit.get("clinical_significance", {}) or {}).get("description", "")
        protein_degisim = ""
        for varset in kayit.get("variation_set", []) or []:
            ad = varset.get("variation_name", "")
            if "p." in ad:
                protein_degisim = "p." + ad.split("p.")[1].split(")")[0]
                break
        if protein_degisim and kl_anl:
            cikti.append({
                "gen": gen,
                "protein_degisim": protein_degisim,
                "klinik_anlam": kl_anl,
            })
    return cikti


def _demo_clinvar_etiketleri() -> pd.DataFrame:
    """Demo ClinVar etiketleri (literatürden bilinen patojenik/benign varyantlar)."""
    veri = [
        ("IDH1", "p.R132H", "Pathogenic"),
        ("IDH1", "p.R132C", "Pathogenic"),
        ("IDH2", "p.R172K", "Pathogenic"),
        ("TP53", "p.R175H", "Pathogenic"),
        ("TP53", "p.R248Q", "Pathogenic"),
        ("TP53", "p.R273H", "Pathogenic"),
        ("TP53", "p.P72R", "Benign"),
        ("BRAF", "p.V600E", "Pathogenic"),
        ("PTEN", "p.R130G", "Pathogenic"),
        ("PIK3CA", "p.E545K", "Pathogenic"),
        ("PIK3CA", "p.H1047R", "Pathogenic"),
        ("EGFR", "p.A289V", "Pathogenic"),
        ("ATRX", "p.R907C", "Likely_pathogenic"),
        ("NF1", "p.R1276Q", "Pathogenic"),
        ("CIC", "p.R215W", "Likely_pathogenic"),
        # Yumuşatma için bazı benign örnekler (polimorfizmler)
        ("TP53", "p.R213R", "Benign"),
        ("EGFR", "p.R521K", "Benign"),
        ("PIK3CA", "p.I391M", "Benign"),
        ("PTEN", "p.D252G", "Likely_benign"),
        ("ATRX", "p.E929K", "Benign"),
    ]
    return pd.DataFrame(veri, columns=["gen", "protein_degisim", "klinik_anlam"]) \
        .assign(kaynak="ClinVar-demo")


# ---------------------------------------------------------------------------
# CIVIC — açık REST API
# ---------------------------------------------------------------------------
def civic_kanit_cek(genler: Iterable[str]) -> pd.DataFrame:
    """
    CIVIC veri tabanından gen başına klinik kanıtları çeker.

    CIVIC kanıt seviyelerini patojenik / benign etiketlerine eşler:
        * A, B, C ⇒ Pathogenic (klinik kanıt)
        * D, E    ⇒ Likely_pathogenic
    """
    birikim: list[dict] = []
    for gen in genler:
        try:
            yanit = requests.get(
                config.CIVIC_API,
                params={"entrez_symbol": gen, "count": 50},
                headers=ISTEK_BASLIK, timeout=ISTEK_ZAMAN_ASIMI,
            )
            if yanit.status_code != 200:
                continue
            for v in yanit.json().get("records", []):
                ad = v.get("name", "")
                if ad.startswith(("p.", "P.")) or any(c.isdigit() for c in ad):
                    birikim.append({
                        "gen": gen,
                        "protein_degisim": f"p.{ad}" if not ad.startswith("p.") else ad,
                        "klinik_anlam": "Pathogenic",
                        "kaynak": "CIVIC",
                    })
            time.sleep(0.2)
        except Exception as exc:
            LOG.debug("CIVIC erişim hatası (%s): %s", gen, exc)
    return pd.DataFrame(birikim)


# ---------------------------------------------------------------------------
# CGGA WESeq_286 — yerel mutasyon matrisi & klinik
# ---------------------------------------------------------------------------
def cgga_missense_frekansi_oku(
    mutasyon_yolu: Path = config.CGGA_MUTASYON_DOSYASI,
) -> pd.DataFrame:
    """
    CGGA WESeq_286 SAVI2 dosyasını gen × örnek matrisi olarak okur ve
    her gen için **Çin glioma kohortunda missense varyant taşıyan örnek oranını**
    döndürür. Bu sayı bağımsız bir popülasyon-frekansı özelliği olarak modele
    eklenebilir.

    Returns
    -------
    pd.DataFrame
        ``gen`` + ``cgga_missense_frekans`` (0-1 arası oran) + ``cgga_orneklem``
    """
    if not mutasyon_yolu.exists():
        LOG.warning("CGGA mutasyon dosyası yok — frekans özelliği üretilmiyor.")
        return pd.DataFrame(columns=["gen", "cgga_missense_frekans", "cgga_orneklem"])

    LOG.info("CGGA mutasyon matrisi okunuyor: %s", mutasyon_yolu.name)
    df = pd.read_csv(mutasyon_yolu, sep="\t", low_memory=False, index_col=0)
    df.index.name = "gen"
    n_orneklem = df.shape[1]
    # 'missense_variant' veya çoklu varyant ('multiple_variant') taşıyan hücreler
    missense_maske = df.apply(
        lambda s: s.astype(str).str.contains("missense", case=False, na=False)
                 | s.astype(str).str.contains("multiple_variant", case=False, na=False)
    )
    sayim = missense_maske.sum(axis=1)
    frekans = (sayim / n_orneklem).rename("cgga_missense_frekans")
    sonuc = frekans.reset_index()
    sonuc["cgga_orneklem"] = n_orneklem
    LOG.info("CGGA gen-bazlı missense frekansı: %d gen, %d örnek",
             len(sonuc), n_orneklem)
    return sonuc


def cgga_klinik_oku(klinik_yolu: Path = config.CGGA_KLINIK_DOSYASI) -> pd.DataFrame:
    """CGGA klinik metadatasını okur (rapor/özet için)."""
    if not klinik_yolu.exists():
        return pd.DataFrame()
    df = pd.read_csv(klinik_yolu, sep="\t", low_memory=False)
    LOG.info("CGGA klinik veri yüklendi: %d hasta", len(df))
    return df


# ---------------------------------------------------------------------------
# COSMIC — yerel TSV (varsa)
# ---------------------------------------------------------------------------
def cosmic_frekans_oku(genler: Iterable[str]) -> pd.DataFrame:
    """
    COSMIC mutasyon TSV dosyasından somatik popülasyon frekansı türetir.

    Kullanıcı `veri/CosmicMutantExport.tsv` dosyasını manuel olarak yerleştirmelidir
    (COSMIC kapalı kayıt gerektirir). Dosya yoksa sentetik frekanslar üretilir.
    """
    if not config.COSMIC_LOKAL_DOSYA.exists():
        LOG.warning("COSMIC dosyası bulunamadı; sentetik frekanslar kullanılacak.")
        return pd.DataFrame(columns=["gen", "protein_degisim", "cosmic_frekans"])

    df = pd.read_csv(config.COSMIC_LOKAL_DOSYA, sep="\t", low_memory=False)
    df = df[df["Gene name"].isin(set(genler))]
    df = df[df["Mutation AA"].fillna("").str.startswith("p.")]
    sayim = (df.groupby(["Gene name", "Mutation AA"]).size()
             .reset_index(name="cosmic_frekans"))
    sayim.columns = ["gen", "protein_degisim", "cosmic_frekans"]
    return sayim


# ---------------------------------------------------------------------------
# Üst seviye birleştirme
# ---------------------------------------------------------------------------
def _mc3_clinsig_etiketle(df: pd.DataFrame) -> pd.DataFrame:
    """
    MC3'ün gömülü VEP anotasyonlarından patojenik / benign etiketi üretir.

    Etiketleme kuralları:
        Patojenik (1):
            * CLIN_SIG'de 'pathogenic' / 'likely_pathogenic'
            * VEYA IMPACT == 'HIGH' (stop_gained, frameshift, splice_donor vb.;
              missense süzgecinde kalanlardan HIGH olanlar yıkıcı kabul edilir
              — ancak filtremiz zaten Missense_Mutation olduğundan bu boş kümedir,
              güvenli kalıyoruz)
        Benign (0):
            * CLIN_SIG'de 'benign' / 'likely_benign'
            * VEYA yaygın popülasyon varyantları: ExAC_AF > 0.01 (yaygın
              polimorfizm; patojenik olamaz çünkü popülasyonda yaygın olarak
              bulunamazdı — bu standart yaklaşım)
        Belirsiz: dışlanır.

    Bu strateji sınıf dengesizliğini hafifletir: ClinVar'da somatik benign
    çoğunlukla yoktur, ama yaygın popülasyon varyantları doğal vekil görür.
    """
    def _cs_etiket(metin: str) -> str | None:
        m = str(metin or "").lower()
        if not m or m in ("nan", "."):
            return None
        if "likely_pathogenic" in m or "likely pathogenic" in m:
            return "Likely_pathogenic"
        if "pathogenic" in m and "non" not in m:
            return "Pathogenic"
        if "likely_benign" in m or "likely benign" in m:
            return "Likely_benign"
        if "benign" in m and "non" not in m:
            return "Benign"
        return None

    df = df.copy()
    df["klinik_anlam"] = df["CLIN_SIG"].astype(str).apply(_cs_etiket)

    # ExAC popülasyon frekansı yüksek olanları benign vekili olarak işaretle
    def _exac_to_float(x):
        try:
            return float(x) if x not in ("", ".", "nan", None) else None
        except (ValueError, TypeError):
            return None

    if "ExAC_AF" not in df.columns:
        df["ExAC_AF"] = ""
    # Tümü boşsa apply object dtype üretip karşılaştırmayı patlatıyordu
    exac = pd.to_numeric(df["ExAC_AF"].apply(_exac_to_float), errors="coerce")
    yaygin_polimorfizm = (exac > 0.01) & df["klinik_anlam"].isna()
    df.loc[yaygin_polimorfizm, "klinik_anlam"] = "Benign"
    LOG.info("ExAC tabanlı yaygın polimorfizm benign etiketi: %d satır",
             int(yaygin_polimorfizm.sum()))

    return df


def _cosmic_sayisi_cikar(cosmic_str: str) -> int:
    """MC3'ün 'COSMIC' kolonu virgülle ayrılmış COSM ID'leri içerir.
    Sayı, ne kadar tekrar eden bir somatik mutasyon olduğunun vekilidir."""
    if not isinstance(cosmic_str, str) or cosmic_str in ("", "nan", "."):
        return 0
    return len([x for x in cosmic_str.split("&") if x.startswith(("COSM", "COSV"))])


def tum_kaynaklari_birlestir() -> pd.DataFrame:
    """
    Veri kaynaklarını öncelik sırasıyla birleştirir:

    1. **MC3 PUBLIC MAF** (yerel) → ana TCGA-GBM/LGG missense kaynağı,
       CLIN_SIG etiketi gömülü, COSMIC ID'leri gömülü.
    2. **ClinVar API + CIVIC** → MC3'te CLIN_SIG'i boş olan varyantlar için
       tamamlayıcı etiket (fallback).
    3. **CGGA WESeq_286** → gen başına Çin kohortu missense frekansı.
    4. **COSMIC lokal TSV** → varsa, varyant-bazlı frekans.
    """
    tcga = tcga_missense_indir()
    LOG.info("Birincil varyant seti (MC3 veya GDC): %d satır", len(tcga))

    # VEP anotasyonu MC3'te de GDC MAF'ında da gelir; ikisinde de aynı yoldan
    # etiket üretiyoruz.
    vep_anotasyonlu = ("CLIN_SIG" in tcga.columns
                       and tcga["CLIN_SIG"].astype(str).str.strip()
                       .replace({"nan": "", ".": ""}).str.len().gt(0).any())

    if vep_anotasyonlu:
        tcga = _mc3_clinsig_etiketle(tcga)
        # Gömülü COSMIC ID'lerinden tekrar sayımı çıkar
        tcga["cosmic_frekans"] = tcga["COSMIC"].apply(_cosmic_sayisi_cikar)
        LOG.info("CLIN_SIG'den etiket çıkarıldı: %d patojenik / %d benign",
                 int((tcga["klinik_anlam"].fillna("").str.lower().str.contains("pathogenic")).sum()),
                 int((tcga["klinik_anlam"].fillna("").str.lower().str.contains("benign")).sum()))

    mevcut_etiket = (int(tcga["klinik_anlam"].notna().sum())
                     if "klinik_anlam" in tcga.columns else 0)
    if mevcut_etiket < 20:
        # Anotasyon yoksa ya da çok az etiket çıktıysa ClinVar/CIVIC ile tamamla
        clinvar = clinvar_etiket_cek(config.HEDEF_GENLER)
        civic = civic_kanit_cek(config.HEDEF_GENLER)
        etiketli = pd.concat([clinvar, civic], ignore_index=True)

        # İki taraf da aynı gösterime indirgenmeden birleştirme tutmuyor
        etiketli["eslesme_anahtari"] = etiketli["protein_degisim"].apply(
            protein_degisim_normalize)
        etiketli = (etiketli.dropna(subset=["eslesme_anahtari"])
                    .drop_duplicates(subset=["gen", "eslesme_anahtari"], keep="first"))
        tcga["eslesme_anahtari"] = tcga["protein_degisim"].apply(
            protein_degisim_normalize)

        tcga = tcga.merge(
            etiketli[["gen", "eslesme_anahtari", "klinik_anlam"]]
            .rename(columns={"klinik_anlam": "klinik_anlam_dis"}),
            on=["gen", "eslesme_anahtari"], how="left",
        )
        if "klinik_anlam" in tcga.columns:
            tcga["klinik_anlam"] = tcga["klinik_anlam"].fillna(tcga["klinik_anlam_dis"])
        else:
            tcga["klinik_anlam"] = tcga["klinik_anlam_dis"]
        tcga = tcga.drop(columns=["klinik_anlam_dis", "eslesme_anahtari"])

        LOG.info("ClinVar/CIVIC eşleşmesi sonrası etiketli varyant: %d",
                 int(tcga["klinik_anlam"].notna().sum()))
        if "cosmic_frekans" not in tcga.columns:
            tcga["cosmic_frekans"] = 0

    # CGGA Çin kohortu gen-frekansı
    cgga_frek = cgga_missense_frekansi_oku()
    if not cgga_frek.empty:
        tcga = tcga.merge(cgga_frek[["gen", "cgga_missense_frekans"]],
                          on="gen", how="left")
    if "cgga_missense_frekans" not in tcga.columns:
        tcga["cgga_missense_frekans"] = 0.0
    tcga["cgga_missense_frekans"] = tcga["cgga_missense_frekans"].fillna(0.0)

    # Etiket çıkarıldıysa filtrele
    tablo = tcga.dropna(subset=["klinik_anlam"]).reset_index(drop=True)

    # Sınıf-bazlı dengeli örnekleme — patojenik ve benignden eşit sayıda al
    is_path = tablo["klinik_anlam"].str.lower().str.contains("pathogenic", na=False)
    patojenik = tablo[is_path]
    benign = tablo[~is_path]
    LOG.info("Etiket havuzu: %d patojenik, %d benign",
             len(patojenik), len(benign))
    if len(patojenik) == 0 or len(benign) == 0:
        LOG.error(
            "Sınıflardan biri boş — ikili sınıflandırma kurulamaz. Olası nedenler: "
            "GDC MAF'ları VEP anotasyonu taşımıyor, ClinVar'a erişilemedi ya da "
            "varyantlar ClinVar kayıtlarıyla eşleşmedi. config.GDC_MAF_DOSYA_SAYISI "
            "değerini arttırmayı veya veri/ altına MC3 PUBLIC MAF koymayı dene."
        )

    yari_hedef = config.MAKS_VARYANT_SAYISI // 2
    n_path = min(len(patojenik), yari_hedef)
    n_benign = min(len(benign), yari_hedef)

    secilen_path = patojenik.sample(n_path, random_state=config.RASTGELE_TOHUM) \
        if n_path > 0 else patojenik
    secilen_benign = benign.sample(n_benign, random_state=config.RASTGELE_TOHUM) \
        if n_benign > 0 else benign

    tablo = pd.concat([secilen_path, secilen_benign], ignore_index=True) \
        .sample(frac=1, random_state=config.RASTGELE_TOHUM) \
        .reset_index(drop=True)

    LOG.info("Dengelenmiş eğitim veri seti: %d satır (%d patojenik / %d benign)",
             len(tablo), n_path, n_benign)
    return tablo
