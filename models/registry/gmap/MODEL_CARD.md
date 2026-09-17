# GMAP — H&E WSI'dan IDH / 1p/19q / TERT / +7−10 tahmini

- **Kayıt kimliği:** `gmap`
- **Alan / tür:** pathology / molecular_marker_predictor
- **Köken:** external_pretrained
- **Üründeki rolü:** phase2_candidate
- **Ürün kararı (2026-09-14):** `reference` — Yalnız karşılaştırma ve etiket doğrulama; üründe çalışmaz.
- **Durum:** `weights_verified_dependencies_gated` — 4 görev checkpointi indirildi ve hash kaydedildi; depoda lisans yok; UNI encoder (HF erişim onayı, CC-BY-NC-ND) olmadan çıkarım zinciri kurulamaz.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Belirtilmemiş (depoda LICENSE yok)
- **Kod lisansı:** Belirtilmemiş
- **Not:** Makale CC BY-NC-ND 4.0. UNI ağırlıkları CC-BY-NC-ND-4.0 ve bireysel erişim onaylıdır.
- Kod: https://github.com/Bingchao-Zhao/GMAP
- Ağırlık (Google Drive, README bağlantısı): https://drive.google.com/file/d/17X5aLFs8ZiZ9z-0Jwg-hEhg2pQAshpDo/view
- Makale: https://doi.org/10.1016/j.landig.2025.100977
- GLTrans aggregator: https://github.com/Bingchao-Zhao/MAG-GLTrans
- source_commit: `d10abeb2d660023a9bfc186e753dbb004c12a220`
- weights_archive: `GMAP.zip (2025-10-19 tarihli içerik)`
- retrieved: `2026-09-14`

Atıf:

- Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062)

## Mimari

CLAM ön işleme (20×), UNI tile özellikleri, GLTrans (Transformer) aggregator; genotip başına ayrı ikili model (IDH, 1p19q, TERT, 7g10l).

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "TCGA-GBM + TCGA-LGG",
    "wsis": 1696,
    "patients": 877,
    "label_file_distribution_877": {
      "IDH": {
        "mutant(1)": 421,
        "wildtype(0)": 381,
        "NA": 75
      },
      "1p19q": {
        "codel(1)": 162,
        "non-codel(0)": 704,
        "NA": 11
      },
      "TERT": {
        "mutant(1)": 150,
        "wildtype(0)": 151,
        "NA": 576
      },
      "+7/-10": {
        "positive(1)": 311,
        "negative(0)": 548,
        "NA": 18
      },
      "WHO_grade": {
        "G4": 440,
        "G3": 68,
        "G2": 77,
        "NA": 292
      },
      "classification": {
        "Glioblastoma": 418,
        "Astrocytoma": 287,
        "Oligodendroglioma": 162,
        "NA": 10
      }
    },
    "source": "label/total_label.csv + makale"
  },
  "validation": {
    "internal_test": {
      "wsis": 167,
      "patients": 88
    }
  },
  "test": {
    "external": {
      "wsis": 4602,
      "patients": 3147,
      "sites": "12 Çin hastanesi + EBRAINS"
    }
  },
  "notes": [
    "Yerel 762 WSI hastasının tamamı GMAP'in TCGA etiket listesindedir; yerel kohort GMAP için bağımsız test değildir."
  ]
}
```

Yerel TCGA WSI kohortu (762 hasta) ile ilişki:

```json
{
  "overlap_with_local": 762
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| IDH | iç test (88 hasta) | AUROC | 0.939 (%95 GA 0.865–0.993) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| 1p19q | iç test | AUROC | 0.955 (%95 GA 0.898–0.992) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| TERT | iç test | AUROC | 0.944 (%95 GA 0.849–1.000) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| +7/-10 | iç test | AUROC | 0.886 (%95 GA 0.802–0.955) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| IDH | dış doğrulama (3147 hasta) | AUROC | 0.87 (%95 GA 0.857–0.883) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| 1p19q | dış doğrulama | AUROC | 0.885 (%95 GA 0.865–0.905) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| TERT | dış doğrulama | AUROC | 0.694 (%95 GA 0.665–0.724) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |
| +7/-10 | dış doğrulama | AUROC | 0.672 (%95 GA 0.615–0.727) | Han C, Li D, Zhao B, et al. Molecular alterations prediction in gliomas via an interpretable deep learning model: a multicentre and retrospective study. Lancet Digit Health 2026;8(4):100977. https://doi.org/10.1016/j.landig.2025.100977 (PMID 42115062) |

Not: Makale accuracy, sensitivity, specificity ve F1 de raporlar; tam metin açık erişimli olmadığı için bu değerler buraya alınmadı.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| weight_archive | `models/gmap/downloads/GMAP.zip` | 71408335 | `264446a669988bcd…` | present |
| checkpoint_IDH | `models/gmap/weights/GMAP/IDH.ckpt` | 19336348 | `d2244f0ccceba70b…` | present |
| checkpoint_1p19q | `models/gmap/weights/GMAP/1p19q.ckpt` | 19336348 | `77682eef66f6716a…` | present |
| checkpoint_TERT | `models/gmap/weights/GMAP/TERT.ckpt` | 19336348 | `b06321a3c180459c…` | present |
| checkpoint_7g10l | `models/gmap/weights/GMAP/7g10l.ckpt` | 19336348 | `b4661581cc4566ba…` | present |
| training_labels | `models/gmap/label/total_label.csv` | 60361 | `591877dbc18f6f44…` | present |
| upstream_readme | `models/gmap/README.upstream.md` | 5587 | `914588af05f63ea8…` | present |
| upstream_requirements | `models/gmap/requirements.upstream.txt` | 340 | `801891fbef2c454a…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: Python 3.10, torch 2.4.0, pytorch-lightning 2.4.0, nystrom_attention, transformers 4.47.1; UNI özellik çıkarımı (timm) ayrı.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

Checkpointler `logs/GMAP/UNI/TCGA/<gen>/GMAP` altına konur; `python train.py --stage=test --gen_type=<IDH|1p19q|TERT|7g10l> --extractor=UNI`.
