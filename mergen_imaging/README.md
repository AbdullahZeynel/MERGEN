# Isolated Swin UNETR runner (G4-B)

Bu paket yalnız `mergen_executor.process_adapter` tarafından, ayrı model venv'i
içinde çalıştırılır. Ağ, VPS, dispatcher, spool veya token bilmez.

## Sabit model sözleşmesi

- Model: `swin-unetr-brats21`, sürüm `fold0-f48-ep300`
- Kanallar: `FLAIR, T1CE, T1, T2`
- Ön işleme: her kanalda yalnız nonzero voxel'lerde ayrı z-score normalizasyonu
- Inference: `128×128×128` sliding window, batch 1, overlap `0.6`, CUDA autocast
- Çıkış: sigmoid ve `0.5` eşik; BraTS etiketleri NCR=1, ED=2, ET=4

Bu değerler depodaki MONAI referans çıkarımı ve kullanılan checkpoint ile aynıdır.
Runner resample, registration, sahte modalite veya ground truth kullanmaz. Dört
NIfTI hacminin şekli ve affine matrisi uyuşmuyorsa açık hata verir.

Resample olmadığı için girdi ızgarası da sözleşmenin parçasıdır: 1 mm izotropik,
LPS, eksen hizalı — incelenen bütün vakaların taşıdığı yön matrisi. Başka bir
uzaydaki hacim `input-invalid` ile reddedilir, sessizce yeniden örneklenmez.

## Çıktı

`result.zip` yalnız şunları taşır:

- `manifest.json`: canlı `ResultManifest` v1
- `report.json`: model kimliği, araştırma uyarısı ve etiket voxel sayıları
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
