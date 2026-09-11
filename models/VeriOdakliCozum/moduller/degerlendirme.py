"""
Değerlendirme Modülü
=====================

İki kritik işlevi yerine getirir:

1. **Standart sınıflandırma metrikleri** — Doğruluk, F1, Recall, Precision,
   ROC-AUC, PR-AUC ve karışıklık matrisini hesaplar.
2. **Klasik araç karşılaştırması** — SIFT ve PolyPhen-2 skorlarını
   myvariant.info üzerinden dbNSFP veri tabanından çeker, McNemar testi ile
   MERGEN modeli ile istatistiksel karşılaştırma yapar.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

import numpy as np
import pandas as pd
import requests
from scipy.stats import chi2
from sklearn.metrics import (
    accuracy_score, average_precision_score, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score, roc_curve,
)

from .. import config

LOG = logging.getLogger(__name__)


# ===========================================================================
# Standart metrikler
# ===========================================================================
def metrikleri_hesapla(y_gercek: np.ndarray, y_olas: np.ndarray,
                      esik: float = 0.5) -> dict:
    """
    İkili sınıflandırma için kapsamlı metrik raporu üretir.

    Parameters
    ----------
    y_gercek, y_olas : np.ndarray
        Gerçek etiketler (0/1) ve patojenik olasılıkları.
    esik : float
        Karar eşiği (varsayılan 0.5).
    """
    y_tahmin = (y_olas >= esik).astype(int)

    metrikler = {
        "dogruluk": accuracy_score(y_gercek, y_tahmin),
        "f1": f1_score(y_gercek, y_tahmin, zero_division=0),
        "precision": precision_score(y_gercek, y_tahmin, zero_division=0),
        "recall": recall_score(y_gercek, y_tahmin, zero_division=0),
        "roc_auc": roc_auc_score(y_gercek, y_olas) if len(np.unique(y_gercek)) > 1 else float("nan"),
        "pr_auc": average_precision_score(y_gercek, y_olas) if len(np.unique(y_gercek)) > 1 else float("nan"),
    }
    cm = confusion_matrix(y_gercek, y_tahmin)
    metrikler["karisiklik_matrisi"] = cm.tolist()

    # ROC eğrisi koordinatları (görselleştirme için)
    if len(np.unique(y_gercek)) > 1:
        fpr, tpr, _ = roc_curve(y_gercek, y_olas)
        metrikler["roc_fpr"] = fpr.tolist()
        metrikler["roc_tpr"] = tpr.tolist()
    return metrikler


# ===========================================================================
# dbNSFP — SIFT / PolyPhen skorlarını myvariant.info üzerinden çek
# ===========================================================================
def _myvariant_sorgula(hgvs_list: Iterable[str]) -> list[dict]:
    """myvariant.info batch endpoint — dbNSFP SIFT/PolyPhen alanları."""
    alanlar = ("dbnsfp.sift.pred,dbnsfp.sift.score,"
               "dbnsfp.polyphen2.hdiv.pred,dbnsfp.polyphen2.hdiv.score,"
               "dbnsfp.polyphen2.hvar.pred,dbnsfp.polyphen2.hvar.score")
    try:
        yanit = requests.post(
            f"{config.MYVARIANT_API}/variant",
            data={"ids": ",".join(hgvs_list), "fields": alanlar},
            timeout=60,
        )
        if yanit.status_code == 200:
            return yanit.json()
    except Exception as exc:
        LOG.debug("myvariant.info hatası: %s", exc)
    return []


def klasik_arac_karsilastirmasi(matris: pd.DataFrame) -> pd.DataFrame:
    """
    SIFT ve PolyPhen-2 skorlarını tedarik eder.

    Strateji:
        1. MC3'ten gelen ``mc3_sift_skor`` / ``mc3_polyphen_skor`` iz
           kolonları varsa **doğrudan** onları kullan (en güvenilir, MAF'ın
           üzerinde VEP-anotasyonlu skorlardır).
        2. Eksik kalanlar için myvariant.info dbNSFP API'sini sorgula.
        3. Hâlâ eksikse vekil dağılımdan örnekle (rapor şeffafça not eder).
    """
    iz_sift = ("mc3_sift_skor" in matris.columns
               and matris["mc3_sift_skor"].notna().any())
    iz_pp = ("mc3_polyphen_skor" in matris.columns
             and matris["mc3_polyphen_skor"].notna().any())

    sift_skor: list[float] = []
    pp_skor: list[float] = []
    bulundu_mc3 = 0
    bulundu_api = 0

    # Önce MC3 iz kolonlarını dene
    mc3_sift_arr = matris["mc3_sift_skor"].values if iz_sift else [None] * len(matris)
    mc3_pp_arr = matris["mc3_polyphen_skor"].values if iz_pp else [None] * len(matris)

    eksik_indeksler: list[int] = []
    for i in range(len(matris)):
        s = mc3_sift_arr[i] if iz_sift else None
        p = mc3_pp_arr[i] if iz_pp else None
        if s is not None and not pd.isna(s) and p is not None and not pd.isna(p):
            sift_skor.append(float(s))
            pp_skor.append(float(p))
            bulundu_mc3 += 1
        else:
            sift_skor.append(np.nan)
            pp_skor.append(np.nan)
            eksik_indeksler.append(i)

    LOG.info("MC3 anotasyonlu klasik skor bulunan varyant: %d / %d",
             bulundu_mc3, len(matris))

    # Eksikler için myvariant.info'a dene
    if eksik_indeksler:
        hgvs = [f"{matris.iloc[i]['gen']}:{matris.iloc[i]['protein_degisim']}"
                for i in eksik_indeksler]
        LOG.info("Eksik %d varyant için dbNSFP (myvariant.info) sorgulanıyor…",
                 len(hgvs))
        parti = 100
        for j in range(0, len(hgvs), parti):
            ks = _myvariant_sorgula(hgvs[j:j + parti])
            kayit_map = {k.get("query"): k for k in ks}
            for poz, q in enumerate(hgvs[j:j + parti]):
                orijinal_idx = eksik_indeksler[j + poz]
                kayit = kayit_map.get(q, {})
                ds = (kayit.get("dbnsfp") or {})
                s = (ds.get("sift") or {}).get("score")
                p = (ds.get("polyphen2", {}).get("hdiv") or {}).get("score")
                if s is None or p is None:
                    # Skor bulunamadı: NaN kalır ve karşılaştırma dışında tutulur.
                    # (Eskiden buraya rastgele sayı yazılıyordu — rakip aracın
                    #  skorunu uydurmak karşılaştırmayı geçersiz kılar.)
                    continue
                try:
                    sift_skor[orijinal_idx] = float(np.asarray(s).mean())
                    pp_skor[orijinal_idx] = float(np.asarray(p).mean())
                    bulundu_api += 1
                except (TypeError, ValueError):
                    continue
            time.sleep(0.3)

    toplam_kapsama = (bulundu_mc3 + bulundu_api) / max(len(matris), 1)
    LOG.info("Toplam gerçek klasik skor kapsaması: %.2f%% (%d/%d)",
             100 * toplam_kapsama, bulundu_mc3 + bulundu_api, len(matris))

    sift_arr = np.array(sift_skor, dtype=float)
    pp_arr = np.array(pp_skor, dtype=float)
    gecerli = ~(np.isnan(sift_arr) | np.isnan(pp_arr))
    if not gecerli.all():
        LOG.warning("Klasik skoru bulunamayan %d varyant karşılaştırma dışında "
                    "tutuluyor.", int((~gecerli).sum()))
    return pd.DataFrame({
        "sift_skor": sift_arr,
        "polyphen_skor": pp_arr,
        "sift_patojenik": (sift_arr < 0.05).astype(int),
        "polyphen_patojenik": (pp_arr > 0.5).astype(int),
        "klasik_gecerli": gecerli,
        "dbnsfp_kapsama": toplam_kapsama,
    })


# ===========================================================================
# McNemar testi — eşli sınıflandırıcı karşılaştırması
# ===========================================================================
def mcnemar_testi(y_gercek: np.ndarray, tahmin_a: np.ndarray,
                 tahmin_b: np.ndarray) -> dict:
    """
    İki sınıflandırıcının aynı test seti üzerindeki kararları için
    McNemar χ² testi uygular (süreklilik düzeltmeli).
    """
    a_dogru = tahmin_a == y_gercek
    b_dogru = tahmin_b == y_gercek
    b_dogru_a_yanlis = int(np.sum(b_dogru & ~a_dogru))
    a_dogru_b_yanlis = int(np.sum(a_dogru & ~b_dogru))

    if (b_dogru_a_yanlis + a_dogru_b_yanlis) == 0:
        return {"chi2": 0.0, "p_degeri": 1.0,
                "a_lehine": a_dogru_b_yanlis, "b_lehine": b_dogru_a_yanlis}

    chi2_ist = ((abs(b_dogru_a_yanlis - a_dogru_b_yanlis) - 1.0) ** 2
                / (b_dogru_a_yanlis + a_dogru_b_yanlis))
    p = float(1.0 - chi2.cdf(chi2_ist, df=1))
    return {"chi2": float(chi2_ist), "p_degeri": p,
            "a_lehine": a_dogru_b_yanlis, "b_lehine": b_dogru_a_yanlis}


def tam_karsilastirma_raporu(
    y_gercek: np.ndarray,
    mergen_olas: np.ndarray,
    klasik: pd.DataFrame,
) -> dict:
    """
    MERGEN modeli ile SIFT ve PolyPhen-2'yi tüm metrikler üzerinden karşılaştırır.
    """
    mergen_tahmin = (mergen_olas >= 0.5).astype(int)

    # Klasik skoru olmayan varyantlar karşılaştırmadan çıkarılır; MERGEN kendi
    # metriklerini tüm test seti üzerinde verir, klasik araçlar ise yalnızca
    # skorlarının bulunabildiği alt küme üzerinde (n rapora yazılmalı).
    if "klasik_gecerli" in klasik.columns:
        gecerli = klasik["klasik_gecerli"].values.astype(bool)
    else:
        gecerli = ~(klasik["sift_skor"].isna() | klasik["polyphen_skor"].isna()).values

    rapor = {
        "MERGEN": metrikleri_hesapla(y_gercek, mergen_olas),
        "SIFT": metrikleri_hesapla(
            y_gercek[gecerli],
            1.0 - klasik["sift_skor"].values[gecerli],  # SIFT'te düşük skor ⇒ patojenik
        ),
        "PolyPhen2": metrikleri_hesapla(
            y_gercek[gecerli], klasik["polyphen_skor"].values[gecerli],
        ),
    }
    rapor["n_test"] = int(len(y_gercek))
    rapor["n_klasik_karsilastirma"] = int(gecerli.sum())

    rapor["MERGEN_vs_SIFT_mcnemar"] = mcnemar_testi(
        y_gercek[gecerli], mergen_tahmin[gecerli],
        klasik["sift_patojenik"].values[gecerli]
    )
    rapor["MERGEN_vs_PolyPhen_mcnemar"] = mcnemar_testi(
        y_gercek[gecerli], mergen_tahmin[gecerli],
        klasik["polyphen_patojenik"].values[gecerli]
    )
    rapor["dbnsfp_kapsama"] = float(klasik["dbnsfp_kapsama"].iloc[0]) \
        if "dbnsfp_kapsama" in klasik.columns else 0.0
    return rapor
