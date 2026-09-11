"""
Model Eğitim Modülü
====================

Çok modlu özellik matrisi üzerinde XGBoost (GBDT) sınıflandırıcı eğitir,
stratifiye train/test ayrımı yapar, gen-grup tabanlı çapraz doğrulama
(GroupKFold) uygular ve eğitimli modeli diske kaydeder.

Gen-grup bazlı CV: aynı genin varyantları aynı fold içinde tutulur. Bu,
"TCGA dışı bir kohort üzerinde nasıl davranır?" sorusunun korsanlık-vekil
testidir: model gen-spesifik desenlere değil, taşınabilir biyolojik
sinyallere bel bağlamak zorunda kalır.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, train_test_split

from .. import config

LOG = logging.getLogger(__name__)

# Modelin asla kullanmaması gereken iz / etiket kolonları
# (mc3_sift / mc3_polyphen rakip yöntem skorları; modele girerse haksız avantaj olur)
IZ_KOLONLARI = {"etiket", "gen", "protein_degisim", "kohort",
                "mc3_sift_skor", "mc3_polyphen_skor"}


# ---------------------------------------------------------------------------
def ozellikleri_ayir(
    matris: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Özellik matrisinden (X, y, gruplar) tuple'ı çıkarır."""
    X = matris.drop(columns=[c for c in IZ_KOLONLARI if c in matris.columns])
    y = matris["etiket"].astype(int)
    gruplar = matris["gen"].astype(str) if "gen" in matris.columns \
        else pd.Series(["G"] * len(matris))
    return X, y, gruplar


# ---------------------------------------------------------------------------
def capraz_dogrulama_yap(
    X: pd.DataFrame, y: pd.Series, gruplar: pd.Series,
    fold_sayisi: int = config.CV_FOLD_SAYISI,
) -> dict:
    """
    GroupKFold ile gen-grup tabanlı CV uygular.

    Returns
    -------
    dict
        ``{"fold_auc": [...], "ortalama_auc": float, "std_auc": float}``
    """
    benzersiz = gruplar.nunique()
    etkili_fold = min(fold_sayisi, benzersiz)
    if etkili_fold < 2:
        LOG.warning("Yetersiz grup sayısı (n=%d); CV atlanıyor.", benzersiz)
        return {"fold_auc": [], "ortalama_auc": float("nan"), "std_auc": float("nan")}

    gkf = GroupKFold(n_splits=etkili_fold)
    fold_skorlari: list[float] = []

    for kat, (eg, tst) in enumerate(gkf.split(X, y, groups=gruplar), 1):
        if len(np.unique(y.iloc[tst])) < 2:
            LOG.debug("Fold %d tek sınıflı, atlanıyor.", kat)
            continue
        model = xgb.XGBClassifier(**config.XGB_HIPERPARAMETRELER)
        model.fit(X.iloc[eg], y.iloc[eg])
        olas = model.predict_proba(X.iloc[tst])[:, 1]
        auc = roc_auc_score(y.iloc[tst], olas)
        fold_skorlari.append(auc)
        LOG.info("CV fold %d/%d AUC=%.4f", kat, etkili_fold, auc)

    if not fold_skorlari:
        return {"fold_auc": [], "ortalama_auc": float("nan"), "std_auc": float("nan")}

    return {
        "fold_auc": fold_skorlari,
        "ortalama_auc": float(np.mean(fold_skorlari)),
        "std_auc": float(np.std(fold_skorlari)),
    }


# ---------------------------------------------------------------------------
def son_modeli_egit(
    X: pd.DataFrame, y: pd.Series,
) -> tuple[xgb.XGBClassifier, dict]:
    """
    Stratifiye train/test ayrımı yapar, model eğitir ve test metriklerini
    döndürür. Aynı zamanda model nesnesini diske kaydeder.
    """
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=config.TEST_ORANI,
        random_state=config.RASTGELE_TOHUM, stratify=y,
    )

    model = xgb.XGBClassifier(**config.XGB_HIPERPARAMETRELER)
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

    test_olas = model.predict_proba(X_te)[:, 1]
    test_tahmin = (test_olas >= 0.5).astype(int)

    # Modeli kaydet (XGBoost native + joblib her ikisi de)
    model_yolu = config.MODEL_DIZINI / "mergen_xgb.joblib"
    joblib.dump(model, model_yolu)
    model.save_model(str(config.MODEL_DIZINI / "mergen_xgb.json"))
    LOG.info("Model kaydedildi: %s", model_yolu)

    bilgi = {
        "X_train": X_tr, "X_test": X_te,
        "y_train": y_tr, "y_test": y_te,
        "test_olasiliklar": test_olas,
        "test_tahminler": test_tahmin,
        "model_yolu": str(model_yolu),
        "ozellik_isimleri": list(X.columns),
    }
    return model, bilgi
