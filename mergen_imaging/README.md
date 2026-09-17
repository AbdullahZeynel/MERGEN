# Isolated UWCSE v3 runner (G4-B / M5)

Bu paket yalnız `mergen_executor.process_adapter` tarafından, ayrı model venv'i
içinde çalıştırılır. Ağ, VPS, dispatcher, spool veya token bilmez.

## Sabit model sözleşmesi

- Model kimliği: `mergen-uwcse`, sürüm `v3` — ürün yapılandırmasının kendisi
- Üyeler (sırayla, cihaz aralarında boşaltılır):
  1. `nnunet-brats21`, Dataset002_BRATS19, **beş fold** — ölçülen tepe 3,1 GiB
  2. `swin-unetr-brats21`, `fold0-f48-ep300` — ölçülen tepe 4,4 GiB
- Kanallar: Swin `FLAIR, T1CE, T1, T2`; nnU-Net kendi sırasıyla `T1, T1c, T2, FLAIR`
  ve ITK eksen sırasında (referans: `models/imaging/nnunet_predictor.py`)
- Ön işleme: Swin için her kanalda nonzero z-score; nnU-Net kendi içinde normalize eder
- Inference: Swin `128×128×128` sliding window, overlap `0.6`, CUDA autocast;
  nnU-Net eşzamanlı (multiprocessing yok), mirroring açık
- Birleştirme: UWCSE v3 — bölge ağırlıkları TC 0,425 / WT 0,697 / ET 0,447,
  voxel belirsizlik ağırlığı, eşik `0.5`
- Son işleme: küçük bileşen temizliği, `ET_MIN`, `TC_MIN`; ardından `review_flags`
- Çıkış: BraTS etiketleri NCR=1, ED=2, ET=4

Ağırlıklar `models/registry/mergen-uwcse/uwcse_v3/segmentation_metrics.json`
içindeki uydurulmuş değerlerdir; kural kodu `mergen_imaging/uwcse.py`'dedir ve
`models/imaging/test_live_product_rule.py` onu araştırma hattıyla karşılaştırır.

Runner resample, registration, sahte modalite veya ground truth kullanmaz. Dört
NIfTI hacminin şekli ve affine matrisi uyuşmuyorsa açık hata verir.

Resample olmadığı için girdi ızgarası da sözleşmenin parçasıdır: 1 mm izotropik,
LPS, eksen hizalı — incelenen bütün vakaların taşıdığı yön matrisi. Başka bir
uzaydaki hacim `input-invalid` ile reddedilir, sessizce yeniden örneklenmez.

Manifest ölçülen topluluğu tarif etmek zorundadır: beş fold (0–4, aynı eğitilmiş
model klasöründe, aynı checkpoint adıyla) ve tam bir Swin. Eksik ya da fazla üye
reddedilir; başka bir topluluk aynı adla skorlanmaz.

> **Durum:** kod ve sözleşme hazır, **hostta kabul edilmedi.** nnU-Net üyesi
> gerçek ağırlıklarla burada çalıştırılmadı; `requirements.lock` nnunetv2 ile
> yeniden üretilecek ve uçtan uca koşu GPU hostunda yapılacak (#48).

## Çıktı

`result.zip` yalnız şunları taşır:

- `manifest.json`: canlı `ResultManifest` v1
- `report.json` (v2): ürün kimliği, üyeler, kural (ağırlıklar/eşikler), bölge
  hacimleri (TC/WT/ET), inceleme bayrakları, etiket voxel sayıları ve uyarı
- `prediction.nii.gz`: giriş affine/header'ı ile uint8 BraTS maskesi
- `prediction.glb`: ET, NCR ve ED yüzeyleri; boş tahminde geçerli boş sahne

Dice veya klinik skor üretilmez; canlı girdide referans etiket yoktur. Runner
stdout/stderr'e hasta verisi, yol veya hata metni yazmaz.

## Preflight

Başlamadan önce G4-A katmanı manifest ve checkpoint boyut/SHA-256 değerini
doğrular. Runner ayrıca `requirements.lock` içindeki bütün dağıtım sürümlerini,
CUDA erişimini, model
mimarisini ve checkpoint'in `state_dict` uyumunu doğrular. Herhangi biri
başarısızsa executor `imaging` capability ilan etmez.

## Kabul fixture'ı

`python -m mergen_imaging.make_fixture <dizin>` incelenen ızgarada sentetik dört
modalite yazar. Hiçbir parçası bir insandan gelmez ve segmentasyon kalitesini
ölçmez; sınırı, ortamı ve sonuç sözleşmesini ölçer. Kabul komutu ve ölçülen
süre/VRAM değerleri [`GPU_HOST_RUNBOOK.md`](../docs/GPU_HOST_RUNBOOK.md) 16.
adımdadır.
