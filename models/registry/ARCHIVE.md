# MERGEN — Onkolojide 3T Raporu Teknik Kaynak Paketi

> **Depoya alınış (17 Eylül 2026).** Bu belge, GPU hostundan gelen dondurulmuş kanıt
> arşivinin (`onkolojide3T_modelsAndAnalysis`) kök README'sidir. Arşivin metin ve JSON
> dosyaları `models/registry/` altına aşağıdaki eşlemeyle alındı; yollar buna göre
> yeniden yazıldı. Figürler, PDF ve vaka klasörleri Git dışıdır: `<EVIDENCE_ROOT>` =
> `.local/evidence-2026-09-17/` (bkz. `docs/LOCAL_ASSETS.md`). Betikler M2 sprintinde
> `models/imaging/` ve `models/pathology/` altına alınır.
>
> | Arşiv | Depo |
> |---|---|
> | `02_mri/nnunet`, `02_mri/swin_unetr`, `02_mri/uwcse` | `nnunet-brats21/`, `swin-unetr-brats21/`, `mergen-uwcse/` |
> | `03_wsi/dinov2`, `03_wsi/attention_mil` | `dinov2-vitb14/`, `mergen-wsi-attention-mil/` |
> | `04_training_results/*`, `05_evaluation_results/*` | ilgili bileşenin `training/`, `results/` alt dizini; smoke → `smoke/` |
> | `07_model_inventory/*` | bu dizinin kökü ve `<model-id>/` kartları |
> | `08_legacy_removed_model`, `09_invalid_results` | `legacy-esm2-xgboost/`, `invalid/` |
> | `01_system_overview/*` | `report/`, `docs/MODEL_INTEGRATION_PLAN.md`, `docs/SISTEM_MIMARISI_2026-09-16.md` |

Bu klasör, **Gazi Brains 2020 çalışmasına başlamadan önceki** MERGEN sistem durumunun
dondurulmuş teknik kanıt deposudur. Rapordaki her sayısal iddianın kaynağı buradadır.

**Kapsam sınırı (cutoff):** Gazi Brains 2020 veri kümesiyle yapılan benchmark, ön işleme
düzeltmesi, 3B/2B ince ayar ve bunlara dayanan hiçbir karar bu arşivde **yoktur**. Bunlar
geçersiz değil, kapsam dışıdır; canlı depoda dururlar.

Dosyalar kopyalanmıştır — kaynak proje dosyaları taşınmadı veya silinmedi.

---

## 1. Final sistem bileşenleri

MERGEN iki bağımsız görüntü kolundan oluşur ve bunlar bir vaka nesnesinde birleşir. Doktora
**ölçülen** (laboratuvar) ile **tahmin edilen** (model) ayrı gösterilir.

| Kol | Bileşen | Rolü | Durum |
|---|---|---|---|
| MRI | nnU-Net BraTS21 (5 fold) | birincil segmentasyon uzmanı | hazır, ölçüldü |
| MRI | Swin UNETR BraTS21 | ikincil segmentasyon uzmanı | hazır, ölçüldü |
| MRI | **UWCSE** | iki uzmanı birleştiren **kural** (ağ değil, 3 katsayı) | katsayılar sabitlendi |
| WSI | DINOv2 ViT-B/14 | dondurulmuş kare kodlayıcı | hazır |
| WSI | **MERGEN Gated Attention-MIL** | A/O/G sınıflandırıcı, 5-fold ensemble | **bizim eğittiğimiz**, donduruldu |

Ürün çıktısı iki sözleşmedir: MRI tarafında tümör maskesi + hacim + belirsizlik +
`review_flags`, patoloji tarafında A/O/G olasılığı + attention ısı haritası + güven bayrağı.

## 2. Hangi modeller hazır alındı, hangileri bizim

**Hazır (pretrained, dışarıdan):**
- nnU-Net BraTS21 — Zenodo, BraTS 2021 yarışma ağırlıkları
- Swin UNETR BraTS21 — MONAI
- DINOv2 ViT-B/14 — Meta AI, dondurulmuş, hiç eğitilmedi

**MERGEN tarafından üretilen:**
- **MERGEN Gated Attention-MIL** — 263.556 parametre, TCGA WSI üzerinde sıfırdan eğitildi
- **UWCSE katsayıları** — TC 0,425 / WT 0,697 / ET 0,447, UCSF-PDGM doğrulama vakalarında ölçüldü
- **TC_MIN = 250 kuralı** ve **`review_flags`** çekirdek güvenilirlik bayrağı
- Tüm veri hattı: split, QC, embedding çıkarımı, eğitim, kalibrasyon, değerlendirme

Ayrıntı: `index.yaml` (durum sözlüğüyle birlikte tüm envanter).

## 3. MRI pipeline

`nnunet-brats21/`, `swin-unetr-brats21/`, `mergen-uwcse/` · Girdi T1 · T1c · T2 · FLAIR → nnU-Net ve Swin UNETR paralel çıkarım →
UWCSE birleştirme → TC ⊂ WT, ET maskeleri + hacim + voxel belirsizliği → `review_flags`.

- Model kartları, provenance ve checkpoint doğrulaması: `nnunet-brats21/`, `swin-unetr-brats21/`
- Bu makinedeki çalışırlık ölçümleri (Dice, süre, VRAM): her modelin `smoke/` klasörü
- **Dikkat:** smoke Dice'ları performans iddiası değildir (bkz. `INVALID_OR_EXCLUDED_RESULTS.md` §3)

## 4. UWCSE pipeline

`mergen-uwcse/` · UWCSE öğrenilen ağırlığı olmayan bir birleştirme kuralıdır: bölge başına tek
bir karışım oranı, voxel düzeyinde model güveniyle çarpılır, ardından son işleme uygulanır.

| Koşu | Ne | Kullanım |
|---|---|---|
| `uwcse_v1` | rastgele 10 vakalık ağırlık ölçümü | **kullanma** — örneklem temsili değil (§5 INVALID) |
| `uwcse_v2` | grade'e orantılı tabakalı 30 vaka | ara adım |
| `uwcse_v3` | v2 + `TC_MIN=250` kuralı | **ÜRÜN** |
| `sampling_sweep` | örneklem büyüklüğü/bileşimi taraması, ağırlık uçurumu, kapı araması, karar kaydı | gerekçe |

Kod: `uwcse_ensemble.py` (kural), `refit_uwcse_weights.py` (tabakalı ölçüm),
`sweep_uwcse_sampling.py` (tarama), `evaluate_uwcse.py` (değerlendirme).

## 5. WSI pipeline

`dinov2-vitb14/`, `mergen-wsi-attention-mil/` · Slayt → HSV doku maskesi → 0,5 µm/px'e normalize 224 px kareler → DINOv2 gömüleri
(≤8192 kare × 768, fp16) → Gated Attention-MIL → A/O/G + attention ısı haritası.

- Kodlayıcı ve kare çıkarımı: `dinov2-vitb14/` (`wsi_tiles.py`, `extract_embeddings.py`)
- Model mimarisi ve hat: `mergen-wsi-attention-mil/` (`model.py`, `train.py`, `README.md`)
- Kilitli split: `mergen-wsi-attention-mil/splits_v1.json` — 532/115/115 hasta, sınıf×grade stratifiye,
  tohum 20260914; QC (`--min-tiles 100`) sonrası 524/115/113

## 6. Attention-MIL eğitim özeti

`mergen-wsi-attention-mil/training/`

- Mimari: 768 → 256 → gated attention 128 → 3 sınıf, **263.556 parametre**; encoder dondurulmuş
- Eğitim: sınıf ağırlıklı cross-entropy, kosinüs zamanlama, val macro-F1'de erken durdurma (sabır 15)
- `mil_v1`: 39 epoch, en iyi epoch 24, 183 s — `config.json`, `train_log.jsonl`, `best_metrics.json`
- `seeds_v1`: 5 tohum, her birinin tam epoch geçmişi
- `cv_v1`: 5 fold, her fold'un tam epoch geçmişi + `cv_summary.json`

## 7. Kullanılacak ana performans sonuçları

Tam tablo kaynak dosyalarıyla birlikte: **`RESULTS_SUMMARY.md`**

**Patoloji (A/O/G, TCGA WSI):**
- Ürün 5-fold ensemble, **kilitli test macro-F1 0,790 [0,708–0,863]** (n=113)
- En güvenilir genelleme tahmini: **out-of-fold 0,827 [0,793–0,857]** (n=639)

**MRI (UCSF-PDGM, BraTS21 dışı vakalar):**
- Ürün UWCSE, **kilitli test n=172** — Dice TC 0,764 · WT 0,929 · ET 0,856 · ortalama 0,866
- **HD95: TC 2,44 · WT 3,45 · ET 1,77 mm** — her üç bölgede de iki tek modelden iyi
- En iyi tek modele göre **+0,0053 [−0,0138, +0,0261]**

## 8. Geçersiz / kullanılmaması gereken sonuçlar

**`INVALID_OR_EXCLUDED_RESULTS.md`** — silinmediler, işaretlendiler. Özetle:

1. Sızıntılı ensemble macro-F1 **0,923** — 115 val hastasının tamamı 5 modelden 4'ünün eğitim setinde
2. Doğrulama skorları — en iyi epoch seçiminden ötürü **+0,046** şişkin
3. Smoke test Dice'ları — eğitim örtüşmesi olabilir, performans iddiası değil
4. MRI ortalama Dice — `by_region_presence` ayrımı olmadan verilemez
5. `uwcse_v1` — ağırlık örneklemi temsili değil, yalnız "önce/sonra" için
6. Gömü-tabanlı dağılım-dışılık kapısı — test edildi ve **çürütüldü**

## 9. Sistemden çıkarılan model

`legacy-esm2-xgboost/` · **ESM-2 + AAindex + XGBoost missense varyant prototipi**
(`VeriOdakliCozum`). Durum: `deferred` / `out_of_core_scope`.

Çıkarılma gerekçesi model kartında ve `metrics.json` içinde belgelidir: çekirdek glioma görüntü
akışının dışındadır, yerel ağırlık/veri/sonuç üretilmemiştir, ve MERGEN'in karar-destek akışı
(MRI + patoloji + laboratuvar) içinde bir rolü yoktur. Kaynak kod `source_code/` altında saklıdır.

## 10. Hangi dosya hangi iddia için

| Rapordaki iddia | Kaynak dosya |
|---|---|
| Sistem akış şeması | `report/figures/fig_system_flow.png`, `docs/SISTEM_MIMARISI_2026-09-16.md` §1 |
| Model envanteri ve durumları | `index.yaml`, `SUMMARY.md` |
| nnU-Net provenance / lisans / upstream metrik | `nnunet-brats21/MODEL_CARD.md`, `metrics.json` |
| Swin UNETR provenance / upstream metrik | `swin-unetr-brats21/MODEL_CARD.md`, `metrics.json` |
| MRI bağımsız test Dice'ları | `mergen-uwcse/uwcse_v3/segmentation_metrics.json` |
| MRI var/yok ayrımı (yanlış alarm analizi) | aynı dosya, `by_region_presence` bloğu |
| UWCSE ağırlık uçurumu (kadran değil basamak) | `mergen-uwcse/sampling_sweep/tc_weight_curve.json` + `<EVIDENCE_ROOT>/06_figures/uwcse/` |
| UWCSE yapılandırma kararı ve gerekçesi | `mergen-uwcse/sampling_sweep/decision.json` |
| TC_MIN kuralının kazancı | `mergen-uwcse/sampling_sweep/tc_gate_test_readout.json` |
| Doktor ekranı güvenilirlik bayrağı | `mergen-uwcse/sampling_sweep/core_review_flag.json` |
| MRI örnek segmentasyon çıktıları | `<EVIDENCE_ROOT>/06_figures/mri/cases/<vaka>/overlay.png` + `case_info.json` |
| MRI sınır doğruluğu (HD95) | `mergen-uwcse/results/hd95/hd95.json` + `README.md` |
| WSI vaka bazlı attention örnekleri | `<EVIDENCE_ROOT>/06_figures/wsi/cases/<bölme>_<hasta>/` |
| WSI hata örnekleri (yanlış sınıflandırma) | `<EVIDENCE_ROOT>/06_figures/wsi/cases/INDEX.json` — `correct: false` satırları |
| WSI veri kümesi, split ve QC | `mergen-wsi-attention-mil/splits_v1.json`, `data_distribution.json` |
| Attention-MIL mimarisi | `../pathology/model.py`, `MODEL_CARD.md` |
| Eğitim eğrisi, epoch/loss/metrik geçmişi | `mergen-wsi-attention-mil/training/*/train_log.jsonl` |
| Kilitli test sonucu (patoloji ana iddia) | `mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json` |
| Out-of-fold genelleme tahmini | `mergen-wsi-attention-mil/results/variance_v1/cv_v1_summary.json` |
| Tohum oynaklığı | `mergen-wsi-attention-mil/results/variance_v1/seeds_v1_summary.json` |
| Kalibrasyon ve çekimserlik eşiği | `mergen-wsi-attention-mil/results/ensemble_cv_v1/calibration.json` |
| Karışıklık matrisi grafikleri | `<EVIDENCE_ROOT>/06_figures/wsi/confusion_*.png` |
| Attention ısı haritası örnekleri | `<EVIDENCE_ROOT>/06_figures/wsi/review_sheet.jpg` |
| Hata analizi (hangi vakalar, neden) | `mergen-wsi-attention-mil/results/mil_v1/heatmaps/review_summary.json` |
| DINOv2 verim ve VRAM ölçümü | `dinov2-vitb14/smoke/dinov2_wsi_smoke.json` |
| Çıkarılan eski model gerekçesi | `legacy-esm2-xgboost/MODEL_CARD.md` |
| Geçersiz sonuçlar ve nedenleri | `INVALID_OR_EXCLUDED_RESULTS.md` |

---

## Vaka bazlı örnek klasörleri

Rapor yazarken kolaylık olsun diye her örnek vaka kendi klasöründe, yanında makine-okunur
künyesiyle duruyor.

**`<EVIDENCE_ROOT>/06_figures/wsi/cases/` — 12 patoloji vakası** (`INDEX.json` tam listeyi verir)

Her klasörde: `attention.jpg` (slayt üzerinde attention ısı haritası), `top_tiles.jpg` (en
yüksek attention'lı 12 kare), `case_info.json` (gerçek/tahmin sınıf, WHO grade, kaynak merkez,
sınıf olasılıkları, attention yoğunlaşma istatistikleri).

Kapsam: üç sınıfın hepsi (A/O/G), 9 farklı kaynak merkez, 7 doğru + 5 yanlış sınıflandırma.
Doğrulama bölmesinden 6, kilitli testten 6 vaka. Attention haritaları `mil_v1` tek modelinden
gelir — attention tek bir ağın iç değişkenidir; ürün 5-fold ensemble'ın olasılıkları
`mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json` içindedir.

**`<EVIDENCE_ROOT>/06_figures/mri/cases/` — 5 MRI vakası** (`INDEX.json` tam listeyi verir)

Her klasörde: `overlay.png` (FLAIR · T1 kontrastlı · referans · tahmin yan yana),
`case_info.json` (WHO grade, tanı, IDH durumu, bölge bazlı referans/tahmin hacimleri, Dice,
HD95, `review_flags` çıktısı).

Vakalar kasıtlı çeşitlendirildi:

| Vaka | Neden seçildi | Dice ort |
|---|---|---:|
| UCSF-PDGM-0504 | yüksek başarı | 0,979 |
| UCSF-PDGM-0155 | tipik / medyan | 0,930 |
| UCSF-PDGM-0443 | en zayıf vaka | 0,167 |
| UCSF-PDGM-0231 | çekirdeksiz — model doğru sustu | 0,986 |
| UCSF-PDGM-0440 | çekirdeksiz — model yanlış çekirdek işaretledi | 0,326 |

Son iki satır rapor için önemli: ürünün en kırılgan davranışı kontrast tutmayan tümörlerde
çekirdek kararıdır ve iki yüzü de burada görünüyor.

## Türetilmiş dosyalar

Bu arşivde iki dosya kaynaklardan **türetilmiştir**, elle yazılmamıştır:

- `RESULTS_SUMMARY.md` — tablodaki her sayı, satırda belirtilen kaynak JSON'dan programatik okundu
- `<EVIDENCE_ROOT>/06_figures/mri/fig_mri_segmentation_examples.png` ve `<EVIDENCE_ROOT>/06_figures/mri/cases/` — UCSF-PDGM kilitli
  test vakaları; önbellekteki olasılık haritalarından ürün ağırlıkları ve TC_MIN kuralıyla üretildi,
  yeni çıkarım yapılmadı. Betikler yanındadır: `generate_mri_examples.py`, `cases/generate_mri_cases.py`
- `mergen-uwcse/results/hd95/hd95.json` — aynı önbellekten hesaplandı, `compute_hd95.py` yanındadır
- `<EVIDENCE_ROOT>/06_figures/wsi/cases/` — `heatmap_review.py` çıktılarından vaka klasörlerine derlendi
- `../../docs/SISTEM_MIMARISI_2026-09-16.md` — depo kökündeki `sistem_mimarisi.md`'den
  üretildi; cutoff kuralı gereği 5.9 ve 5.10 bölümleri (Gazi Brains) çıkarıldı. Dosya başındaki
  yorum satırı bunu belirtir.
