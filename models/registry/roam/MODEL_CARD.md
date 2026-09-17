# ROAM — büyük ROI + piramit transformer ile glioma alt tip/derece

- **Kayıt kimliği:** `roam`
- **Alan / tür:** pathology / subtype_classifier
- **Köken:** external_pretrained
- **Üründeki rolü:** offline_reference
- **Ürün kararı (2026-09-14):** `reference` — Yalnız karşılaştırma ve etiket doğrulama; üründe çalışmaz.
- **Durum:** `weights_verified` — 5 split checkpointi Google Drive'dan indirildi (GPL-3.0); sınıf indeks anlamları ve eski bağımlılıklar çalıştırmadan önce doğrulanmalı.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** GPL-3.0 (depo LICENSE)
- **Kod lisansı:** GPL-3.0
- **Not:** GPL-3.0 kodla türev dağıtım yapılırsa lisans yükümlülükleri doğar; ürün paketine alınmadan önce hukuki değerlendirme gerekir.
- Kod: https://github.com/whiteyunjie/ROAM
- Checkpointler (Google Drive): https://drive.google.com/drive/folders/1fi_OWsR9jlmFgx2uBdPOO5vwsHAy4WH8
- Makale: https://doi.org/10.1038/s42256-024-00868-w
- source_commit: `2c8414c2aa2d43d293bf6d45be37382fcc90530b`
- retrieved: `2026-09-14`

Atıf:

- Jiang R, Yin X, Yang P, et al. A transformer-based weakly supervised computational pathology method for clinical-grade diagnosis and molecular marker discovery of gliomas. Nat Mach Intell 2024;6:876–891. https://doi.org/10.1038/s42256-024-00868-w

## Mimari

2048×2048 ROI (20×), ROI içinde 256×256 patch'ler 20×/10×/5× üç ölçekte ImageNet-ResNet50 (+stain norm) özellikleri (84×d), piramit transformer, ROI dropout/denetim; 5-fold ensemble.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "Xiangya Hospital in-house (kapalı)",
    "slides_total": 1109,
    "subtyping_task_slides": 193,
    "training_class_weights_cls_weights": [
      281,
      119,
      111
    ],
    "source": "Jiang R, Yin X, Yang P, et al. A transformer-based weakly supervised computational pathology method for clinical-grade diagnosis and molecular marker discovery of gliomas. Nat Mach Intell 2024;6:876–891. https://doi.org/10.1038/s42256-024-00868-w / ROAM/parse_config.py"
  },
  "test": {
    "dataset": "TCGA dış doğrulama",
    "slides": 618,
    "note": "Depoda 2 sınıflı (astro vs oligo) TCGA dış görevi tanımlıdır; 3 sınıflı A/O/G dış testi depoda yoktur."
  },
  "notes": [
    "Depodaki 'int_glioma_tumor_subtyping' etiket eşlemesi {2:0,3:1,4:2}; hangi indeksin astro/oligo/GBM olduğu data_prepare/data_csv üzerinden doğrulanmalıdır."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| glioma_subtyping_3class | Xiangya in-house test (depo örnek sonucu, seed s1) | Accuracy | 0.8519 | https://github.com/whiteyunjie/ROAM (ROAM/results/.../s1/visual_res/metrics.json) |
| glioma_subtyping_3class | Xiangya in-house test (s1) | Precision (macro) | 0.8524 | https://github.com/whiteyunjie/ROAM (metrics.json) |
| glioma_subtyping_3class | Xiangya in-house test (s1) | Recall (macro) | 0.8325 | https://github.com/whiteyunjie/ROAM (metrics.json) |
| glioma_subtyping_3class | Xiangya in-house test (s1) | F1 (macro) | 0.8417 | https://github.com/whiteyunjie/ROAM (metrics.json) |
| glioma_subtyping_3class | Xiangya in-house test (s1) | Balanced accuracy | 0.8325 | https://github.com/whiteyunjie/ROAM (metrics.json) |

Not: Makaledeki AUC değerleri (ör. alt tip AUC) tam metin erişimi olmadığı için buraya alınmadı; yalnız depodaki sonuç dosyaları kullanıldı.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| checkpoint_split_0 | `models/roam/checkpoints/ROAM_split0.pth` | 35168473 | `694629e4ac005466…` | present |
| checkpoint_split_1 | `models/roam/checkpoints/ROAM_split1.pth` | 35168473 | `7d30a3ab53265143…` | present |
| checkpoint_split_2 | `models/roam/checkpoints/ROAM_split2.pth` | 35168473 | `9897385308297ee0…` | present |
| checkpoint_split_3 | `models/roam/checkpoints/ROAM_split3.pth` | 35168473 | `a6b6d0f30c164b9a…` | present |
| checkpoint_split_4 | `models/roam/checkpoints/ROAM_split4.pth` | 35168473 | `50aa7cc9350e55a1…` | present |
| license | `models/roam/LICENSE` | 35149 | `3972dc9744f6499f…` | present |
| upstream_readme | `models/roam/README.upstream.md` | 19161 | `ff9b0e463598de96…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: Python 3.8.13, PyTorch 1.12.1, openslide 3.4.1, h5py 3.6.0, spams 2.6.5.4 (eski yığın; izole ortam). <!-- repo-guard: allow: sürüm numarası -->

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

Checkpointler `results/int_glioma_tumor_subtyping/<exp_code>/s1/ROAM_split{0..4}.pth` yerleşimine konur; `sh int_glioma_tumor_subtyping_test.sh`.
