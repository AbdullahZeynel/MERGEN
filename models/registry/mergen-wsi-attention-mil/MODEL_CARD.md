# MERGEN WSI gated Attention-MIL A/O/G

- **Kayıt kimliği:** `mergen-wsi-attention-mil`
- **Alan / tür:** pathology / slide_classifier
- **Köken:** team_trained
- **Üründeki rolü:** primary_wsi_output
- **Ürün kararı (2026-09-14):** `core` — Doktor akışında kullanılır.
- **Durum:** `trained_evaluated` — MERGEN tarafından eğitildi; test, val bölmesinde değerlendirildi (results/).
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** n/a
- **Kod lisansı:** Proje lisansı
- **Not:** Gated attention mimarisi Ilse et al. 2018'e dayanır; kod MERGEN tarafından yazılacaktır.
- WSI kaynağı (GDC): https://portal.gdc.cancer.gov/ (files API: https://api.gdc.cancer.gov/files)
- Etiket kaynağı (cBioPortal, sabit commit): https://github.com/cBioPortal/datahub/tree/04f170590dbd1ac6e49c2d334decb4dbdb4c14b9/public/lgggbm_tcga_pub
- Mimari referansı: https://github.com/AMLab-Amsterdam/AttentionDeepMIL
- retrieved: `2026-09-14`

Atıf:

- Ilse M, Tomczak JM, Welling M. Attention-based Deep Multiple Instance Learning. ICML 2018, PMLR 80:2127–2136. https://proceedings.mlr.press/v80/ilse18a.html
- Ceccarelli M, Barthel FP, Malta TM, et al. Molecular Profiling Reveals Biologically Discrete Subsets and Pathways of Progression in Diffuse Glioma. Cell 2016;164:550–563. https://doi.org/10.1016/j.cell.2015.12.028

## Mimari

768 → 256 → gated attention 128 → 3 sınıf (263.556 parametre); DINOv2 ViT-B/14 dondurulmuş. Slayt başına en fazla 8192 tile saklanır (224×224, 0,5 µm/px'e normalize), eğitimde her epoch 4096'lık rastgele alt küme, değerlendirmede tüm tile'lar. Ürün artifact'i 5 fold checkpoint'inin olasılık ortalamasıdır.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "TCGA-GBM + TCGA-LGG tanısal H&E WSI (hasta başına bir primer DX slayt)",
    "patients": 762,
    "class_counts": {
      "A": 255,
      "O": 162,
      "G": 345
    },
    "bytes": 661993519708,
    "source": "https://portal.gdc.cancer.gov/ (files API: https://api.gdc.cancer.gov/files)"
  },
  "labels": {
    "A": "IDH-mutant, 1p/19q non-codeleted (cBioPortal IDHmut-non-codel)",
    "O": "IDH-mutant, 1p/19q codeleted (IDHmut-codel)",
    "G": "IDH-wildtype ve (G4 veya +7/−10 veya TERT mutant)"
  },
  "notes": [
    "Kilitli split (splits_v1, tohum 20260914): hasta düzeyinde, sınıf×grade stratifiye, 532/115/115. QC (>=100 doku tile) sonrası kullanılabilir: 524/115/113; 758/762 slayttan embedding çıkarıldı.",
    "Etiketler TUM (760/760) ve IUCompPath (638/638) WHO2021 etiketleriyle %100 uyumludur (bkz. _evidence/tcga_overlap_analysis.json).",
    "G sınıfı: G4 vakalarda G=281, A=19, O=1 — grade ile sınıf güçlü ilişkilidir; grade-2/3 alt kümede ayrıca değerlendirme gerekir."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Bu model bir literatür başlığı yeniden üretmez; tüm sayılar MERGEN'in kendi kilitli bölmesinde ölçülmüştür. En güvenilir genelleme tahmini 5-fold OOF (n=639): macro-F1 0,827 [0,793–0,857]. Doğrulamada en iyi epoch seçimi ortalama +0,046 makro-F1 şişkinlik getirir (10 koşuda ölçüldü), bu yüzden val skorları ürün iddiası olarak kullanılmaz.

## MERGEN sonuçları

**mergen_reproduced** — bu projede eğitilen/değerlendirilen modelin kendi sonuçları (koşu kimliği ve artifact ile):

| Koşu | Bölme | n | macro-F1 | balanced acc | AUROC (OvR) | MCC | %95 GA (macro-F1) | checkpoint epoch |
|---|---|---:|---:|---:|---:|---:|---|---:|
| ensemble_cv_v1 | test | 113 | 0.790 | 0.788 | 0.909 | 0.696 | 0.708–0.863 | – |
| ensemble_seeds_v1 | val | 115 | 0.886 | 0.886 | 0.958 | 0.837 | 0.815–0.944 | – |
| mil_v1 | test | 113 | 0.770 | 0.761 | 0.903 | 0.671 | 0.679–0.847 | 23 |
| mil_v1 | val | 115 | 0.881 | 0.877 | 0.960 | 0.824 | 0.815–0.936 | 23 |

Ayrıntılar (config, epoch logu, tahmin CSV'si, karışıklık matrisi) `results/<koşu>/` altındadır. Tek model ağırlığı veri kökünde `pathology/runs/<koşu>/best.pt` (SHA-256 `results/<koşu>/best.pt.sha256`); `ensemble_cv_v1` beş fold checkpoint'inin olasılık ortalamasıdır (SHA-256 listesi `results/ensemble_cv_v1/fold_checkpoints.sha256`).

**Varyans ve çapraz doğrulama** — aynı mimarinin tekrarlanabilirliği; hiçbiri test bölmesine dokunmaz:

| Koşu | Ne ölçer | n | macro-F1 |
|---|---|---:|---|
| seeds_v1 | kilitli split, 5 tohum (val) | 115 | 0.864 ± 0.020 |
| seeds_v1 ensemble | 5 tohumun olasılık ortalaması (val) | 115 | 0.886 |
| cv_v1 (tohum 1) | 5-fold, fold başına | 127 | 0.826 ± 0.023 |
| cv_v1 (tohum 1) | **out-of-fold havuz — en güvenilir tahmin** | 639 | **0.827** [0.793–0.857] |

Doğrulama skorları en iyi epoch'un kendi doğrulama verisinde seçilmesinden ötürü şişkindir; bu şişkinlik eğitim loglarından ölçüldü (en iyi epoch eksi 10. epoch sonrasının medyanı): 10 koşuda **+0,046 ± 0,014** makro-F1. OOF 0,827'den bu düşülünce ≈0,78 kalır ve kilitli testte ölçülen 0,770 (tek model) / 0,790 (ensemble) ile örtüşür.

`ensemble_val.INVALID_train_overlap.json`: k-fold modelleri train+val havuzunda eğitildiği için doğrulama bölmesinde değerlendirilmeleri sızıntıdır (115 val hastasının tamamı 5 modelden 4'ünün eğitim setinde). O koşunun ürettiği 0,923 geçersizdir ve yalnız kayıt olarak saklanır; `ensemble_eval.py` artık bu durumu tespit edip reddeder.

Bu makinede (RTX 5060 Ti 16 GB, torch 2.14.0+cu130) yapılan yerel çalıştırma kayıtları `smoke/` altındadır. Bunlar çalışırlık, süre ve VRAM ölçümleridir; kullanılan vakalar eğitim verisiyle örtüşebildiğinden bağımsız klinik değerlendirme değildir. Ayrıntılı tablo ve grafikler `models/registry/report/REPORT.md` içindedir.

- `smoke/attention_mil_train_benchmark.json`
- `smoke/preflight_report.json`

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| cohort_manifest | `pathology/datasets/tcga_glioma/manifests/cohort.tsv` | 180478 | `f8308659a4386e19…` | present |
| gdc_manifest | `pathology/datasets/tcga_glioma/manifests/gdc_manifest_full.txt` | 117562 | `4ba5a17e8a53645f…` | present |
| labels | `pathology/datasets/tcga_glioma/metadata/data_clinical_sample.txt` | 374033 | `cf622c83218f6a1a…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- `models/pathology/scripts/build_gdc_manifest.py`
- `models/pathology/scripts/download_watchdog.py`
- Ortam: OpenSlide + torch (mergen-py314) gerekir; openslide-python henüz kurulmadı.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

Planlanan: QC → tile koordinatları → DINOv2 embedding (fp16) → MIL eğitimi (resume destekli) → kilitli test.

## Notlar

- WSI ham verisi 762 dosya / 616,53 GiB; dosya bazlı MD5 doğrulaması GDC istemcisi tarafından indirme sırasında yapıldı.
