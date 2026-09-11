"""
Görselleştirme Modülü
======================

Pipeline çalıştığında ``sonuclar/`` altına otomatik kaydedilen PNG'leri
üretir. Tüm grafikler proje sunum estetiğine uygun, yüksek DPI'da
ve başlık/etiket Türkçe olarak hazırlanır.
"""

from __future__ import annotations

import logging

import matplotlib

matplotlib.use("Agg")        # headless ortam (CI / Windows servis)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import shap
from sklearn.metrics import (
    confusion_matrix, precision_recall_curve, roc_curve,
)

from .. import config

LOG = logging.getLogger(__name__)

sns.set_theme(style="whitegrid", context="talk")


def _nan_ayikla(y_gercek, olas):
    """Skoru olmayan (NaN) varyantları eğriden düşürür — uydurma skor yok."""
    y = np.asarray(y_gercek)
    o = np.asarray(olas, dtype=float)
    maske = ~np.isnan(o)
    return y[maske], o[maske]


# ---------------------------------------------------------------------------
def roc_egrisi_ciz(
    y_gercek: np.ndarray,
    olasilik_haritasi: dict[str, np.ndarray],
    cikti: str = "roc_karsilastirma.png",
) -> str:
    """
    Birden çok sınıflandırıcının ROC eğrisini aynı eksende kıyaslar.

    Parameters
    ----------
    olasilik_haritasi : dict
        ``{"MERGEN": olas, "SIFT": olas, "PolyPhen2": olas}``
    """
    fig, ax = plt.subplots(figsize=(8, 7))
    for ad, olas in olasilik_haritasi.items():
        try:
            y, o = _nan_ayikla(y_gercek, olas)
            fpr, tpr, _ = roc_curve(y, o)
            from sklearn.metrics import auc
            etiket = f"{ad} (AUC = {auc(fpr, tpr):.3f}"
            etiket += f", n={len(y)})" if len(y) != len(y_gercek) else ")"
            ax.plot(fpr, tpr, lw=2.5, label=etiket)
        except ValueError:
            continue
    ax.plot([0, 1], [0, 1], "--", color="gray", lw=1.5, alpha=0.7)
    ax.set_xlabel("Yanlış Pozitif Oranı (FPR)")
    ax.set_ylabel("Doğru Pozitif Oranı (TPR)")
    ax.set_title("ROC Eğrisi — MERGEN vs Klasik Yöntemler", fontsize=14)
    ax.legend(loc="lower right")
    fig.tight_layout()
    yol = config.SONUC_DIZINI / cikti
    fig.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close(fig)
    LOG.info("ROC eğrisi kaydedildi: %s", yol)
    return str(yol)


# ---------------------------------------------------------------------------
def pr_egrisi_ciz(y_gercek, olasilik_haritasi, cikti="pr_karsilastirma.png") -> str:
    """Precision-Recall eğrisi — dengesiz sınıflarda ROC'tan daha bilgilendirici."""
    fig, ax = plt.subplots(figsize=(8, 7))
    for ad, olas in olasilik_haritasi.items():
        try:
            y, o = _nan_ayikla(y_gercek, olas)
            p, r, _ = precision_recall_curve(y, o)
            ax.plot(r, p, lw=2.5,
                    label=ad if len(y) == len(y_gercek) else f"{ad} (n={len(y)})")
        except ValueError:
            continue
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Eğrisi", fontsize=14)
    ax.legend(loc="lower left")
    fig.tight_layout()
    yol = config.SONUC_DIZINI / cikti
    fig.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(yol)


# ---------------------------------------------------------------------------
def karisiklik_matrisi_ciz(y_gercek, y_tahmin, cikti="karisiklik_matrisi.png") -> str:
    """Sınıflandırma karışıklık matrisinin ısı haritası."""
    cm = confusion_matrix(y_gercek, y_tahmin)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax,
                xticklabels=["Benign", "Patojenik"],
                yticklabels=["Benign", "Patojenik"],
                annot_kws={"size": 18})
    ax.set_xlabel("Tahmin")
    ax.set_ylabel("Gerçek")
    ax.set_title("MERGEN — Karışıklık Matrisi", fontsize=14)
    fig.tight_layout()
    yol = config.SONUC_DIZINI / cikti
    fig.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(yol)


# ---------------------------------------------------------------------------
def metrik_kar_grafigi(
    karsilastirma: dict, cikti="metrik_karsilastirma.png",
) -> str:
    """
    MERGEN vs SIFT vs PolyPhen-2 için dört temel metriğin bar grafiği.
    """
    metrikler = ["dogruluk", "f1", "recall", "roc_auc"]
    etiketler = ["Doğruluk", "F1-Skoru", "Recall", "ROC-AUC"]
    modeller = ["MERGEN", "SIFT", "PolyPhen2"]

    veri = []
    for met, et in zip(metrikler, etiketler):
        for m in modeller:
            val = karsilastirma.get(m, {}).get(met)
            if val is not None and not np.isnan(val):
                veri.append({"metrik": et, "model": m, "değer": val})
    df = pd.DataFrame(veri)

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=df, x="metrik", y="değer", hue="model", ax=ax,
                palette=["#2563eb", "#16a34a", "#dc2626"])
    ax.set_ylim(0, 1.05)
    ax.set_title("Klasik Araçlarla Karşılaştırma — Test Seti Performansı",
                 fontsize=14)
    ax.set_xlabel("")
    ax.set_ylabel("Skor")
    for konteyner in ax.containers:
        ax.bar_label(konteyner, fmt="%.2f", padding=3, fontsize=10)
    fig.tight_layout()
    yol = config.SONUC_DIZINI / cikti
    fig.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(yol)


# ---------------------------------------------------------------------------
def shap_ozet_ciz(aciklama, cikti="shap_ozet.png") -> str:
    """SHAP summary plot — global özellik önemi + yön dağılımı."""
    fig = plt.figure(figsize=(10, 7))
    shap.summary_plot(aciklama, show=False, plot_size=(10, 7))
    yol = config.SONUC_DIZINI / cikti
    plt.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close()
    LOG.info("SHAP özeti kaydedildi: %s", yol)
    return str(yol)


def shap_bar_ciz(aciklama, cikti="shap_bar.png") -> str:
    """SHAP bar plot — ortalama mutlak SHAP'a göre özellik önemi."""
    fig = plt.figure(figsize=(9, 6))
    shap.plots.bar(aciklama, show=False, max_display=15)
    yol = config.SONUC_DIZINI / cikti
    plt.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close()
    return str(yol)


def shap_karar_ciz(aciklama, n_orneklem: int = 30,
                  cikti="shap_karar.png") -> str:
    """
    SHAP decision plot — örnek varyantların karar yolaklarını görselleştirir.
    Klinisyenin "modelimi neden buraya götürdü?" sorusuna ideal cevap.
    """
    if len(aciklama.values) > n_orneklem:
        idx = np.random.RandomState(config.RASTGELE_TOHUM).choice(
            len(aciklama.values), n_orneklem, replace=False
        )
    else:
        idx = np.arange(len(aciklama.values))

    fig = plt.figure(figsize=(10, 8))
    shap.decision_plot(
        base_value=float(aciklama.base_values[0]) if np.ndim(aciklama.base_values) else float(aciklama.base_values),
        shap_values=aciklama.values[idx],
        features=aciklama.data[idx],
        feature_names=aciklama.feature_names,
        show=False,
        ignore_warnings=True,
    )
    yol = config.SONUC_DIZINI / cikti
    plt.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close()
    return str(yol)


# ---------------------------------------------------------------------------
def cv_kutu_grafigi(cv_skorlar: list[float], cikti="cv_kutu.png") -> str:
    """Çapraz doğrulama fold-başına AUC dağılımının kutu grafiği."""
    if not cv_skorlar:
        return ""
    fig, ax = plt.subplots(figsize=(6, 6))
    sns.boxplot(y=cv_skorlar, color="#2563eb", ax=ax, width=0.4)
    sns.stripplot(y=cv_skorlar, color="black", size=8, ax=ax, jitter=True)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("ROC-AUC")
    ax.set_title("Gen-Grup Çapraz Doğrulama (GroupKFold)", fontsize=13)
    fig.tight_layout()
    yol = config.SONUC_DIZINI / cikti
    fig.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(yol)
