# Model entegrasyon ve hazırlık planı

## Karar

MERGEN, araştırma amaçlı bir **doktor karar-destek sistemi** olarak kurulacaktır;
model karşılaştırma arayüzü veya otomatik tanı/tedavi sistemi olarak değil. Doktor
ekranında birincil MRI sonucu ile birincil WSI sonucu gösterilir. Model ablationları,
fold sonuçları ve alternatifler teknik raporda tutulur.

Ürünün orkestrasyonu, veri kalite kontrolü, adaptörleri, UWCSE katmanı, yerel
değerlendirmesi ve kullanıcı arayüzü MERGEN katkısıdır. Harici kod ve pretrained
ağırlıklar ekip tarafından üretilmiş gibi gösterilemez. Her varlık için kaynak,
lisans, sabit sürüm/commit ve hash saklanır; kullanıcı arayüzü ürün markası olarak
MERGEN adını kullanabilir.

## Çekirdek sistem

| Katman | Bileşen | Karar | Eğitim | Bugünkü durum (2026-09-14) |
|---|---|---|---|---|
| MRI | nnU-Net v2 BraTS21 | Birincil segmentasyon uzmanı | Yeniden eğitme yok | 5 fold checkpoint indirildi ve hash/torch-load doğrulandı; nnunetv2 ortamı ve yerel test yok |
| MRI | Swin UNETR BraTS21 | İkinci segmentasyon uzmanı | Yeniden eğitme yok | Fold-0 checkpoint doğrulandı; MONAI ortamı ve yerel test yok |
| MRI | MERGEN UWCSE | Tek doktor çıktısını üreten füzyon | Ağ eğitimi yok; katsayılar yalnız validation'da dondurulur | Kod var, doğrulanmış sonuç yok |
| WSI | DINOv2 ViT-B/14 | Dondurulmuş tile encoder | Yeniden eğitme yok | Ağırlık doğrulandı; GPU'da yüklendi (620 tile/s bf16, batch 64) |
| WSI | MERGEN Attention-MIL A/O/G | Birincil patoloji sınıflandırıcısı ve heatmap | **Eğitilecek tek görev modeli** | 762 WSI indirildi; etiketler iki bağımsız WHO2021 listesiyle %100 uyumlu; QC, split, embedding, model ve sonuç yok |
| RAG | Doktor bilgi yardımcısı | Analizler kararlı olduktan sonra | Model eğitimi yok | Model ve doküman korpusu seçilmedi |

MONAI BraTS18 SegResNet, TUM radio-path, GMAP, ROAM, 1p19qNet, MIL_Pretrained ve eski
genomik XGBoost çekirdek doktor ekranına eklenmez; model kayıtlarında referans veya
ertelenmiş aday olarak tutulur. 2026-09-14 itibarıyla TUM, GMAP, ROAM, 1p19qNet ve
MIL_Pretrained ağırlıkları araştırma amaçlı olarak veri köküne indirilmiş ve hash'leri
kaydedilmiştir; ancak TUM, GMAP, 1p19qNet ve MIL_Pretrained depolarında açık bir
yazılım lisansı yoktur ve TUM/GMAP çıkarım zincirleri erişim onaylı encoderlar
(Prov-GigaPath, UNI) ister. Yazılı izin/lisans ve encoder erişimi netleşmeden bunlar
ürün paketine alınmaz. Envanter ve kaynaklı metrikler
[`models/registry/SUMMARY.md`](../models/registry/SUMMARY.md) içindedir.

Bu seçim, lisanssız hazır checkpointleri gizlemek yerine gerçekten takım tarafından
eğitilmiş bir A/O/G görev başlığı üretir. DINOv2 harici ve dondurulmuş bir encoder
olarak açıkça belirtilir; A/O/G sınıflandırıcısı, splitler ve yerel sonuçlar MERGEN'e
ait olur.

## Doktor akışı

1. Doktor vaka oluşturur ve dört hizalı MRI modalitesini (T1, T1c, T2, FLAIR),
   varsa aynı hastaya ait H&E WSI'ı yükler.
2. Sistem dosya ve kalite kontrolü yapar. Eksik/bozuk modalite başarılı sonuç gibi
   gösterilmez.
3. MRI kolu WT, TC ve ET maskelerini, hacimleri ve 2D/3D görselleştirmeyi üretir.
4. WSI kolu A/O/G olasılıklarını, karar üzerinde etkili bölgeleri ve belirsizlik
   uyarısını üretir.
5. Ölçülmüş IDH, 1p/19q ve MGMT laboratuvar bulguları `measured`; görüntüden
   tahmin edilen değerler `predicted` etiketiyle gösterilir. Birbirinin yerine geçmez.
6. MRI ile WSI aynı hastaya ait değilse sistem iki sonucu matematiksel olarak
   birleştirmez. Mevcut UCSF/BraTS MRI örnekleri ile TCGA WSI'lar aynı vaka değildir.
7. RAG, yalnız seçilmiş tıbbi kılavuz ve yerel model kartlarından kaynak göstererek
   açıklama yapar; tanı veya tedavi uygunluğu hesaplayan serbest bir chatbot olmaz.

## “Kullanıma hazır” kabul ölçütü

Bir bileşen ancak aşağıdakilerin tümü tamamlandığında `ready` olur:

1. Kaynak URL, commit/sürüm, lisans ve kullanım koşulları kaydedilmiş.
2. Ağırlık indirilmiş; SHA-256 ve dosya boyutu manifestte doğrulanmış.
3. Ayrı ve kilitlenmiş çalışma ortamı kurulmuş.
4. Girdi/çıktı sözleşmesi ve başarısızlık davranışı tanımlanmış.
5. Küçük gerçek veriyle uçtan uca smoke inference geçmiş.
6. Eğitim/validation/test dağılımı hasta düzeyinde kayıtlı.
7. Upstream metrik ile MERGEN'in yeniden ürettiği metrik ayrı dosyalarda kayıtlı.
8. Çakışan hasta/veri kaynağı kontrolü yapılmış; dış test sonucu açıkça etiketlenmiş.
9. Tek komutlu inference adaptörü ve otomatik smoke testi mevcut.
10. Klinik amaç dışı kullanım ve bilinen sınırlamalar model kartında yazılı.

Bir ağırlığın bulunması tek başına `ready` anlamına gelmez.

## Dosya düzeni

Çalışan kod, mevcut yolları ve importları bozmamak için yerinde kalır. Kayıt ve
kanıtlar `models/registry/<model-id>/MODEL_CARD.md` altında toplanır.

```text
models/registry/
├── index.yaml
├── nnunet-brats21/
├── swin-unetr-brats21/
├── mergen-uwcse/
├── monai-segresnet-brats18/
├── dinov2-vitb14/
├── prov-gigapath/
├── uni/
├── mergen-wsi-attention-mil/
├── tum-radio-path-moe-mamba/
├── gmap/
├── iucompath-glioma-subtyping/
├── roam/
├── 1p19qnet/
├── legacy-esm2-xgboost/
└── doctor-rag/
```

Ağırlık, veri ve koşu çıktıları Git dışında tutulur:

```text
<MERGEN_DATA_ROOT>/models/<model-id>/weights/
<MERGEN_DATA_ROOT>/datasets/<dataset-id>/
<MERGEN_DATA_ROOT>/runs/<model-id>/<run-id>/
```

## Uygulama sırası

### A0 — Envanter ve model kayıtları (tamamlandı)

- Mevcut kod, cache, ağırlık, veri ve sonuçlar sayıldı.
- Model kayıt yapısı ve başlangıç kartları oluşturuldu.
- Gerçek durum `ready` yerine `missing_assets`, `to_train`, `reference_only` ve
  `deferred` olarak kaydedildi.

### A1 — Kaynak ve lisans kapıları (2026-09-14: büyük ölçüde tamamlandı)

- nnU-Net ve Swin UNETR için indirme URL'si, lisans, sürüm ve hash
  `models/registry/assets.lock.json` içinde sabitlendi.
- TCGA/GDC WSI manifesti ile cBioPortal etiket tablosunun URL/commit/hash bilgileri
  varlık manifestine yazıldı.
- TUM, GMAP, 1p19qNet ve MIL_Pretrained için yazılı izin/lisans hâlâ açık; ürün
  bağımlılığı yapılmadı. ROAM GPL-3.0.

### A2 — MRI bileşenlerini hazır etme

- nnU-Net (5 fold) ve Swin fold-0 checkpointleri veri diskine indirildi; MD5/SHA-256
  doğrulandı ve torch ile yüklendi (`verify_assets.py --torch-load`).
- nnU-Net checkpoint loglarından fold bazlı eğitim-zamanı doğrulama pseudo-Dice
  değerleri çıkarıldı (`models/registry/nnunet-brats21/upstream_training_log.json`);
  bunlar bağımsız test sonucu değildir.
- 2026-09-14: `mergen-py314` ortamına MONAI 1.6.0 ve nnU-Net v2 kuruldu; nnU-Net
  (fold-0 ve 5-fold), Swin UNETR fold-0 ve MONAI SegResNet, etiketli 8 MSD Task01
  vakasında uçtan uca çalıştırıldı (Dice, süre, VRAM: `models/registry/report/REPORT.md`).
  MSD vakaları BraTS 2016/17 kökenli olduğundan bu bir bağımsız test değildir.
- Sırada: UCSF-PDGM BraTS21-dışı vakalarla (Aspera indirmesi) bağımsız test ve UWCSE
  katsayılarının dondurulması.
- Sabit validation kohortunda UWCSE katsayıları belirlenir ve dondurulur.
- Ayrı, görünmemiş test kohortunda Dice, HD95, sensitivity ve false-positive hacim
  raporlanır. İki hard-coded vaka klinik kanıt olarak kullanılmaz.

### A3 — MERGEN WSI A/O/G modelini eğitme

Durum 2026-09-14: eğitim hattı `models/pathology/mil/` altında hazır (kilitli split
532/115/115, resumable embedding çıkarımı, checkpoint/resume'lu eğitim, değerlendirme,
tek slayt çıkarım); preflight geçti. Tam koşu kullanıcı terminalinden başlatılacak
(`run_training.sh extract` → `train`). Ürün model seti: çekirdek nnU-Net, Swin UNETR,
UWCSE, DINOv2, MERGEN MIL; koşullu TUM MoE; diğerleri referans. MONAI SegResNet
kayıttan çıkarıldı.

- 762 slayt için açılabilirlik, MPP, bulanıklık, doku oranı ve artefakt QC raporu
  üretilir.
- Split, hasta düzeyinde ve sınıf/merkez/grade dengesi gözetilerek oluşturulur.
- Ham tile'lar kalıcı olarak çoğaltılmaz; koordinatlar ve sıkıştırılmış embeddingler
  saklanır.
- Önce 12 slaytlık pilot ile tile/s, VRAM, disk ve hata oranı ölçülür.
- DINOv2 dondurularak embeddingler checkpointli ve devam-edebilir iş kuyruğuyla
  çıkarılır.
- Attention-MIL; early stopping, epoch checkpointi ve resume desteğiyle eğitilir.
- Macro-F1, balanced accuracy, one-vs-rest AUROC, MCC, sınıf duyarlılığı,
  kalibrasyon ve confusion matrix hasta düzeyinde raporlanır.
- TCGA üstünde eğitilen model için bağımsız dış veri olmadan “genelleme” veya
  “klinik başarı” iddiası yapılmaz.

Pilot ölçüm olmadan kesin süre verilemez. Mevcut 3,1 milyon-tile üst sınırı için
ön planlama aralığı: preprocessing + embedding yaklaşık 18–40 saat, MIL eğitimi
yaklaşık 1–4 saat. Pilot bu aralığı gerçek donanımda daraltır.

### A4 — Tek-vaka servisleri ve doktor ekranı

- Eğitim/evaluation komutlarından ayrı, yalnız inference yapan model adaptörleri
  yazılır.
- Backend iş kuyruğu, durum, hata ve artifact manifesti eklenir.
- Doktor ekranı yalnız birincil MRI ve WSI sonucunu gösterir; karşılaştırmalar teknik
  ayrıntıya taşınır.
- `same_patient` doğrulaması olmadan multimodal füzyon çalışmaz.

### A5 — Kaynaklı doktor RAG'i

- Yarışma şartnamesi, seçilmiş nöro-onkoloji kılavuzları, model kartları ve yerel
  vaka raporu ayrı koleksiyonlar olarak indekslenir.
- Her cevap belge/sürüm/sayfa bağlantısı verir; kaynak dışı klinik iddia reddedilir.
- Ölçülmüş MGMT verisi bağlam olarak açıklanabilir; sistem tedavi önerisi veya
  “uyum skoru” uydurmaz.
- Retrieval doğruluğu, citation precision, answer faithfulness ve güvenli-red
  senaryoları test edilir.

## Bir haftalık gerçekçi kapsam

Bir haftada savunulabilir hedef, tüm adayları ürünleştirmek değil; çekirdek MRI
adaptörlerini doğrulamak ve MERGEN WSI pilotu ile tam embedding/eğitim koşusunu
tamamlamaktır. TUM, GMAP, ROAM, 1p19qNet ve RAG aynı haftaya eklenirse sistem
doktor aracından model vitrini hâline gelir ve her bileşenin doğrulaması yüzeysel
kalır.
