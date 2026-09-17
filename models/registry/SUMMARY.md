# Model envanteri raporu — 2026-09-14

Bu rapor, sistemin ihtiyaç duyduğu ve aday olarak incelenen tüm model varlıklarının
indirme, doğrulama ve belgeleme durumunu özetler. Ayrıntılar her bileşenin
`MODEL_CARD.md`, `metrics.json`, `data_distribution.json` ve `assets.json`
dosyalarındadır; makine tarafından okunur toplam liste `assets.lock.json` içindedir.

## Yerelde bulunan varlıklar

Veri kökü `~/mergen-data` (Git dışı). 96 dosya, toplam 3,47 GiB; tümü SHA-256 ile
kaydedildi ve `verify_assets.py --torch-load` ile 39 PyTorch checkpointinin tamamı
yüklendi (state-dict okunabilirlik testi; doğruluk testi değildir).

| Bileşen | İndirilen | Boyut | Kaynak | Lisans | Durum |
|---|---|---:|---|---|---|
| nnU-Net v2 BraTS21 | 5 fold checkpoint + plans/dataset json + zip | 2.346 MiB | Zenodo 11582627 (BAMF Health) | CC-BY-4.0 | `weights_verified` |
| Swin UNETR BraTS21 | fold-0 model.pt + zip | 465 MiB | MONAI-extra-test-data 0.8.1 | Apache-2.0 | `weights_verified` |
| MONAI SegResNet BraTS18 | model.pt + metadata/lisans | 18 MiB | Hugging Face MONAI/brats_mri_segmentation v0.5.4 | Apache-2.0 | `weights_verified` |
| DINOv2 ViT-B/14 | ağırlık + kaynak kodu | 333 MiB | facebookresearch/dinov2 @7764ea0f | Apache-2.0 | `weights_verified` (GPU testi geçti) |
| TUM Radio-Path MoE/Mamba | 10 fold checkpoint + meta veri/split CSV'leri | 11 MiB | csaueres/radio-path-glioma-subtyping @ac1b53b | Depoda lisans yok | `weights_verified_dependencies_gated` |
| GMAP | IDH/1p19q/TERT/+7−10 checkpointleri + etiket CSV | 142 MiB | Bingchao-Zhao/GMAP @d10abeb, Google Drive | Depoda lisans yok | `weights_verified_dependencies_gated` |
| ROAM | 5 split checkpoint + LICENSE | 168 MiB | whiteyunjie/ROAM @2c8414c, Google Drive | GPL-3.0 | `weights_verified` |
| 1p/19qNET | 1pNET, 19qNET, lojistik model | 0,5 MiB | rogo96/1p19qNet @e5ae13f | Depoda lisans yok | `weights_verified_license_unclear` |
| MIL_Pretrained | 10 MIL aggregator başlangıç ağırlığı | 64 MiB | fu0201/MIL_Pretrained @82906a6 | Depoda lisans yok | `weights_verified_license_unclear` |
| IUCompPath glioma-subtyping | etiket CSV'leri + 10 split | 2 MiB | IUCompPath/glioma-subtyping @91c05a5 | Depoda lisans yok; README ticari-olmayan | `metadata_only` (checkpoint yayımlanmamış) |
| AttentionDeepMIL | model.py + LICENSE | <1 MiB | AMLab-Amsterdam/AttentionDeepMIL | MIT | `code_reference` |
| TCGA glioma WSI kohortu | 762 WSI + manifest/etiket | 616,53 GiB | GDC + cBioPortal (sabit commit) | GDC açık erişim | indirme tamamlandı |
| Prov-GigaPath | — | — | Hugging Face (gated) | Apache-2.0, erişim onaylı | `gated_access_required` |
| UNI | — | — | Hugging Face (gated) | CC-BY-NC-ND-4.0, erişim onaylı | `gated_access_required` |

Hiçbir bileşen henüz `ready` değildir: ağırlıklar ve kaynaklar tamam, fakat model
bazlı çalışma ortamları (nnunetv2, MONAI, mamba-ssm, eski PyTorch yığınları) ve
gerçek vaka üzerinde uçtan uca smoke inference yapılmadı.

## Yayımlanmış performans özeti (kaynaklı)

| Model | Görev | Kohort | Sonuç | Kaynak |
|---|---|---|---|---|
| nnU-Net BraTS21 | MRI segmentasyonu | fold doğrulama (eğitim-zamanı pseudo-Dice) | EMA fg-Dice ort. 0,869; label 1 0,852 / label 2 0,894 / ET 0,864 | checkpoint logları (`upstream_training_log.json`); Zenodo yayımlanmış metrik vermez |
| Swin UNETR | MRI segmentasyonu | BraTS21 fold 0–4 doğrulama | Mean Dice 0,8854 / 0,9059 / 0,8981 / 0,8924 / 0,9035 | MONAI README |
| MONAI SegResNet | MRI segmentasyonu | BraTS18 doğrulama (42) | Dice TC 0,8559, WT 0,9026, ET 0,7905 | bundle metadata |
| DINOv2 ViT-B/14 | genel görüntü özelliği | ImageNet-1k | k-NN 82,1 %, linear 84,5 % | DINOv2 README |
| TUM MoE (WSI+MRI) | A/O/G | TCGA bağımsız test (171) | AUC 0,94; BA 0,80; accuracy 0,85; MCC 0,73 ± 0,05 | npj Precis Oncol 2026;10:118 |
| TUM yalnız-WSI | A/O/G | TCGA test | MCC 0,67 ± 0,04; sınıf doğruluğu GBM 0,87 / Astro 0,75 / Oligo 0,72 | aynı makale, Tablo 2 |
| GMAP | IDH / 1p19q / TERT / +7−10 | iç test 88 hasta | AUROC 0,939 / 0,955 / 0,944 / 0,886 | Lancet Digit Health 2026;8:100977 |
| GMAP | aynı | dış doğrulama 3.147 hasta | AUROC 0,870 / 0,885 / 0,694 / 0,672 | aynı makale |
| IUCompPath (en iyi FM+AM) | A/O/G | TCGA / EBRAINS / IPD | AUC 0,9795 / 0,9630 / 0,9261 | Neuro-Oncology 2026;28:282 |
| 1p/19qNET lojistik | Oligo vs Astro | discovery 288 / TCGA IVS 385 | Acc 0,861 F1 0,850 AUC 0,930 / Acc 0,725 F1 0,527 AUC 0,837 | npj Precis Oncol 2023;7:94, Tablo 1 |
| ROAM | 3 sınıf alt tip | Xiangya in-house test (seed s1, depo dosyası) | Acc 0,852, macro-F1 0,842, BA 0,833 | depo `results.json`/`metrics.json` |

Makale ekinde kalan sayılar (TUM Tablo S1, GMAP F1/sens/spec, IUCompPath F1/BA,
ROAM makale AUC'leri) açık erişimli olmadığı için kayda alınmadı; doğrulanmamış değer
yazılmadı.

## Eğitim verisi dağılımları (özet)

- **nnU-Net / Swin UNETR:** BraTS 2021 eğitim kümesi, 1.251 vaka, 5-fold.
- **MONAI SegResNet:** BraTS 2018, 285 vaka → 200 / 42 / 43.
- **DINOv2:** LVD-142M, 142 M etiketsiz görüntü.
- **TUM:** eğitim tamamen TCGA-dışı ve eşleşmesiz: EBRAINS WSI 786 (GBM 497 / Astro 132 /
  Oligo 157), UCSF-PDGM MRI 497 (398/84/15), EGD MRI 369 (249/62/58); test TCGA 171
  eşleşmiş vaka.
- **GMAP:** TCGA 877 hasta / 1.696 WSI (IDH mut 421 / wt 381; 1p19q codel 162; TERT mut
  150; +7/−10 pozitif 311); iç test 88 hasta; dış 3.147 hasta.
- **IUCompPath:** TCGA 656 vaka / 1.322 slayt (Oligo 141, Astro 226, GBM 289); EBRAINS
  794 slayt; IPD-Brain 209 vaka.
- **1p/19qNET:** Severance 288 hasta (kapalı); TCGA IVS 385 örnek (Oligo 153 / Astro 232).
- **ROAM:** Xiangya 1.109 slayt (kapalı), alt tip görevi 193 slayt; TCGA 618 slayt dış.
- **MERGEN WSI kohortu:** 762 hasta (A 255 / O 162 / G 345), 27+ merkez; grade-4
  vakalarda G 281 / A 19 / O 1.

## Yerel kohortla çakışma kontrolü (`_evidence/tcga_overlap_analysis.json`)

| Upstream | Yerel 762 hastadan çakışan | Etiket uyumu | Sonuç |
|---|---:|---|---|
| TUM TCGA histoloji listesi (828 vaka) | 760 | 760/760 | TUM TCGA'yı eğitimde kullanmadı; 170 vaka onların yayımlanmış test kümesi. Yerel kohort TUM için bağımsız ama yeni olmayan test. |
| GMAP eğitim etiket listesi (877 hasta) | 762 | — | Yerel kohort GMAP için **bağımsız test değildir**. |
| IUCompPath TCGA (656 vaka) | 638 | 638/638 | Etiketler WHO2021 tanılarıyla birebir uyumlu. |

MERGEN A/O/G etiket kuralı iki bağımsız WHO2021 etiket setiyle yüzde yüz uyuşmuştur;
"G sınıfı kuralını tıbbi danışmana doğrulatma" adımı bu kanıtla büyük ölçüde
kapanmıştır, ancak kural belgede aynen kalmalıdır.

## GPU ve ortam

- Sanal ortam: `~/mergen-data/envs/mergen-py314` — Python 3.14.4, torch 2.14.0+cu130,
  torchvision 0.29.0, numpy 2.5.2, nibabel, pyyaml, scikit-learn 1.9.1, addict.
  RTX 5060 Ti (sm_120) CUDA ile tanındı.
- DINOv2 ViT-B/14 GPU testi (`dinov2-vitb14/dinov2_gpu_smoke.json`): 86.580.480
  parametre, 224×224 batch 64 için 208 tile/s (fp32) ve 620 tile/s (bf16), tepe VRAM
  978 MiB. Rastgele tensörle ölçüldü; WSI okuma/tiling maliyeti dahil değildir.
  3,13 M tile üst sınırı için salt-GPU süre ≈ 1,4 saat (bf16); gerçek süre disk/CPU
  darboğazıyla belirlenecektir.

## Yerel çalıştırma sonuçları (2026-09-14, aynı gün eklendi)

Ayrıntılı rapor ve grafikler: [`report/REPORT.md`](report/REPORT.md), model rehberi ve akış
şeması [`report/MODEL_GUIDE.md`](report/MODEL_GUIDE.md); ikisinin birleşik HTML ve PDF
sürümü `report/REPORT.html` ve `report/MERGEN_model_raporu.pdf`.
Ortam: `mergen-py314` venv'ine MONAI 1.6.0, nnU-Net v2, SimpleITK 2.5.6,
OpenSlide 1.4.6 (openslide-bin), scikit-learn, matplotlib eklendi.

| Model | Girdi | Sonuç | Süre / tepe VRAM |
|---|---|---|---:|
| nnU-Net fold-0 | 8 MSD Task01 vakası (BraTS 2016/17 kökenli, etiketli) | Dice ort. TC 0,80 · WT 0,86 · ET 0,76 (medyan 0,91 / 0,88 / 0,86) | 4,6 s · 3,1 GiB |
| nnU-Net 5-fold ensemble | aynı | TC 0,80 · WT 0,85 · ET 0,75 | 20,2 s · 3,1 GiB |
| Swin UNETR fold-0 | aynı | TC 0,77 · WT 0,83 · ET 0,84 (medyan 0,89 / 0,86 / 0,83) | 6,8 s · 4,4 GiB (rez. 6,1) |
| MONAI SegResNet BraTS18 | aynı | TC 0,79 · WT 0,83 · ET 0,75 (medyan 0,91 / 0,87 / 0,84) | 0,4 s · 3,1 GiB |
| DINOv2 ViT-B/14 | 3 gerçek TCGA slaytı, 224 px @ 0,5 µm/px | 51–144 tile/s uçtan uca (okuma darboğazı), 497–510 tile/s yalnız GPU | 785 MiB |
| 1p/19qNET (hazır ağırlık) | 12 TCGA IDH-mutant slaytı (6 A, 6 O) | doğruluk 0,67; codeletion AUC 0,94, precision 1,0, recall 0,33 (upstream TCGA: 0,84 / 0,83 / 0,39) | 25–97 s/slayt · 1,5 GiB |

Dice ortalamalarını düşüren tek vaka BRATS_177'dir (referansta tümör çekirdeği 0,09 ml,
kontrastlanan bölge yok). MSD vakaları BraTS 2018/2021 eğitim kümeleriyle örtüşebildiği
için MRI sonuçları bağımsız test değil, çalışırlık ve tutarlılık kontrolüdür. GMAP ve TUM
checkpointleri UNI / Prov-GigaPath erişimi olmadan çalıştırılamadı; ROAM'un eski yığını
kurulmadı.

## Model seti kararı ve eğitim hattı (2026-09-14, akşam)

- **Çekirdek:** nnU-Net BraTS21, Swin UNETR BraTS21, UWCSE, DINOv2 ViT-B/14, MERGEN
  Attention-MIL. **Koşullu:** TUM MoE (Prov-GigaPath erişimi). **Referans:** GMAP,
  1p/19qNET, ROAM, IUCompPath, MIL_Pretrained, AttentionDeepMIL. **Çıkarıldı:** MONAI
  SegResNet BraTS18 (kayıt, paket ve rapordan silindi; ağırlığı veri kökünden kaldırıldı).
- Attention-MIL eğitim hattı `models/pathology/mil/` altında: `make_split.py` (kilitli
  532/115/115, sınıf×grade stratifiye), `extract_embeddings.py` (resumable),
  `train.py` (last/best/epoch/interrupt checkpoint, `--resume auto`), `evaluate.py`,
  `infer_slide.py`, `preflight.py`, `run_training.sh`.
- Preflight geçti (`~/mergen-data/pathology/runs/preflight/preflight_report.json`):
  6 slayt embedding 151 tile/s uçtan uca (6 okuyucu), eğitim + kesinti sonrası devam
  doğru (epoch 0–3 kesintisiz log), heatmap üretimi 4,6 s. Tam koşu tahmini: embedding
  3–6 saat, eğitim 100 epoch ≈ 3 dakika.
- WSI çıktı demosu (`1p19qnet/smoke/*_wsi_outputs_small.jpg`): DINOv2 embedding kümeleri
  ve 1p/19qNET tile ısı haritası gerçek slaytta görülebilir.

## Attention-MIL eğitimi tamamlandı (mil_v1, 2026-09-14 gece)

- Embedding çıkarımı: 758/762 slayt, 6,6 GB fp16, 2 s 41 dk, 472 kare/s (6 okuyucu).
  4 slayt doku bulunamadığı, 6 slayt < 100 kare olduğu için kalite eşiğiyle dışlandı
  (train 524, val 115, test 113 kullanılabilir).
- Eğitim: 39 epoch (erken durdurma, sabır 15), en iyi epoch 24, toplam 183 s, 4,7 s/epoch.
- Doğrulama (115 hasta, `best.pt`): macro-F1 **0,881** (%95 GA 0,815–0,936), balanced
  accuracy 0,877, AUROC 0,960, MCC 0,824, accuracy 0,887. Sınıf F1: A 0,845 / O 0,880 /
  G 0,917. Hataların çoğu grade 3–4 astrositomların G'ye kayması.
- Kayıt: `mergen-wsi-attention-mil/results/mil_v1/` (config, log, tahminler, karışıklık
  matrisi, best.pt SHA-256).
- **Kilitli test (113 hasta, tek sefer):** macro-F1 0,770 (%95 GA 0,679–0,847), balanced
  accuracy 0,761, AUROC 0,903, MCC 0,671, accuracy 0,788. Sınıf F1: A 0,765 / O 0,708 /
  G 0,836. Karışıklık (satır gerçek A/O/G): [[26,4,8],[2,17,6],[2,2,46]]. Hatalar A→G (8)
  ve O→G (6) yönünde; 24 hatanın 12'si iki merkezden (Case Western St Joes 7, Henry Ford 5).
  Doğrulama→test düşüşü (0,88→0,77) model seçimi iyimserliği ve merkez/boyama farkını
  yansıtır. Softmax farkına dayalı çekimserlik testte belirgin kazanç sağlamadı (model
  yanlışlarında da kendinden emin); ürün için kalibrasyon (temperature scaling) gerekir.
- Karar: mil_v1 **dondurulmuş sürüm**; test bir kez açıldığı için bu kohortta yeniden
  ayar yapılmaz. İyileştirme (merkez dengeleme, stain augmentation, tohum ensemble)
  ancak TCGA-dışı bir doğrulama setiyle kanıtlanabilir.

## Eksikler ve sonraki adımlar

1. **Model ortamları:** nnunetv2, MONAI (Swin/SegResNet), TUM (mamba-ssm, Python 3.10),
   GMAP (torch 2.4 + lightning), ROAM/1p19qNET (PyTorch 1.12 yığını) için izole ortamlar
   ve gerçek vaka smoke inference.
2. **Gated encoderlar:** Prov-GigaPath ve UNI ağırlıkları için kullanıcı Hugging Face
   hesabıyla koşulları kabul etmeli; token yerelde tutulmalı. Bunlar olmadan TUM ve
   GMAP checkpointleri ham WSI üzerinde çalışmaz.
3. **Lisans/izin:** TUM, GMAP, 1p/19qNET ve MIL_Pretrained depolarında lisans yok;
   ürün paketine alınmadan önce yazarlardan yazılı izin istenmeli. ROAM GPL-3.0'dır.
4. **MRI değerlendirmesi:** UCSF-PDGM BraTS21-dışı vakalar indirilip UWCSE katsayıları
   validation'da dondurulmalı; görünmemiş test raporu üretilmeli.
5. **WSI kolu:** Karar iki seçenek arasındadır: (a) DINOv2 + MERGEN gated Attention-MIL
   eğitimi (encoder hazır, veri hazır); (b) GigaPath erişimi alınırsa TUM'un yalnız-WSI
   yolunun yerel TCGA üzerinde yeniden değerlendirilmesi. Her iki durumda da yerel
   kohort GMAP için test verisi olamaz.
