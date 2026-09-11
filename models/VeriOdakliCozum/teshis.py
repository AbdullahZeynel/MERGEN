"""
MERGEN Modeli Overfit/Underfit Teşhis Betiği
=============================================

Üç farklı açıdan modelin genelleme durumunu inceler:

1. **Train-Test Gap (Klasik overfit testi):**
   Eğitim ve test setindeki AUC farkını ölçer. Büyük fark ⇒ overfit.

2. **Stratified vs Gen-Grup Test Farkı:**
   Aynı genden örnek görmek vs hiç görmeden başka gene tahmin yapmak
   arasındaki performans farkı. Büyük fark ⇒ gen-kimliğine overfit.

3. **Öğrenme Eğrisi:**
   Eğitim örneklem boyutu artıkça train/test skorların yakınsayışı.
   Train↑ Test↓ veya iki çizgi açılıyorsa overfit; ikisi düşükse underfit.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import xgboost as xgb
from sklearn.metrics import (accuracy_score, average_precision_score,
                              f1_score, roc_auc_score)
from sklearn.model_selection import (GroupKFold, StratifiedKFold,
                                       learning_curve, train_test_split)

from VeriOdakliCozum import config
from VeriOdakliCozum.moduller import model_egitim

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%H:%M:%S")
LOG = logging.getLogger("TESHIS")

sns.set_theme(style="whitegrid")


def _model_olustur() -> xgb.XGBClassifier:
    return xgb.XGBClassifier(**config.XGB_HIPERPARAMETRELER)


def teshis_calistir() -> dict:
    matris = pd.read_csv(config.VERI_DIZINI / "ozellik_matrisi.csv")
    X, y, gruplar = model_egitim.ozellikleri_ayir(matris)
    LOG.info("Veri: %d satır, %d özellik, %d gen",
             len(X), X.shape[1], gruplar.nunique())

    # ---------------------- 1) Train-Test Gap ---------------------------------
    LOG.info("[1/3] Stratifiye train/test AUC karşılaştırması…")
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=config.TEST_ORANI,
        random_state=config.RASTGELE_TOHUM, stratify=y,
    )
    model = _model_olustur()
    model.fit(X_tr, y_tr)
    tr_olas = model.predict_proba(X_tr)[:, 1]
    te_olas = model.predict_proba(X_te)[:, 1]

    train_auc = roc_auc_score(y_tr, tr_olas)
    test_auc = roc_auc_score(y_te, te_olas)
    train_acc = accuracy_score(y_tr, (tr_olas >= 0.5).astype(int))
    test_acc = accuracy_score(y_te, (te_olas >= 0.5).astype(int))
    train_f1 = f1_score(y_tr, (tr_olas >= 0.5).astype(int))
    test_f1 = f1_score(y_te, (te_olas >= 0.5).astype(int))

    auc_gap = train_auc - test_auc
    LOG.info("  Train AUC: %.4f | Test AUC: %.4f | Δ = %.4f",
             train_auc, test_auc, auc_gap)
    LOG.info("  Train ACC: %.4f | Test ACC: %.4f", train_acc, test_acc)

    # ---------------------- 2) Stratified-CV vs GroupKFold --------------------
    LOG.info("[2/3] Aynı gen-farklı varyant vs farklı gen testi…")
    skf = StratifiedKFold(n_splits=5, shuffle=True,
                          random_state=config.RASTGELE_TOHUM)
    stratified_auc = []
    for eg, ts in skf.split(X, y):
        m = _model_olustur()
        m.fit(X.iloc[eg], y.iloc[eg])
        p = m.predict_proba(X.iloc[ts])[:, 1]
        stratified_auc.append(roc_auc_score(y.iloc[ts], p))

    gkf_sonuc = model_egitim.capraz_dogrulama_yap(X, y, gruplar, fold_sayisi=5)
    group_auc = gkf_sonuc["fold_auc"]

    LOG.info("  Stratified-CV (aynı genler): %.4f ± %.4f",
             np.mean(stratified_auc), np.std(stratified_auc))
    LOG.info("  GroupKFold (yeni genler):    %.4f ± %.4f",
             np.mean(group_auc), np.std(group_auc))
    LOG.info("  Genelleme açığı (Stratified − Group): %.4f",
             np.mean(stratified_auc) - np.mean(group_auc))

    # ---------------------- 3) Öğrenme Eğrisi ---------------------------------
    LOG.info("[3/3] Öğrenme eğrisi (train-size vs AUC)…")
    train_size_oran = np.linspace(0.1, 1.0, 8)
    egitim_boyutlari, egitim_skorlari, test_skorlari = learning_curve(
        _model_olustur(), X, y, cv=5, n_jobs=1,
        train_sizes=train_size_oran, scoring="roc_auc",
        shuffle=True, random_state=config.RASTGELE_TOHUM,
    )

    # ---------------------- Görsel ---------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(20, 6))

    # Panel A: Train vs Test bar
    ax = axes[0]
    metrikler = ["AUC", "Accuracy", "F1"]
    train_vals = [train_auc, train_acc, train_f1]
    test_vals = [test_auc, test_acc, test_f1]
    x = np.arange(len(metrikler))
    w = 0.35
    ax.bar(x - w/2, train_vals, w, label="Train", color="#2563eb")
    ax.bar(x + w/2, test_vals, w, label="Test", color="#dc2626")
    for i, (tr, te) in enumerate(zip(train_vals, test_vals)):
        ax.text(i - w/2, tr + 0.01, f"{tr:.3f}", ha="center", fontsize=10)
        ax.text(i + w/2, te + 0.01, f"{te:.3f}", ha="center", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(metrikler)
    ax.set_ylim(0, 1.10)
    ax.set_title("A) Train vs Test Metrik Farkı\n(stratifiye %80/%20 ayrım)",
                 fontsize=12)
    ax.legend()

    # Panel B: Stratified vs GroupKFold box
    ax = axes[1]
    df_box = pd.DataFrame({
        "AUC": list(stratified_auc) + list(group_auc),
        "Strateji": (["Stratified-CV\n(aynı genler görülü)"] * len(stratified_auc)
                     + ["GroupKFold\n(yeni genler)"] * len(group_auc)),
    })
    sns.boxplot(data=df_box, x="Strateji", y="AUC", ax=ax,
                palette=["#2563eb", "#dc2626"], width=0.4)
    sns.stripplot(data=df_box, x="Strateji", y="AUC", ax=ax, color="black",
                  jitter=True, size=7)
    ax.set_ylim(0, 1.05)
    ax.set_title("B) CV Stratejisine Göre AUC\n(genelleme açığı testi)",
                 fontsize=12)
    ax.set_xlabel("")

    # Panel C: Learning curve
    ax = axes[2]
    train_ort = egitim_skorlari.mean(axis=1)
    train_std = egitim_skorlari.std(axis=1)
    test_ort = test_skorlari.mean(axis=1)
    test_std = test_skorlari.std(axis=1)
    ax.plot(egitim_boyutlari, train_ort, "o-", color="#2563eb",
            label="Train AUC", linewidth=2)
    ax.fill_between(egitim_boyutlari, train_ort - train_std,
                    train_ort + train_std, alpha=0.15, color="#2563eb")
    ax.plot(egitim_boyutlari, test_ort, "o-", color="#dc2626",
            label="Test AUC (CV)", linewidth=2)
    ax.fill_between(egitim_boyutlari, test_ort - test_std,
                    test_ort + test_std, alpha=0.15, color="#dc2626")
    ax.set_ylim(0.5, 1.05)
    ax.set_xlabel("Eğitim örneklem sayısı")
    ax.set_ylabel("ROC-AUC")
    ax.set_title("C) Öğrenme Eğrisi\n(daha çok veri ⇒ ne kadar fayda?)",
                 fontsize=12)
    ax.legend()

    fig.suptitle("MERGEN Overfit/Underfit Teşhis Paneli", fontsize=15, y=1.02)
    fig.tight_layout()
    yol = config.SONUC_DIZINI / "overfit_teshis.png"
    fig.savefig(yol, dpi=200, bbox_inches="tight")
    plt.close(fig)
    LOG.info("Teşhis paneli kaydedildi: %s", yol)

    # ---------------------- Karar ----------------------------------------------
    karar: dict = {
        "train_auc": float(train_auc),
        "test_auc": float(test_auc),
        "train_test_gap": float(auc_gap),
        "stratified_cv_ort": float(np.mean(stratified_auc)),
        "stratified_cv_std": float(np.std(stratified_auc)),
        "group_cv_ort": float(np.mean(group_auc)),
        "group_cv_std": float(np.std(group_auc)),
        "genelleme_acigi": float(np.mean(stratified_auc) - np.mean(group_auc)),
        "ogrenme_egrisi_son_train": float(train_ort[-1]),
        "ogrenme_egrisi_son_test": float(test_ort[-1]),
    }

    # Otomatik etiketleme — iki ayrı boyutta değerlendirme
    karar["overfit_train_test"] = "Var" if auc_gap > 0.10 else "Yok"
    if karar["genelleme_acigi"] > 0.15:
        karar["overfit_gen_kimligi"] = "Belirgin (yeni genlerde performans düşüyor)"
    elif karar["genelleme_acigi"] > 0.08:
        karar["overfit_gen_kimligi"] = "Hafif"
    else:
        karar["overfit_gen_kimligi"] = "Yok"

    if test_auc < 0.65 and train_auc < 0.70:
        karar["sonuc"] = "UNDERFIT — model yeterli karmaşıklıkta değil"
    elif train_auc > 0.99 and karar["genelleme_acigi"] > 0.15:
        karar["sonuc"] = ("OVERFIT (gen-kimliğine) — model bilinen sürücü "
                          "genlerde mükemmel, yeni genlerde performansı düşüyor. "
                          "Klinik kullanımda bilinen genler için güvenli; "
                          "rare/novel genler için ek doğrulama gerekli.")
    elif auc_gap > 0.10:
        karar["sonuc"] = "Hafif overfit — train-test farkı düşürülmeli"
    else:
        karar["sonuc"] = "SAĞLIKLI — kabul edilebilir genelleme"

    LOG.info("=" * 60)
    LOG.info("TEŞHIS: %s", karar["sonuc"])
    LOG.info("=" * 60)
    return karar


if __name__ == "__main__":
    sonuc = teshis_calistir()
    import json
    print("\n" + json.dumps(sonuc, indent=2, ensure_ascii=False))
