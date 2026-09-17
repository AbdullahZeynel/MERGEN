# 1p/19qNET — IDH-mutant gliomada 1p/19q codeletion (Astro vs Oligo)

- **Kayıt kimliği:** `1p19qnet`
- **Alan / tür:** pathology / molecular_marker_predictor
- **Köken:** external_pretrained
- **Üründeki rolü:** redundant_reference
- **Ürün kararı (2026-09-14):** `reference` — Yalnız karşılaştırma ve etiket doğrulama; üründe çalışmaz.
- **Durum:** `smoke_tested` — 1pNET, 19qNET ve lojistik birleştirici ağırlıkları indirildi; depoda lisans yok; ResNet50-ImageNet özellik hattı ile çalışır; gerçek girdiyle yerel çalıştırma kaydı smoke/ altındadır.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Belirtilmemiş (depoda LICENSE yok)
- **Kod lisansı:** Belirtilmemiş
- **Not:** Makale CC BY 4.0; makale 'pretrained models available upon request' der, depo ağırlıkları içerir.
- Kod + ağırlık: https://github.com/rogo96/1p19qNet
- Makale (PMC10505231): https://doi.org/10.1038/s41698-023-00450-4
- source_commit: `e5ae13f4b8f5b7e2aedf122f1e22c9739f8af0a6`
- retrieved: `2026-09-14`

Atıf:

- Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0)

## Mimari

DeepZoom tiling → (isteğe bağlı stain normalizasyonu) → torchvision ResNet50 (ImageNet) 1024-d özellik → 1pNET ve 19qNET (fold-change regresyonu) → lojistik model (Oligo vs Astro).

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "Severance Hospital discovery set (NGS etiketli, kapalı)",
    "patients": 288,
    "source": "Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0)"
  },
  "test": {
    "dataset": "TCGA-LGG/GBM bağımsız doğrulama (IVS)",
    "samples": 385,
    "class_counts": {
      "Oligodendroglioma": 153,
      "Astrocytoma": 232
    }
  },
  "notes": [
    "IVS TCGA olduğu için yerel kohortun IDH-mutant alt kümesiyle örtüşür; TCGA üzerinde yeni bağımsız test iddiası kurulamaz."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| 1p19q_codeletion | Discovery set (288) | Logistic model Accuracy / Precision / Recall / F1 / AUC | 0.861 / 0.944 / 0.776 / 0.850 / 0.930 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| 1p19q_codeletion | Discovery set (288) | 1pNET Accuracy / Precision / Recall / F1 / AUC | 0.884 / 0.929 / 0.840 / 0.879 / 0.921 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| 1p19q_codeletion | Discovery set (288) | 19qNET Accuracy / Precision / Recall / F1 / AUC | 0.891 / 0.940 / 0.841 / 0.885 / 0.927 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| 1p19q_codeletion | Discovery set (288) | Conventional FISH Accuracy / Precision / Recall / F1 | 0.843 / 0.978 / 0.722 / 0.831 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| 1p19q_codeletion | TCGA IVS (385) | Logistic model Accuracy / Precision / Recall / F1 / AUC | 0.725 / 0.831 / 0.386 / 0.527 / 0.837 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| 1p19q_codeletion | TCGA IVS (385) | 1pNET Accuracy / Precision / Recall / F1 / AUC | 0.777 / 0.725 / 0.706 / 0.715 / 0.833 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| 1p19q_codeletion | TCGA IVS (385) | 19qNET Accuracy / Precision / Recall / F1 / AUC | 0.766 / 0.684 / 0.765 / 0.722 / 0.837 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) (Tablo 1) |
| fold_change_regression | Discovery set | R² 1p / 19q | 0.589 / 0.547 | Kim GJ, Lee T, Ahn S, Uh Y, Kim SH. Efficient diagnosis of IDH-mutant gliomas: 1p/19qNET assesses 1p/19q codeletion status using weakly-supervised learning. npj Precis Oncol 2023;7:94. https://doi.org/10.1038/s41698-023-00450-4 (PMC10505231, CC BY 4.0) |

Not: Dış (TCGA) recall 0,386 düşüktür; GMAP 1p/19q AUROC'u (0,885 dış) daha yüksektir ve GMAP bu görevi kapsar.

## MERGEN sonuçları

Bu makinede (RTX 5060 Ti 16 GB, torch 2.14.0+cu130) yapılan yerel çalıştırma kayıtları `smoke/` altındadır. Bunlar çalışırlık, süre ve VRAM ölçümleridir; kullanılan vakalar eğitim verisiyle örtüşebildiğinden bağımsız klinik değerlendirme değildir. Ayrıntılı tablo ve grafikler `models/registry/report/REPORT.md` içindedir.

- `smoke/1p19qnet_smoke.json`: `{"n": 12, "accuracy": 0.6667, "per_class": {"A": {"n": 6, "correct": 6}, "O": {"n": 6, "correct": 2}}, "auc_codel_vs_intact": 0.9444, "precision_codel": 1.0, "recall_codel": 0.3333, "f1_codel": 0.5, "threshold": 0.5}`
- `smoke/wsi_output_demo_TCGA-HT-8108_outputs.json`
- `smoke/wsi_output_demo_TCGA-QH-A65R_outputs.json`

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| checkpoint_1pNET | `models/1p19qnet/model/1pNet_19qNet/1pNet/all/best_model_95.pth` | 252687 | `7aab623c1c9d4bc2…` | present |
| checkpoint_19qNET | `models/1p19qnet/model/1pNet_19qNet/19qNet/all/best_model_72.pth` | 252687 | `212ba965f52de794…` | present |
| checkpoint_logistic | `models/1p19qnet/model/1pNet_19qNet/logistic/all/logistic_model.pth` | 1327 | `1697eaca1b064e2c…` | present |
| upstream_readme | `models/1p19qnet/README.upstream.md` | 5853 | `437121ab249680e8…` | present |
| upstream_env | `models/1p19qnet/environment.upstream.yml` | 3571 | `e7abcdd8794ffbe0…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: Python 3.10.11, PyTorch 1.12.1, torchvision 0.13.1, openslide 3.4.1, staintools.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`python3 test_model.py --dname_1pNet 1pNet --dname_19qNet 19qNet --feat_dir <features> --max_r=100 --gpu=0` (ResNet50 özellikleri `preprocess/compute_feats.py` ile üretildikten sonra).
