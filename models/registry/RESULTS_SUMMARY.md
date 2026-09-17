# MERGEN — Rapor İçin Sayısal Sonuç Özeti

> Bu tablo yalnız **Gazi Brains 2020 çalışması öncesi** (cutoff) geçerli sonuçları içerir.
> Her satırın kaynak dosyası bu arşiv klasörüne göreli yoldur. Sayılar kaynak JSON'lardan
> programatik olarak okunmuştur, elle yazılmamıştır.

## Sonuç türü sözlüğü

| Tür | Anlamı |
|---|---|
| `locked test` | Kilitli test bölmesi; model seçimi bu veriye bakılarak yapılmadı. Raporun ana iddiası bunlardır. |
| `5-fold CV (en güvenilir tahmin)` | Out-of-fold havuz; en büyük n, en dar güven aralığı. |
| `validation` | Doğrulama bölmesi. En iyi epoch bu veride seçildiği için **iyimserdir** (ölçülen şişkinlik +0,046 makro-F1). |
| `seed repeat` | Aynı split, farklı tohum; oynaklık ölçüsü. |
| `calibration` | Eşik doğrulamada seçildi, testte bir kez okundu. |
| `smoke test` | Çalışırlık/kaynak ölçümü. Kullanılan vakalar eğitim verisiyle örtüşebilir; **performans iddiası değildir**. |
| `upstream` | Modelin kendi yayınının bildirdiği değer; bizim ölçümümüz değil. |

## Ana tablo

| Model | Veri kümesi | Bölme | n | Metrik | Değer | Tür | Kaynak dosya |
|---|---|---|---:|---|---|---|---|
| MERGEN Attention-MIL (5-fold ensemble, ÜRÜN) | TCGA-GBM/LGG WSI | test | 113 | AUROC (macro OvR) | **0.9090** | `locked test` | `mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json` |
| MERGEN Attention-MIL (5-fold ensemble, ÜRÜN) | TCGA-GBM/LGG WSI | test | 113 | MCC | **0.6957** | `locked test` | `mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json` |
| MERGEN Attention-MIL (5-fold ensemble, ÜRÜN) | TCGA-GBM/LGG WSI | test | 113 | balanced accuracy | **0.7877** | `locked test` | `mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json` |
| MERGEN Attention-MIL (5-fold ensemble, ÜRÜN) | TCGA-GBM/LGG WSI | test | 113 | macro-F1 | **0.7903 [0.708–0.863]** | `locked test` | `mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | test | 113 | AUROC (macro OvR) | **0.9034** | `locked test` | `mergen-wsi-attention-mil/results/mil_v1/eval_test.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | test | 113 | MCC | **0.6705** | `locked test` | `mergen-wsi-attention-mil/results/mil_v1/eval_test.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | test | 113 | balanced accuracy | **0.7614** | `locked test` | `mergen-wsi-attention-mil/results/mil_v1/eval_test.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | test | 113 | macro-F1 | **0.7698 [0.679–0.847]** | `locked test` | `mergen-wsi-attention-mil/results/mil_v1/eval_test.json` |
| Swin UNETR BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | Dice Mean | **0.8318** | `locked test` | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | Dice ET | **0.8564 [0.815–0.893]** | `locked test` | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | Dice Mean | **0.8659 [0.837–0.894]** | `locked test` | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | Dice TC | **0.8126 [0.762–0.861]** | `locked test` | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | Dice WT | **0.9288 [0.910–0.942]** | `locked test` | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| nnU-Net BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | Dice Mean | **0.7048** | `locked test` | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| MERGEN Attention-MIL | TCGA-GBM/LGG WSI | out-of-fold havuz | 639 | macro-F1 | **0.8269 [0.793–0.857]** | `5-fold CV (en güvenilir tahmin)` | `mergen-wsi-attention-mil/results/variance_v1/cv_v1_summary.json` |
| MERGEN Attention-MIL (ensemble) | TCGA-GBM/LGG WSI | locked test | 113 | tutulanlarda doğruluk | **0.835** | `calibration` | `…/calibration.json` |
| MERGEN Attention-MIL (ensemble) | TCGA-GBM/LGG WSI | val→test okuma | 113 | çekimserlik eşiği 0.45 · kapsam | **0.805** | `calibration` | `mergen-wsi-attention-mil/results/ensemble_cv_v1/calibration.json` |
| MERGEN Attention-MIL | TCGA-GBM/LGG WSI | val (5 tohum) | 115 | macro-F1 ort±std | **0.8639 ± 0.0199** | `seed repeat` | `mergen-wsi-attention-mil/results/variance_v1/seeds_v1_summary.json` |
| MERGEN Attention-MIL (5-tohum ensemble) | TCGA-GBM/LGG WSI | val | 115 | AUROC (macro OvR) | **0.9585** | `validation` | `mergen-wsi-attention-mil/results/ensemble_seeds_v1/eval_val.json` |
| MERGEN Attention-MIL (5-tohum ensemble) | TCGA-GBM/LGG WSI | val | 115 | MCC | **0.8375** | `validation` | `mergen-wsi-attention-mil/results/ensemble_seeds_v1/eval_val.json` |
| MERGEN Attention-MIL (5-tohum ensemble) | TCGA-GBM/LGG WSI | val | 115 | balanced accuracy | **0.8858** | `validation` | `mergen-wsi-attention-mil/results/ensemble_seeds_v1/eval_val.json` |
| MERGEN Attention-MIL (5-tohum ensemble) | TCGA-GBM/LGG WSI | val | 115 | macro-F1 | **0.8861 [0.815–0.944]** | `validation` | `mergen-wsi-attention-mil/results/ensemble_seeds_v1/eval_val.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | val | 115 | AUROC (macro OvR) | **0.9597** | `validation` | `mergen-wsi-attention-mil/results/mil_v1/eval_val.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | val | 115 | MCC | **0.8242** | `validation` | `mergen-wsi-attention-mil/results/mil_v1/eval_val.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | val | 115 | balanced accuracy | **0.8770** | `validation` | `mergen-wsi-attention-mil/results/mil_v1/eval_val.json` |
| MERGEN Attention-MIL (tek model) | TCGA-GBM/LGG WSI | val | 115 | macro-F1 | **0.8808 [0.815–0.936]** | `validation` | `mergen-wsi-attention-mil/results/mil_v1/eval_val.json` |
| Swin UNETR BraTS21 (fold 0) | MSD Task01 (BraTS türevi) | smoke | 7 | Dice ET | **0.8417** | `smoke test (eğitim örtüşmesi olabilir)` | `swin-unetr-brats21/smoke/swin_fold0.json` |
| Swin UNETR BraTS21 (fold 0) | MSD Task01 (BraTS türevi) | smoke | 8 | Dice TC | **0.7690** | `smoke test (eğitim örtüşmesi olabilir)` | `swin-unetr-brats21/smoke/swin_fold0.json` |
| Swin UNETR BraTS21 (fold 0) | MSD Task01 (BraTS türevi) | smoke | 8 | Dice WT | **0.8320** | `smoke test (eğitim örtüşmesi olabilir)` | `swin-unetr-brats21/smoke/swin_fold0.json` |
| nnU-Net BraTS21 (5 fold) | MSD Task01 (BraTS türevi) | smoke | 8 | Dice ET | **0.7537** | `smoke test (eğitim örtüşmesi olabilir)` | `nnunet-brats21/smoke/nnunet_folds0-1-2-3-4.json` |
| nnU-Net BraTS21 (5 fold) | MSD Task01 (BraTS türevi) | smoke | 8 | Dice TC | **0.7983** | `smoke test (eğitim örtüşmesi olabilir)` | `nnunet-brats21/smoke/nnunet_folds0-1-2-3-4.json` |
| nnU-Net BraTS21 (5 fold) | MSD Task01 (BraTS türevi) | smoke | 8 | Dice WT | **0.8506** | `smoke test (eğitim örtüşmesi olabilir)` | `nnunet-brats21/smoke/nnunet_folds0-1-2-3-4.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 151 | HD95 TC (mm, düşük iyi) | **2.44** (medyan 1.00) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 171 | HD95 WT (mm, düşük iyi) | **3.45** (medyan 2.00) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| UWCSE (ÜRÜN: tabakalı ağırlık + TC_MIN) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 160 | HD95 ET (mm, düşük iyi) | **1.77** (medyan 1.00) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| nnU-Net BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 117 | HD95 TC (mm, düşük iyi) | **3.60** (medyan 1.41) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| nnU-Net BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 172 | HD95 WT (mm, düşük iyi) | **3.90** (medyan 2.00) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| nnU-Net BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 120 | HD95 ET (mm, düşük iyi) | **2.60** (medyan 1.41) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| Swin UNETR BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 144 | HD95 TC (mm, düşük iyi) | **2.78** (medyan 1.00) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| Swin UNETR BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 170 | HD95 WT (mm, düşük iyi) | **5.86** (medyan 2.91) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |
| Swin UNETR BraTS21 (tek başına) | UCSF-PDGM v5 (BraTS21 dışı) | locked test | 156 | HD95 ET (mm, düşük iyi) | **1.93** (medyan 1.00) | `locked test` | `mergen-uwcse/results/hd95/hd95.json` |

> HD95 satırlarında `n` **tanımlı** vaka sayısıdır: referans ile tahminden
> yalnız biri boşsa mesafe tanımsızdır ve ortalamaya girmez. Tanımsız sayıları
> `hd95.json` içindedir (üründe TC 21 · WT 1 · ET 12; nnU-Net'te 55 · 0 · 52).

## Raporda kullanılacak başlık sayılar

**Patoloji (A/O/G sınıflandırma, TCGA WSI):**

- Ürün modeli 5-fold ensemble, **kilitli test macro-F1 0,790 [0,708–0,863]** (n=113)
- Mimarinin en güvenilir genelleme tahmini: **out-of-fold macro-F1 0,827 [0,793–0,857]** (n=639)
- Doğrulama skorları (0,86–0,89) en iyi epoch seçiminden ötürü **+0,046 şişkindir**; ürün iddiası olarak kullanılmaz

**MRI (tümör segmentasyonu, UCSF-PDGM BraTS21-dışı):**

- Ürün yapılandırması UWCSE (tabakalı ağırlık + TC_MIN), **kilitli test n=172**
- Dice: TC 0,764 · WT 0,929 · ET 0,856 · ortalama 0,866
- En iyi tek modele göre fark **+0,0053 [−0,0138, +0,0261]** — ensemble ilk kez pozitif
- **HD95 (sınır doğruluğu): TC 2,44 · WT 3,45 · ET 1,77 mm** — her üç bölgede de iki tek modelden iyi

**Önemli uyarı:** MRI ortalama Dice tek başına yanıltıcıdır. Test vakalarının üçte birinde
referansta hiç tümör çekirdeği/kontrast tutan bölge yoktur; orada Dice 'örtüşme' değil
'susabildin mi' ölçer. Ayrıntı: `mergen-uwcse/uwcse_v3/segmentation_metrics.json` içindeki
`by_region_presence` bloğu ve arşivdeki `docs/SISTEM_MIMARISI_2026-09-16.md` bölüm 5.4.

