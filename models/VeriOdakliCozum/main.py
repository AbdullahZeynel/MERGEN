"""
MERGEN Veri Odaklı Çözüm — Pipeline Orkestratörü
=================================================

TEKNOFEST 2026 Onkolojide 3T projesinin makine öğrenmesi tarafının uçtan
uca yürütüm betiği. Çalıştırma:

    cd VeriOdakliCozum
    python -m main                    # tam pipeline
    python -m main --esm-yok          # ESM-2'yi atla (donanım kısıtı)
    python -m main --maks 200         # daha küçük veri seti

Aşamalar:
    1) Veri indirme (TCGA + ClinVar + CIVIC + COSMIC)
    2) Ön işleme (HGVSp parse, etiket, UniProt dizilim)
    3) Özellik çıkarımı (AAindex + ESM-2)
    4) GBDT eğitimi + GroupKFold çapraz doğrulama
    5) Değerlendirme + dbNSFP karşılaştırması (SIFT, PolyPhen-2)
    6) SHAP açıklanabilirlik
    7) Görsel + rapor üretimi (sonuclar/)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Modül paketi olarak çalışsın diye proje kökünü path'e ekle
PROJE_KOKU = Path(__file__).resolve().parent
if str(PROJE_KOKU.parent) not in sys.path:
    sys.path.insert(0, str(PROJE_KOKU.parent))

from VeriOdakliCozum import config                                       # noqa: E402
from VeriOdakliCozum.moduller import (                                   # noqa: E402
    degerlendirme,
    gorseller,
    model_egitim,
    on_isleme,
    ozellik_cikarimi,
    rapor,
    shap_analiz,
    veri_indirme,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
LOG = logging.getLogger("MERGEN")


def argumanlari_ayristir() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MERGEN veri odaklı çözüm pipeline")
    p.add_argument("--esm-yok", action="store_true",
                   help="ESM-2 inference adımını atla (CPU sınırlı sistemler için)")
    p.add_argument("--maks", type=int, default=config.MAKS_VARYANT_SAYISI,
                   help="Maksimum varyant sayısı (varsayılan: %(default)s)")
    p.add_argument("--shap-yok", action="store_true",
                   help="SHAP analiz adımını atla")
    return p.parse_args()


def main() -> None:
    arg = argumanlari_ayristir()
    config.MAKS_VARYANT_SAYISI = arg.maks      # runtime override

    LOG.info("=" * 70)
    LOG.info("MERGEN Veri Odaklı Çözüm — Pipeline başlatılıyor")
    LOG.info("=" * 70)

    # --------------------------------------------------------------- 1) VERI
    LOG.info("[1/7] Veri kaynaklarından çekiliyor…")
    ham = veri_indirme.tum_kaynaklari_birlestir()

    # --------------------------------------------------------------- 2) ÖN İŞLEME
    LOG.info("[2/7] Ön işleme (HGVSp + UniProt + etiketleme)…")
    on_islenmis = on_isleme.veriyi_hazirla(ham)
    if len(on_islenmis) < 20:
        LOG.error("Etiketli varyant sayısı yetersiz (%d). "
                  "Pipeline durduruluyor.", len(on_islenmis))
        sys.exit(1)

    # --------------------------------------------------------------- 3) ÖZELLİK
    LOG.info("[3/7] Çok modlu özellik çıkarımı…")
    matris = ozellik_cikarimi.ozellik_matrisi_olustur(
        on_islenmis, esm_kullan=not arg.esm_yok,
    )
    matris.to_csv(config.VERI_DIZINI / "ozellik_matrisi.csv", index=False)

    X, y, gruplar = model_egitim.ozellikleri_ayir(matris)

    # --------------------------------------------------------------- 4) CV + EĞİTİM
    LOG.info("[4/7] Gen-grup çapraz doğrulama (GroupKFold)…")
    cv_sonucu = model_egitim.capraz_dogrulama_yap(X, y, gruplar)

    LOG.info("[5/7] Son model eğitiliyor (stratifiye train/test)…")
    model, bilgi = model_egitim.son_modeli_egit(X, y)

    # --------------------------------------------------------------- 5) DEĞERLENDIRME
    LOG.info("[6/7] Klasik araç karşılaştırması (SIFT, PolyPhen-2)…")
    iz_kolonlari = ["gen", "protein_degisim", "etiket"]
    for ek in ("mc3_sift_skor", "mc3_polyphen_skor"):
        if ek in matris.columns:
            iz_kolonlari.append(ek)
    test_iz = matris.loc[bilgi["X_test"].index, iz_kolonlari].reset_index(drop=True)
    klasik = degerlendirme.klasik_arac_karsilastirmasi(test_iz)
    karsilastirma = degerlendirme.tam_karsilastirma_raporu(
        bilgi["y_test"].values, bilgi["test_olasiliklar"], klasik,
    )

    # --------------------------------------------------------------- 6) SHAP
    if not arg.shap_yok:
        LOG.info("[7/7] SHAP açıklanabilirlik analizi…")
        aciklama = shap_analiz.shap_acikla(model, bilgi["X_test"])
        shap_top = shap_analiz.en_etkili_ozellikler(aciklama, n=10)
    else:
        aciklama = None
        shap_top = None

    # --------------------------------------------------------------- 7) GÖRSEL + RAPOR
    LOG.info("Görseller üretiliyor…")
    olasilik_haritasi = {
        "MERGEN": bilgi["test_olasiliklar"],
        "SIFT": 1.0 - klasik["sift_skor"].values,
        "PolyPhen2": klasik["polyphen_skor"].values,
    }
    yollar = {
        "ROC karşılaştırma": gorseller.roc_egrisi_ciz(
            bilgi["y_test"].values, olasilik_haritasi
        ),
        "Precision-Recall": gorseller.pr_egrisi_ciz(
            bilgi["y_test"].values, olasilik_haritasi
        ),
        "Karışıklık matrisi": gorseller.karisiklik_matrisi_ciz(
            bilgi["y_test"].values, bilgi["test_tahminler"]
        ),
        "Metrik karşılaştırma": gorseller.metrik_kar_grafigi(karsilastirma),
        "CV kutu grafiği": gorseller.cv_kutu_grafigi(cv_sonucu.get("fold_auc", [])),
    }
    if aciklama is not None:
        yollar["SHAP özet"] = gorseller.shap_ozet_ciz(aciklama)
        yollar["SHAP bar"] = gorseller.shap_bar_ciz(aciklama)
        try:
            yollar["SHAP karar"] = gorseller.shap_karar_ciz(aciklama)
        except Exception as exc:
            LOG.warning("SHAP karar grafiği üretilemedi: %s", exc)

    LOG.info("Rapor yazılıyor…")
    veri_ozeti = {
        "toplam": int(len(matris)),
        "patojenik": int((matris["etiket"] == 1).sum()),
        "benign": int((matris["etiket"] == 0).sum()),
        "gen_sayisi": int(matris["gen"].nunique()),
        "ozellik_sayisi": int(X.shape[1]),
    }
    if shap_top is None:
        import pandas as pd
        shap_top = pd.DataFrame(columns=["ozellik", "ortalama_mutlak_shap"])

    rapor_yolu = rapor.rapor_olustur(
        veri_ozeti=veri_ozeti,
        cv_sonucu=cv_sonucu,
        karsilastirma=karsilastirma,
        shap_top=shap_top,
        gorsel_yollari=yollar,
    )

    LOG.info("=" * 70)
    LOG.info("Pipeline tamamlandı.")
    LOG.info("  Rapor : %s", rapor_yolu)
    LOG.info("  Model : %s", bilgi["model_yolu"])
    LOG.info("  Görseller: %s", config.SONUC_DIZINI)
    LOG.info("=" * 70)


if __name__ == "__main__":
    main()
