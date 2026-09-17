# Swin UNETR — BraTS 2021 fold-0 (MONAI research-contributions)

- **Kayıt kimliği:** `swin-unetr-brats21`
- **Alan / tür:** mri / segmentation_model
- **Köken:** external_pretrained
- **Üründeki rolü:** secondary_mri_expert
- **Ürün kararı (2026-09-14):** `core` — Doktor akışında kullanılır.
- **Durum:** `smoke_tested` — Fold-0 ağırlığı indirildi ve hash doğrulandı; MONAI çalışma ortamı ve smoke inference bekliyor; gerçek girdiyle yerel çalıştırma kaydı smoke/ altındadır.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Apache-2.0 (MONAI)
- **Kod lisansı:** Apache-2.0
- **Not:** MONAI research-contributions ve MONAI-extra-test-data sürüm 0.8.1.
- Kod ve README (fold tablosu): https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md
- Ağırlık sürümü: https://github.com/Project-MONAI/MONAI-extra-test-data/releases/tag/0.8.1
- Fold-0 arşivi: https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1/fold0_f48_ep300_4gpu_dice0_8854.zip
- BraTS21 fold JSON: https://developer.download.nvidia.com/assets/Clara/monai/tutorials/brats21_folds.json
- upstream_version: `MONAI-extra-test-data 0.8.1`
- retrieved: `2026-09-14`

Atıf:

- Hatamizadeh A, Nath V, Tang Y, Yang D, Roth HR, Xu D. Swin UNETR: Swin Transformers for Semantic Segmentation of Brain Tumors in MRI Images. BrainLes 2021, LNCS 12962 (2022). https://arxiv.org/abs/2201.01266
- Tang Y, Yang D, Li W, et al. Self-Supervised Pre-Training of Swin Transformers for 3D Medical Image Analysis. CVPR 2022. https://arxiv.org/abs/2111.14791
- Baid U, et al. The RSNA-ASNR-MICCAI BraTS 2021 Benchmark on Brain Tumor Segmentation and Radiogenomic Classification. arXiv:2107.02314 (2021). https://arxiv.org/abs/2107.02314

## Mimari

SwinUNETR(in_channels=4, out_channels=3, feature_size=48, use_checkpoint=True); 62,1 M parametre; ROI 128³; batch 1; AdamW lr 1e-4 warmup-cosine; 300 epoch; 4 GPU.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "BraTS 2021",
    "cases": 1251,
    "split": "brats21_folds.json ile 5 fold; her fold ≈1.000 eğitim / ≈250 doğrulama",
    "source": "https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md"
  },
  "validation": {
    "note": "README'deki Mean Dice değerleri her fold'un doğrulama bölümündedir (WT, ET, TC ortalaması)."
  },
  "notes": [
    "Yalnız fold-0 ağırlığı indirildi; diğer fold arşivleri kayıt altındadır."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| segmentation | BraTS21 fold-0 doğrulama | Mean Dice (WT/ET/TC ort.) | 0.8854 | https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md |
| segmentation | BraTS21 fold-1 doğrulama | Mean Dice | 0.9059 (ağırlık indirilmedi) | https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md |
| segmentation | BraTS21 fold-2 doğrulama | Mean Dice | 0.8981 (ağırlık indirilmedi) | https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md |
| segmentation | BraTS21 fold-3 doğrulama | Mean Dice | 0.8924 (ağırlık indirilmedi) | https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md |
| segmentation | BraTS21 fold-4 doğrulama | Mean Dice | 0.9035 (ağırlık indirilmedi) | https://github.com/Project-MONAI/research-contributions/blob/main/SwinUNETR/BRATS21/README.md |

Not: README yalnız ortalama Dice verir; sınıf bazlı WT/TC/ET, HD95 ve bağımsız test sonucu yayımlanmamıştır.

## MERGEN sonuçları

Bu makinede (RTX 5060 Ti 16 GB, torch 2.14.0+cu130) yapılan yerel çalıştırma kayıtları `smoke/` altındadır. Bunlar çalışırlık, süre ve VRAM ölçümleridir; kullanılan vakalar eğitim verisiyle örtüşebildiğinden bağımsız klinik değerlendirme değildir. Ayrıntılı tablo ve grafikler `models/registry/report/REPORT.md` içindedir.

- `smoke/swin_fold0.json`: `{"dice_TC_mean": 0.769, "dice_TC_median": 0.893, "dice_TC_n": 8, "dice_WT_mean": 0.832, "dice_WT_median": 0.8633, "dice_WT_n": 8, "dice_ET_mean": 0.8417, "dice_ET_median": 0.8294, "dice_ET_n": 7, "seconds_mean": 6.75, "peak_allocated_mib_max": 4411, "peak_reserved_mib_max": 6102}`

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| weight_archive | `models/swin-unetr-brats21/downloads/fold0_f48_ep300_4gpu_dice0_8854.zip` | 231022652 | `47ba479743f9d515…` | present |
| checkpoint_fold_0 | `models/swin-unetr-brats21/weights/fold0_f48_ep300_4gpu_dice0_8854/model.pt` | 256368326 | `1083e1585263a739…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

İndirilmeyen kardeş ağırlıklar (kayıt için):

- fold 1: https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1/fold1_f48_ep300_4gpu_dice0_9059.zip (231060053 bayt)
- fold 2: https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1/fold2_f48_ep300_4gpu_dice0_8981.zip (231010802 bayt)
- fold 3: https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1/fold3_f48_ep300_4gpu_dice0_8924.zip (231107486 bayt)
- fold 4: https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1/fold4_f48_ep300_4gpu_dice0_9035.zip (231136809 bayt)

## Yerel kod ve ortam

- `models/imaging/SwinUNETR_BRATS21/`
- `models/imaging/evaluate_uwcse.py`
- `models/imaging/asset_paths.py`
- Ortam: Gerekli: MONAI + PyTorch. Yerel `requirements.txt` eski MONAI commitini sabitlerken çağrı kodu modern SwinUNETR imzasını kullanır; izole ortamda çözülmeli.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`asset_paths.swin_model_path()` → `<MERGEN_DATA_ROOT>/models/swin-unetr-brats21/weights/fold0_f48_ep300_4gpu_dice0_8854/model.pt`.
