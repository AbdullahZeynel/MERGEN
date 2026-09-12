"""
MERGEN Projesi - Merkezi Konfigürasyon Modülü
==============================================

Tüm modüllerin paylaştığı sabitler, yollar, API uç noktaları
ve hiperparametreler bu dosyada toplanır.

Yazar: MERGEN Ekibi (TEKNOFEST Onkolojide 3T - 2026)
"""

import os
from pathlib import Path


def _ortam_yolu(degisken: str, varsayilan: Path) -> Path:
    """Ortam değişkeni doluysa onu, değilse varsayılanı döndürür.

    Ağırlıklar ve veri Git dışıdır; worker, worktree veya ayrı bir kurulum
    bunları başka bir yerde tutabilsin diye yollar yapılandırılabilir.
    Değişken tanımlı değilse davranış eskisiyle birebir aynıdır.
    """
    ham = os.environ.get(degisken, "").strip()
    return Path(ham).expanduser().resolve() if ham else varsayilan


def _ortam_bayragi(degisken: str, varsayilan: bool) -> bool:
    ham = os.environ.get(degisken, "").strip().lower()
    if not ham:
        return varsayilan
    return ham in ("1", "true", "yes", "on", "evet")


# ---------------------------------------------------------------------------
# Dizin yolları (proje kökü = bu dosyanın bulunduğu klasör)
# ---------------------------------------------------------------------------
PROJE_KOKU = Path(__file__).resolve().parent
VERI_DIZINI = _ortam_yolu("MERGEN_GENOMIK_VERI_DIZINI", PROJE_KOKU / "veri")
SONUC_DIZINI = _ortam_yolu("MERGEN_GENOMIK_SONUC_DIZINI", PROJE_KOKU / "sonuclar")
MODEL_DIZINI = _ortam_yolu("MERGEN_GENOMIK_MODEL_DIZINI", PROJE_KOKU / "modeller")
ONBELLEK_DIZINI = VERI_DIZINI / "onbellek"

for _dizin in (VERI_DIZINI, SONUC_DIZINI, MODEL_DIZINI, ONBELLEK_DIZINI):
    _dizin.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Harici API uç noktaları
# ---------------------------------------------------------------------------
GDC_API = "https://api.gdc.cancer.gov"
GDC_FILES_ENDPOINT = f"{GDC_API}/files"
GDC_DATA_ENDPOINT = f"{GDC_API}/data"

CLINVAR_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CIVIC_API = "https://civicdb.org/api/variants"
MYVARIANT_API = "https://myvariant.info/v1"
UNIPROT_API = "https://rest.uniprot.org/uniprotkb/search"
ENSEMBL_API = "https://rest.ensembl.org"

# COSMIC kapalı erişimli olduğundan kullanıcı yerel dosyayı belirtmelidir.
# Boşsa pipeline COSMIC modülünü atlar ve sentetik frekans üretir.
COSMIC_LOKAL_DOSYA = VERI_DIZINI / "CosmicMutantExport.tsv"

# ---------------------------------------------------------------------------
# Yerel veri dosyaları (kullanıcı tarafından `veri/` klasörüne yerleştirildi)
# ---------------------------------------------------------------------------
def veri_yolu(*adaylar: str) -> Path:
    """
    `veri/` altındaki bir dosyayı bulur; ilk bulunan aday döner.

    İki tuzağı birden kapatır:
      * macOS'ta açılan zip'ler dosyayı aynı adlı bir klasörün içine koyuyor
        (``veri/X.txt/X.txt``) — iki düzen de kabul edilir.
      * Aynı dosya sıkıştırılmış ya da açılmış hâlde durabiliyor
        (``.maf.gz`` / ``.maf``) — birden fazla aday verilebilir.
    """
    for ad in adaylar:
        dogrudan = VERI_DIZINI / ad
        if dogrudan.is_file():
            return dogrudan
        icice = dogrudan / ad
        if icice.is_file():
            return icice
    return VERI_DIZINI / adaylar[0]   # yoksa da beklenen yolu döndür


# MC3 dosyası .gz olarak da açılmış hâlde de duruyor olabilir
MC3_YEREL_MAF = veri_yolu("mc3.v0.2.8.PUBLIC.maf.gz", "mc3.v0.2.8.PUBLIC.maf")
CGGA_MUTASYON_DOSYASI = veri_yolu("CGGA.WEseq_286.20200506.txt")
CGGA_KLINIK_DOSYASI = veri_yolu("CGGA.WEseq_286_clinical.20200506.txt")

# TCGA-GBM ve TCGA-LGG tissue source site (TSS) kodları
# Kaynak: https://gdc.cancer.gov/resources-tcga-users/tcga-code-tables/tissue-source-site-codes
TCGA_GBM_TSS = {"02", "06", "08", "12", "14", "15", "16", "19",
                "26", "27", "28", "32", "41", "74", "76", "81", "87", "RR"}
TCGA_LGG_TSS = {"CS", "DB", "DH", "DU", "E1", "EZ", "FG", "HT", "IK",
                "KT", "P5", "QH", "R8", "RY", "S9", "TM", "TQ", "VM",
                "VV", "W9", "WH", "WY"}

# ---------------------------------------------------------------------------
# Veri seti yapılandırması
# ---------------------------------------------------------------------------
TCGA_PROJELERI = ["TCGA-GBM", "TCGA-LGG"]
HEDEF_MUTASYON_TIPI = "Missense_Mutation"

# GDC'de her MAF dosyası TEK bir vakaya ait (masked somatic mutation).
# Az dosya çekmek doğrudan az varyant demek; etiketlenebilir varyant bulmak
# için proje başına yeterince dosya indirilmeli.
GDC_MAF_DOSYA_SAYISI = 60

# ClinVar'da gen başına taranacak kayıt sayısı
CLINVAR_GEN_BASINA = 200

# Pipeline'ın bir koşuda inceleyeceği varyant sayısı.
# Demo / CPU çalıştırması için makul; donanım yeterliyse arttırılabilir.
# GPU varsa 2000+, CPU sınırlı sistemlerde 600.
MAKS_VARYANT_SAYISI = 2000

# Glioma'da klinik olarak önemli sürücü genler — pipeline öncelikle bunlara odaklanır.
HEDEF_GENLER = [
    "IDH1", "IDH2", "TP53", "ATRX", "EGFR", "PTEN", "PIK3CA", "PIK3R1",
    "NF1", "CIC", "FUBP1", "TERT", "H3F3A", "BRAF", "RB1", "CDKN2A",
]

# ---------------------------------------------------------------------------
# ESM-2 protein dil modeli yapılandırması
# ---------------------------------------------------------------------------
ESM_MODEL_ADI = "facebook/esm2_t30_150M_UR50D"
ESM_MAKS_DIZILIM_UZUNLUGU = 1022      # ESM-2 girişine sığacak şekilde
ESM_PENCERE_YARI_GENISLIGI = 200      # Uzun proteinlerde mutasyon merkezli pencere

# ESM-2 ağırlıklarının yeri ve çevrimdışı davranışı.
#   MERGEN_ESM_YEREL_YOL   : indirilmiş snapshot dizini (config.json + ağırlık)
#   MERGEN_ESM_CACHE_DIZINI: Hugging Face hub cache kökü (HF_HOME/hub karşılığı)
#   MERGEN_ESM_INDIRME_IZNI: yalnız hazırlık adımında 1 yapılır
# Varsayılan çevrimdışıdır: canlı çıkarım sırasında ağa çıkılmaz, ağırlık
# bulunamazsa sessizce indirmek yerine açık hata verilir.
ESM_YEREL_YOL = os.environ.get("MERGEN_ESM_YEREL_YOL", "").strip() or None
ESM_CACHE_DIZINI = os.environ.get("MERGEN_ESM_CACHE_DIZINI", "").strip() or None
ESM_INDIRME_IZNI = _ortam_bayragi("MERGEN_ESM_INDIRME_IZNI", False)

# ---------------------------------------------------------------------------
# Model eğitim yapılandırması
# ---------------------------------------------------------------------------
RASTGELE_TOHUM = 42
TEST_ORANI = 0.2
CV_FOLD_SAYISI = 5

XGB_HIPERPARAMETRELER = {
    "n_estimators": 600,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "objective": "binary:logistic",
    "eval_metric": "auc",
    "tree_method": "hist",
    "random_state": RASTGELE_TOHUM,
}

# ---------------------------------------------------------------------------
# Etiket sözlüğü (ClinVar / CIVIC normalizasyonu için)
# ---------------------------------------------------------------------------
PATOJENIK_ETIKETLER = {
    "Pathogenic", "Likely_pathogenic", "Likely pathogenic",
    "pathogenic", "likely pathogenic",
}
BENIGN_ETIKETLER = {
    "Benign", "Likely_benign", "Likely benign", "benign", "likely benign",
}

# 20 standart amino asit (ESM-2 ve AAindex hesapları için ortak referans)
STANDART_AA = "ACDEFGHIKLMNPQRSTVWY"
