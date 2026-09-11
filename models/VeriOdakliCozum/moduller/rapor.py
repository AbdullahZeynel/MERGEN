"""
Rapor Üretim Modülü
====================

Pipeline çalışmasının sonunda yazılı, gösterime hazır bir Markdown raporu
(``sonuclar/rapor.md``) üretir. Rapor:
    * Veri seti özet istatistikleri
    * Çapraz doğrulama sonuçları
    * Test seti metrikleri
    * Klasik araç karşılaştırması (SIFT, PolyPhen-2)
    * En etkili biyolojik özellikler (SHAP)
    * Üretilen görsellerin listesi
içerir.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .. import config


def _f(x, basamak: int = 4) -> str:
    """Sayıyı kısa, okunabilir Türkçe formatta basar."""
    try:
        if x is None:
            return "—"
        if isinstance(x, float) and (x != x):     # NaN
            return "—"
        return f"{float(x):.{basamak}f}"
    except Exception:
        return str(x)


def rapor_olustur(
    veri_ozeti: dict,
    cv_sonucu: dict,
    karsilastirma: dict,
    shap_top: pd.DataFrame,
    gorsel_yollari: dict[str, str],
    cikti: str = "rapor.md",
) -> str:
    """
    Pipeline çıktılarını derleyerek Markdown raporu yazar ve dosya yolunu döner.
    """
    yol = Path(config.SONUC_DIZINI) / cikti
    z = datetime.now().strftime("%Y-%m-%d %H:%M")

    mergen = karsilastirma.get("MERGEN", {})
    sift = karsilastirma.get("SIFT", {})
    pp = karsilastirma.get("PolyPhen2", {})
    mn_sift = karsilastirma.get("MERGEN_vs_SIFT_mcnemar", {})
    mn_pp = karsilastirma.get("MERGEN_vs_PolyPhen_mcnemar", {})

    # En etkili özelliklerin biyolojik yorumu
    yorumlar = {
        "esm_pathojenite": "ESM-2 evrimsel şok skoru — yüksek değer, mutasyonun "
                           "evrimsel olarak nadir/şiddetli olduğunu gösterir.",
        "esm_llr": "ESM-2 log-likelihood ratio (negatif değer ⇒ patojenite eğilimi).",
        "delta_hidrofobiklik": "Vahşi tip vs mutant arasındaki hidrofobiklik farkı; "
                                "membran/çekirdek bölgelerinde kararlılığı etkiler.",
        "delta_hacim": "Yan zincir hacim değişimi — paketleme bozulması, "
                       "domain çökmesine yol açabilir.",
        "delta_polarite": "Polarite değişimi — yüzey/iç bölge etkileşimleri.",
        "delta_yuk": "Net yük değişimi — substrat bağlanma, fosforilasyon "
                     "ve protein-protein etkileşimini etkiler.",
        "delta_izoelektrik": "Yan zincir pKa farkı — pH-bağımlı stabilite.",
        "delta_esneklik": "Yan zincir esnekliği — esnek/sert bölge değişimleri.",
        "delta_yuzey_erisim": "Yüzey erişilebilirlik farkı — gömülü mutasyonlar "
                              "katlama bozar.",
        "delta_heliks_tercihi": "α-heliks oluşturma eğiliminin değişimi.",
        "delta_beta_tercihi": "β-tabaka oluşturma eğiliminin değişimi.",
        "grantham_yakl": "Bileşik fizikokimyasal şok endeksi (Grantham yaklaşığı).",
        "cosmic_frekans_log": "COSMIC somatik popülasyon frekansı (log) — yüksek "
                              "değer, tümörlerde tekrarlayan sürücü mutasyona işaret eder.",
        "cgga_missense_frekans": "CGGA Çin glioma kohortunda (n=286) ilgili genin "
                                  "missense varyant taşıyan örnek oranı — yüksek değer "
                                  "rekürrent sürücü genleri işaret eder; bağımsız Asya "
                                  "kohortundan gelen kohort-dışı sinyal.",
        "nispi_pozisyon": "Mutasyonun protein içindeki göreceli konumu — bazı "
                          "domain'ler patojenik hotspotlar barındırır.",
    }

    satirlar: list[str] = []
    P = satirlar.append

    P("# MERGEN — Karar Destek Sistemi Çalışma Raporu")
    P("")
    P(f"**Üretim zamanı:** {z}  ")
    P("**Proje:** TEKNOFEST 2026 — Onkolojide 3T Yarışması  ")
    P("**Modül:** Veri Odaklı Çözüm (Genomik + Protein Dil Modelleri)  ")
    P("")
    P("---")
    P("")

    # 1. ÖZET
    P("## 1. Yönetici Özeti")
    P("")
    P("MERGEN, Glioblastoma (GBM) ve Düşük Dereceli Glioma (LGG) somatik "
      "missense varyantlarının **patojenitesini** çok modlu özelliklerle tahmin "
      "eden ve kararını **SHAP** ile şeffaf biçimde açıklayan bir karar destek "
      "sistemidir. Bu raporda eğitim/test seti büyüklüğü, model performansı, "
      "klasik araçlarla (SIFT, PolyPhen-2) karşılaştırma ve en belirleyici "
      "biyolojik özellikler sunulmaktadır.")
    P("")

    # 2. VERİ
    P("## 2. Veri Seti Özeti")
    P("")
    P("| Özellik | Değer |")
    P("|---|---|")
    P(f"| TCGA projeleri | {', '.join(config.TCGA_PROJELERI)} |")
    P(f"| Toplam etiketli varyant | {veri_ozeti.get('toplam', 0)} |")
    P(f"| Patojenik | {veri_ozeti.get('patojenik', 0)} |")
    P(f"| Benign | {veri_ozeti.get('benign', 0)} |")
    P(f"| Benzersiz gen sayısı | {veri_ozeti.get('gen_sayisi', 0)} |")
    P(f"| Özellik sayısı (X) | {veri_ozeti.get('ozellik_sayisi', 0)} |")
    P(f"| ESM-2 modeli | `{config.ESM_MODEL_ADI}` |")
    P("")
    P("**Veri Kaynakları:**")
    P("- **MC3 PUBLIC MAF** (`mc3.v0.2.8.PUBLIC.maf.gz`, PanCanAtlas) — TCGA-GBM "
      "ve TCGA-LGG kohortlarının 7 farklı çağrıcının ensemble birleşiminden gelen "
      "yüksek-güven somatik missense varyantları. CLIN_SIG (ClinVar), SIFT ve "
      "PolyPhen-2 alanları VEP ile zenginleştirilmiş hâlde gömülü gelir.")
    P("- **CGGA WESeq_286** — Chinese Glioma Genome Atlas, bağımsız Asya kohortu "
      "(286 hasta). Klinik veri (IDH, MGMT, sağkalım) ve gen-bazlı missense "
      "frekansı modele ek bir popülasyon sinyali olarak eklendi.")
    P("- **UniProt** (kanonik insan protein dizilimleri) — ESM-2 girdisi.")
    P("- **dbNSFP / myvariant.info** — MC3'te eksik kalan SIFT/PolyPhen "
      "skorlarını tamamlamak için yedek API çağrısı.")
    P("")

    # 3. CV
    P("## 3. Gen-Grup Çapraz Doğrulama (GroupKFold)")
    P("")
    P("Modelin **yeni genlerde** nasıl davranacağını ölçmek için "
      "**aynı gene ait varyantları aynı fold'da tutan** çapraz doğrulama uyguladık. "
      "Bu, modelin gen-spesifik aşırı uyumdan (memorization) kaçınmasını sağlar — "
      "gerçek klinik kullanımda model daha önce görmediği genlerle karşılaşacaktır. "
      "Fold-başına AUC dalgalanması yüksek olabilir; bu, bazı genlerin (örneğin "
      "TP53, IDH1) tam doğruluk verirken, az veriye sahip genlerde modelin "
      "geniş tahminler yapmak zorunda kaldığını gösterir.")
    P("")
    if cv_sonucu.get("fold_auc"):
        P("| Fold | ROC-AUC |")
        P("|---|---|")
        for i, s in enumerate(cv_sonucu["fold_auc"], 1):
            P(f"| {i} | {_f(s)} |")
        P(f"| **Ortalama** | **{_f(cv_sonucu.get('ortalama_auc'))} ± "
          f"{_f(cv_sonucu.get('std_auc'))}** |")
    else:
        P("_Yeterli grup sayısı olmadığı için CV atlandı._")
    P("")

    # 4. TEST METRİKLERİ
    P("## 4. Test Seti Performansı")
    P("")
    P("| Metrik | MERGEN | SIFT | PolyPhen-2 |")
    P("|---|---|---|---|")
    for k, ad in [("dogruluk", "Doğruluk"), ("f1", "F1-Skoru"),
                  ("precision", "Precision"), ("recall", "Recall"),
                  ("roc_auc", "ROC-AUC"), ("pr_auc", "PR-AUC")]:
        P(f"| {ad} | {_f(mergen.get(k))} | {_f(sift.get(k))} | {_f(pp.get(k))} |")
    P("")
    P(f"**dbNSFP kapsama oranı:** {_f(karsilastirma.get('dbnsfp_kapsama', 0), 3)} "
      "(myvariant.info üzerinden çekilebilen SIFT/PolyPhen skoru oranı).")
    P("")

    # 5. McNEMAR
    P("### 4.1 İstatistiksel Karşılaştırma (McNemar χ²)")
    P("")
    P("| Karşılaştırma | χ² | p-değeri | MERGEN lehine | Rakip lehine |")
    P("|---|---|---|---|---|")
    P(f"| MERGEN vs SIFT | {_f(mn_sift.get('chi2'))} | {_f(mn_sift.get('p_degeri'))} "
      f"| {mn_sift.get('a_lehine', 0)} | {mn_sift.get('b_lehine', 0)} |")
    P(f"| MERGEN vs PolyPhen-2 | {_f(mn_pp.get('chi2'))} | {_f(mn_pp.get('p_degeri'))} "
      f"| {mn_pp.get('a_lehine', 0)} | {mn_pp.get('b_lehine', 0)} |")
    P("")
    P("> Eşli McNemar testi, **aynı test kümesi üzerinde** iki modelin "
      "kararlarının istatistiksel olarak farklı olup olmadığını sınar. "
      "p < 0.05 ⇒ fark anlamlıdır.")
    P("")

    # 6. SHAP
    P("## 5. Şeffaflık — SHAP ile Özellik Önemi")
    P("")
    P("Modelin kararlarını **Kara Kutu** olmaktan çıkaran SHAP analizi, "
      "her bir tahminin hangi biyolojik nedene dayandığını ortaya koyar.")
    P("")
    P("**Global olarak en etkili 10 özellik:**")
    P("")
    P("| Özellik | Ortalama |SHAP| | Biyolojik Yorum |")
    P("|---|---|---|")
    for _, r in shap_top.iterrows():
        ad = r["ozellik"]
        P(f"| `{ad}` | {_f(r['ortalama_mutlak_shap'])} | "
          f"{yorumlar.get(ad, 'Fizikokimyasal değişim göstergesi.')} |")
    P("")

    # 7. GÖRSELLER
    P("## 6. Üretilen Görseller")
    P("")
    for ad, gorsel_yolu in gorsel_yollari.items():
        if gorsel_yolu:
            goreceli = Path(gorsel_yolu).name
            P(f"- **{ad}** — `sonuclar/{goreceli}`")
            P(f"  ![{ad}]({goreceli})")
    P("")

    # 8. ÇALIŞMA SÜRECİ
    P("## 7. Çalışma Süreci (Akış)")
    P("")
    P("```")
    P("TCGA-GBM/LGG  ──┐")
    P("ClinVar         ├── tüm_kaynaklari_birlestir()  ── pd.DataFrame (etiketli)")
    P("CIVIC           │")
    P("COSMIC          ┘")
    P("                       │")
    P("                       ▼")
    P("           on_isleme.veriyi_hazirla()")
    P("                       │")
    P("                       ▼")
    P("    ┌──────────────────────────────────┐")
    P("    │  AAindex deltaları (10 skala)    │")
    P("    │  ESM-2 zero-shot LLR             │")
    P("    │  COSMIC log-frekans              │")
    P("    └──────────────────────────────────┘")
    P("                       │")
    P("                       ▼")
    P("           XGBoost (GroupKFold + Stratify)")
    P("                       │")
    P("           ┌───────────┴───────────┐")
    P("           ▼                        ▼")
    P("    Metrikler (AUC/F1)        SHAP açıklamaları")
    P("           │                        │")
    P("           └────────┬───────────────┘")
    P("                    ▼")
    P("            sonuclar/*.png + rapor.md")
    P("```")
    P("")
    P("---")
    P("")
    P("_Bu rapor MERGEN pipeline'ı tarafından otomatik üretilmiştir._")
    P("")

    yol.write_text("\n".join(satirlar), encoding="utf-8")
    return str(yol)
