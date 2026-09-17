# TUM Radio-Path MoE/Mamba — WHO2021 glioma subtyping (A/O/G)

- **Kayıt kimliği:** `tum-radio-path-moe-mamba`
- **Alan / tür:** multimodal / subtype_classifier
- **Köken:** external_pretrained
- **Üründeki rolü:** ready_aog_candidate
- **Ürün kararı (2026-09-14):** `conditional` — Erişim/lisans koşulu sağlanınca devreye alınır.
- **Durum:** `weights_verified_dependencies_gated` — 10 MoE checkpointi ve meta veriler indirildi; depoda lisans dosyası yok; çıkarım için Prov-GigaPath (HF erişim onayı) + MM-DINOv2 + mamba-ssm gerekir.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Belirtilmemiş (depoda LICENSE yok)
- **Kod lisansı:** Belirtilmemiş
- **Not:** Makale CC BY 4.0; kod/ağırlık için yazarlardan yazılı izin alınmadan dağıtım yapılmamalı.
- Kod + checkpoint: https://github.com/csaueres/radio-path-glioma-subtyping
- Makale (PMC12996459): https://doi.org/10.1038/s41698-026-01366-5
- source_commit: `ac1b53b4cdd987fa09661e03cdfbf4603da8b23a`
- retrieved: `2026-09-14`

Atıf:

- Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0)

## Mimari

Mixture-of-Experts: histoloji uzmanı (MambaMIL, GigaPath 1536-d patch embedding) + MRI uzmanı (MambaMIL, MM-DINOv2 768-d) + gating; 10 fold checkpoint (s_0..s_9, ≈1,1 MB); <1 M parametre.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "unpaired_cases": 1732,
    "wsi": {
      "EBRAINS": {
        "Glioblastoma": 497,
        "Astrocytoma": 132,
        "Oligodendroglioma": 157,
        "source": "Makale Tablo 1"
      }
    },
    "mri": {
      "UCSF-PDGM": {
        "Glioblastoma": 398,
        "Astrocytoma": 84,
        "Oligodendroglioma": 15
      },
      "EGD": {
        "Glioblastoma": 249,
        "Astrocytoma": 62,
        "Oligodendroglioma": 58
      },
      "source": "Makale Tablo 1"
    },
    "repo_train_cases_csv": {
      "cases": 1732,
      "labels": {
        "gbm": 1196,
        "astro": 292,
        "oligo": 244
      },
      "mri_only": 959,
      "wsi_only": 773
    },
    "split": "10 fold (5 fold × 2 tekrar) çapraz doğrulama; TCGA tamamen dışarıda tutuldu"
  },
  "test": {
    "dataset": "TCGA (hasta-eşleşmiş MRI+WSI)",
    "cases": 171,
    "class_counts_paper": {
      "Glioblastoma": 86,
      "Astrocytoma": 55,
      "Oligodendroglioma": 30
    },
    "class_counts_repo_csv": {
      "gbm": 95,
      "astro": 55,
      "oligo": 21
    },
    "note": "Makale Tablo 1 ile depo tcga_paired.csv sayıları farklıdır; ikisi de kaydedildi."
  },
  "notes": [
    "Prov-GigaPath EBRAINS veya TCGA üzerinde eğitilmemiştir (makale).",
    "Yerel 762 WSI kohortunun 760'ı TUM'un TCGA histoloji listesinde, 170'i 171 kişilik test kümesindedir; etiketler 760/760 uyumludur."
  ]
}
```

Yerel TCGA WSI kohortu (762 hasta) ile ilişki:

```json
{
  "overlap_with_local": {
    "tcga_histology_cases": 760,
    "paired_test_cases": 170
  },
  "label_agreement_with_local": {
    "A->A": 255,
    "G->G": 343,
    "O->O": 162
  },
  "label_disagreements": []
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| aog_subtyping | 10-fold çapraz doğrulama | AUC (MM-MoE) | 0.98 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (özet) |
| aog_subtyping | TCGA bağımsız test (171) | AUC (MM-MoE) | 0.94 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (özet) |
| aog_subtyping | 10-fold çapraz doğrulama | Balanced accuracy | 0.91 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tartışma) |
| aog_subtyping | TCGA bağımsız test (171) | Balanced accuracy | 0.8 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tartışma) |
| aog_subtyping | TCGA bağımsız test (171) | Accuracy (MM-MoE, genel) | 0.85 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Sonuçlar) |
| aog_subtyping | TCGA bağımsız test (171) | MCC MM-MoE | 0.73 ± 0.05 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) |
| aog_subtyping | TCGA bağımsız test (171) | MCC MM-EF | 0.71 ± 0.02 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) |
| aog_subtyping | TCGA bağımsız test (171) | MCC MM-LF | 0.7 ± 0.07 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) |
| aog_subtyping | TCGA bağımsız test (171) | MCC UM-WSI (yalnız histoloji) | 0.67 ± 0.04 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) |
| aog_subtyping | TCGA bağımsız test (171) | MCC UM-MRI (yalnız MRI) | 0.51 ± 0.06 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) |
| aog_subtyping | TCGA test, histoloji-uyumlu GBM (78) | Accuracy UM-WSI / MoE-WSI / MoE-MM | 0.87±0.08 / 0.88±0.07 / 0.94±0.04 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tablo 2) |
| aog_subtyping | TCGA test, histoloji-uyumlu Astro (21) | Accuracy UM-WSI / MoE-WSI / MoE-MM | 0.75±0.11 / 0.61±0.12 / 0.73±0.09 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tablo 2) |
| aog_subtyping | TCGA test, histoloji-uyumlu Oligo (20) | Accuracy UM-WSI / MoE-WSI / MoE-MM | 0.72±0.06 / 0.69±0.03 / 0.69±0.05 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tablo 2) |
| aog_subtyping | TCGA test, uyumlu vakalar (119) | Accuracy UM-MRI / UM-WSI / MoE-MRI / MoE-WSI / MoE-MM | 0.73±0.07 / 0.83±0.08 / 0.72±0.06 / 0.80±0.07 / 0.86±0.05 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tablo 2) |
| aog_subtyping | TCGA test, WHO21 ile güncellenen vakalar (52) | Accuracy UM-MRI / UM-WSI / MoE-MRI / MoE-WSI / MoE-MM | 0.68±0.06 / 0.75±0.11 / 0.65±0.05 / 0.77±0.10 / 0.82±0.07 | Saueressig C, Scholz D, Raffler P, Delbridge C, Wiestler B, Schüffler P. Multimodal fusion of pathology and radiology foundation models for WHO 2021 glioma subtyping. npj Precis Oncol 2026;10:118. https://doi.org/10.1038/s41698-026-01366-5 (PMC12996459, CC BY 4.0) (Tablo 2) |

Not: Tablo S1'deki tam AUC/accuracy/BA dökümü makale ekinde olup burada doğrulanmadı. Değerler 10 fold üzerinden ortalama ± std'dir.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| checkpoint_fold_0 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_0_checkpoint.pt` | 1099444 | `48919cc1de823803…` | present |
| checkpoint_fold_1 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_1_checkpoint.pt` | 1099444 | `1dadc51275d8b96c…` | present |
| checkpoint_fold_2 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_2_checkpoint.pt` | 1099444 | `355b586d5489c265…` | present |
| checkpoint_fold_3 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_3_checkpoint.pt` | 1099444 | `20674aff13370fe3…` | present |
| checkpoint_fold_4 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_4_checkpoint.pt` | 1099444 | `b1e105f31b518743…` | present |
| checkpoint_fold_5 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_5_checkpoint.pt` | 1099444 | `cb4bb50ddf9de9c2…` | present |
| checkpoint_fold_6 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_6_checkpoint.pt` | 1099444 | `8202d858c4e9606f…` | present |
| checkpoint_fold_7 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_7_checkpoint.pt` | 1099444 | `6143e4b50f3462c0…` | present |
| checkpoint_fold_8 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_8_checkpoint.pt` | 1099444 | `aeefedb09e041e75…` | present |
| checkpoint_fold_9 | `models/tum-radio-path-moe-mamba/ckpt/moe-mamba/s_9_checkpoint.pt` | 1099444 | `4615e867d60b3a0a…` | present |
| metadata_csv | `models/tum-radio-path-moe-mamba/metadata/histo_tcga.csv` | 159229 | `d0f3aa67b3fbdfa1…` | present |
| metadata_csv | `models/tum-radio-path-moe-mamba/metadata/histo_ebrains.csv` | 36681 | `98ba2c7043e7a38a…` | present |
| metadata_csv | `models/tum-radio-path-moe-mamba/metadata/mri.csv` | 49887 | `1f4eae2b467193c4…` | present |
| metadata_csv | `models/tum-radio-path-moe-mamba/metadata/tcga_paired.csv` | 5147 | `f51c560abf0c79ee…` | present |
| metadata_csv | `models/tum-radio-path-moe-mamba/metadata/train_cases.csv` | 47474 | `e02716c9c830f292…` | present |
| split_csv | `models/tum-radio-path-moe-mamba/metadata/splits/train_cases_5f/split_0.csv` | 17657 | `7f3be45233554b53…` | present |
| split_csv | `models/tum-radio-path-moe-mamba/metadata/splits/train_cases_5f/split_1.csv` | 17643 | `eed6eba05abb842b…` | present |
| split_csv | `models/tum-radio-path-moe-mamba/metadata/splits/train_cases_5f/split_2.csv` | 17641 | `eada10b3126878a1…` | present |
| split_csv | `models/tum-radio-path-moe-mamba/metadata/splits/train_cases_5f/split_3.csv` | 17641 | `3c28f3429627f2ec…` | present |
| split_csv | `models/tum-radio-path-moe-mamba/metadata/splits/train_cases_5f/split_4.csv` | 17647 | `555764268310ae53…` | present |
| upstream_readme | `models/tum-radio-path-moe-mamba/README.upstream.md` | 3751 | `90dc5f2513097b2b…` | present |
| upstream_env | `models/tum-radio-path-moe-mamba/env.upstream.yml` | 453 | `e0ae82ee8ac95c8f…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: Python 3.10, PyTorch 2.2 + CUDA 11.8, mamba-ssm (derleme gerekir), transformers<5; embeddingler için Prov-GigaPath (HF gated) ve MM-DINOv2.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`python eval.py --checkpoint_dir ckpt/moe-mamba --model_type moe_mamba --k 10 --n_heads 3 --histo_embed_dim 1536 --mri_embed_dim 768 ...` (GigaPath .h5 ve MM-DINOv2 .pth embeddingleri hazırlandıktan sonra). Yalnız WSI için `--model_type histo_mamba` ve ayrı checkpoint gerekir; depoda yalnız MoE checkpointleri vardır.

## Notlar

- TUM TCGA'yı eğitimde kullanmadığı için yerel TCGA kohortu bu model için gerçek dış test olabilir; ancak 170 vaka zaten yayımlanan test kümesidir.
