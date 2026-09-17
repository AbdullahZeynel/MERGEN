# nnU-Net v2 3d_fullres — BraTS 2021 (BAMF Health, Zenodo 11582627)

- **Kayıt kimliği:** `nnunet-brats21`
- **Alan / tür:** mri / segmentation_model
- **Köken:** external_pretrained
- **Üründeki rolü:** primary_mri_expert
- **Ürün kararı (2026-09-14):** `core` — Doktor akışında kullanılır.
- **Durum:** `smoke_tested` — 5 fold checkpoint indirildi ve hash doğrulandı; nnunetv2 çalışma ortamı ve gerçek vaka üzerinde uçtan uca çıkarım henüz yapılmadı; gerçek girdiyle yerel çalıştırma kaydı smoke/ altındadır.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** CC-BY-4.0 (Zenodo kaydı)
- **Kod lisansı:** Apache-2.0 (nnU-Net)
- **Not:** Atıf zorunlu: Murugesan GK, Van Oss J, McCrumb D (BAMF Health), Zenodo v1.0.0, 2024-06-11.
- Checkpoint (Zenodo v1.0.0): https://doi.org/10.5281/zenodo.11582627
- Zenodo dosyası: https://zenodo.org/records/11582627/files/Dataset002_BRATS19.zip?download=1
- nnU-Net framework: https://github.com/MIC-DKFZ/nnUNet
- upstream_version: `v1.0.0`
- archive_md5_published: `23a3f55dead4a6642271a08d1a503bbb`
- retrieved: `2026-09-14`

Atıf:

- Isensee F, Jaeger PF, Kohl SAA, Petersen J, Maier-Hein KH. nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. Nat Methods 2021;18:203–211. https://doi.org/10.1038/s41592-020-01008-z
- Baid U, et al. The RSNA-ASNR-MICCAI BraTS 2021 Benchmark on Brain Tumor Segmentation and Radiogenomic Classification. arXiv:2107.02314 (2021). https://arxiv.org/abs/2107.02314
- Murugesan GK, Van Oss J, McCrumb D. Pretrained model for 3D semantic image segmentation of the brain tumor, necrosis, and edema from MRI scans (v1.0.0). Zenodo, 2024. https://doi.org/10.5281/zenodo.11582627

## Mimari

nnU-Net v2 3d_fullres; 4 giriş kanalı (t1, t1ce, t2, flair, 1 mm izotropik, Z-score); patch 128×160×112; batch 2; 5 fold × 1000 epoch; nnUNetTrainer; test-time mirroring (0,1,2).

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "BraTS 2021 training set",
    "cases": 1251,
    "source": "Zenodo açıklaması 'trained on the BRATS 2021 dataset'; BraTS 2021 eğitim kümesi 1.251 vaka (Baid et al. 2021)",
    "split": "nnU-Net iç 5-fold çapraz doğrulama (fold başına ≈%80 eğitim / %20 doğrulama)"
  },
  "validation": {
    "note": "Her fold'un kendi doğrulama bölümü; ayrı bağımsız test kümesi Zenodo kaydında bildirilmemiştir."
  },
  "labels": {
    "0": "background",
    "1": "dataset.json adı 'edema' (predictor doğrulamasına göre BraTS NCR)",
    "2": "dataset.json adı 'nonenhancing' (predictor doğrulamasına göre BraTS ED)",
    "3": "empty (kullanılmıyor)",
    "4": "enhancing (ET)"
  },
  "notes": [
    "dataset.json 'numTraining' alanı 80.064 dosya listeler; bu kanal-bazlı dosya sayısıdır, vaka sayısı değildir.",
    "Klasör adı Dataset002_BRATS19 olsa da kaynak kaydı BraTS 2021'dir."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| segmentation | nnU-Net fold doğrulama (eğitim sırasında, pseudo-Dice) | mean final EMA foreground pseudo-Dice (5 fold ort.) | 0.8691 | checkpoint 'logging' kaydı; models/registry/nnunet-brats21/upstream_training_log.json |
| segmentation | nnU-Net fold doğrulama | final pseudo-Dice label 1 (5 fold ort.) | 0.8521 | checkpoint 'logging' |
| segmentation | nnU-Net fold doğrulama | final pseudo-Dice label 2 (5 fold ort.) | 0.8936 | checkpoint 'logging' |
| segmentation | nnU-Net fold doğrulama | final pseudo-Dice label 4 / ET (5 fold ort.) | 0.8643 | checkpoint 'logging' |

Not: Zenodo kaydı yayımlanmış WT/TC/ET Dice bildirmez. Yukarıdaki değerler checkpoint içindeki eğitim-zamanı doğrulama pseudo-Dice kayıtlarından çözülmüştür; tam hacim üzerinde bağımsız değerlendirme değildir. Fold bazlı değerler upstream_training_log.json içindedir.

## MERGEN sonuçları

Bu makinede (RTX 5060 Ti 16 GB, torch 2.14.0+cu130) yapılan yerel çalıştırma kayıtları `smoke/` altındadır. Bunlar çalışırlık, süre ve VRAM ölçümleridir; kullanılan vakalar eğitim verisiyle örtüşebildiğinden bağımsız klinik değerlendirme değildir. Ayrıntılı tablo ve grafikler `models/registry/report/REPORT.md` içindedir.

- `smoke/nnunet_folds0-1-2-3-4.json`: `{"dice_TC_mean": 0.7983, "dice_TC_median": 0.9093, "dice_TC_n": 8, "dice_WT_mean": 0.8506, "dice_WT_median": 0.8831, "dice_WT_n": 8, "dice_ET_mean": 0.7537, "dice_ET_median": 0.8489, "dice_ET_n": 8, "seconds_mean": 20.18, "peak_allocated_mib_max": 3135, "peak_reserved_mib_max": 3330}`
- `smoke/nnunet_folds0.json`: `{"dice_TC_mean": 0.8007, "dice_TC_median": 0.9072, "dice_TC_n": 8, "dice_WT_mean": 0.8581, "dice_WT_median": 0.8829, "dice_WT_n": 8, "dice_ET_mean": 0.7553, "dice_ET_median": 0.8553, "dice_ET_n": 8, "seconds_mean": 4.62, "peak_allocated_mib_max": 3135, "peak_reserved_mib_max": 3330}`

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| weight_archive | `models/nnunet-brats21/downloads/Dataset002_BRATS19.zip` | 1155915349 | `f45eff0624604333…` | present |
| checkpoint_fold_0 | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_0/checkpoint_final.pth` | 256125179 | `82261f2482f95022…` | present |
| checkpoint_fold_1 | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_1/checkpoint_final.pth` | 256125566 | `4dbab86cdfc05cc8…` | present |
| checkpoint_fold_2 | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_2/checkpoint_final.pth` | 256125758 | `2cdbd76a570e1dd8…` | present |
| checkpoint_fold_3 | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_3/checkpoint_final.pth` | 256125438 | `1ecc782979c1453c…` | present |
| checkpoint_fold_4 | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_4/checkpoint_final.pth` | 256125566 | `7343742da28ba310…` | present |
| plans | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/plans.json` | 8484 | `504b6278db2aee6b…` | present |
| dataset_json | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/dataset.json` | 11689851 | `26b3f6909a4417df…` | present |
| dataset_fingerprint | `models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/dataset_fingerprint.json` | 11370262 | `11efc1e87cccc534…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- `models/imaging/nnunet_predictor.py`
- `models/imaging/asset_paths.py`
- Ortam: Gerekli: nnunetv2 + PyTorch (CUDA 13, sm_120). Yerel venv (mergen-py314) yalnız torch/torchvision içerir; nnunetv2'nin Python 3.14 uyumu doğrulanmadı.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`models/imaging/nnunet_predictor.py` fold 0'ı yükler; `MERGEN_DATA_ROOT` altındaki weights dizinini `asset_paths.nnunet_results_root()` çözer. 5 fold ensemble için `folds=(0,1,2,3,4)` verilebilir.

## Notlar

- Çıktı kanal sırası predictor'da TC/WT/ET olarak yeniden oluşturulur (index 1=NCR, 2=ED, 4=ET).
- Bağımsız test için UCSF-PDGM'nin BraTS21-dışı vakaları planlanmıştır; yerelde henüz yok.
