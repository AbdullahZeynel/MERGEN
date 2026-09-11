"""
SHAP Açıklanabilirlik Modülü
=============================

XGBoost modelinin tahminlerini Shapley değerleri ile açıklar. Her bir
varyantın patojenik/benign kararının hangi biyolojik nedene (ESM şok skoru,
amino asit yük değişimi, hidrofobiklik vb.) dayandığını çıkarır.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import shap

LOG = logging.getLogger(__name__)


def shap_acikla(model, X: pd.DataFrame) -> shap.Explanation:
    """
    Bir XGBoost modeli ve özellik matrisi için Shapley değerlerini hesaplar.

    TreeExplainer kullanılır — ağaç tabanlı modellere uygun, kesin (exact)
    Shapley değerleri üretir ve binlerce örnek için saniyeler içinde çalışır.
    """
    aciklayici = shap.TreeExplainer(model)
    aciklama = aciklayici(X)
    LOG.info("SHAP açıklaması üretildi: %s şekilli", aciklama.values.shape)
    return aciklama


def en_etkili_ozellikler(aciklama: shap.Explanation, n: int = 10) -> pd.DataFrame:
    """
    Global önem sıralaması: ortalama |SHAP| değeri büyükten küçüğe.

    Returns
    -------
    pd.DataFrame
        ``ozellik`` ve ``ortalama_mutlak_shap`` kolonlarıyla.
    """
    mutlak_ort = np.abs(aciklama.values).mean(axis=0)
    siralama = pd.DataFrame({
        "ozellik": aciklama.feature_names,
        "ortalama_mutlak_shap": mutlak_ort,
    }).sort_values("ortalama_mutlak_shap", ascending=False).reset_index(drop=True)
    return siralama.head(n)


def varyant_acikla(
    aciklama: shap.Explanation,
    matris_iz: pd.DataFrame,
    endeks: int,
) -> dict:
    """
    Tek bir varyant için en etkili özellikleri ve yönlerini özetler.

    Bu fonksiyon klinisyenin "bu mutasyon neden patojenik?" sorusuna
    cevap verecek metni üretmek için kullanılır.
    """
    sv = aciklama.values[endeks]
    ozellikler = aciklama.feature_names
    siralama = sorted(
        zip(ozellikler, sv), key=lambda x: abs(x[1]), reverse=True
    )[:5]

    return {
        "gen": matris_iz.iloc[endeks]["gen"],
        "protein_degisim": matris_iz.iloc[endeks]["protein_degisim"],
        "patojenite_yonu": float(sv.sum()),
        "en_belirleyici_ozellikler": [
            {"ozellik": o, "shap_degeri": float(d)} for o, d in siralama
        ],
    }
