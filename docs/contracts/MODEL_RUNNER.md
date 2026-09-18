# Model runner contract v1

G4-A'da executor ile görüntü modeli aynı Python ortamını veya süreci paylaşmaz.
Bu dosya yerel süreç sınırını tanımlar; VPS, ağ ve dispatcher sözleşmesi değildir.

## Operator-managed model manifest

`MERGEN_MODEL_ROOT/manifest.json` UTF-8 JSON'dur:

```json
{
  "schemaVersion": 1,
  "modelId": "mergen-uwcse",
  "modelVersion": "v3",
  "runnerModule": "mergen_imaging.runner",
  "checkpoints": [
    {
      "role": "nnunet-fold",
      "fold": 0,
      "path": "nnunet/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_0/checkpoint_final.pth",
      "size": 123,
      "sha256": "64 lowercase hex characters"
    },
    {
      "role": "swin",
      "path": "swin/pretrained_models/model.pt",
      "size": 123,
      "sha256": "64 lowercase hex characters"
    }
  ]
}
```

Canlı yol ürün yapılandırmasının kimliğini taşır: `mergen-uwcse` / `v3`. Üyeler
manifestte rolleriyle durur — beş `nnunet-fold` (0–4, her biri `fold_N/` altında
ve hepsi aynı dosya adıyla, aynı eğitilmiş model klasöründe), isteğe bağlı
`nnunet-plan` girdileri (aynı klasördeki `plans.json`, `dataset.json`) ve tam bir
`swin`. Eksik fold, tekrarlanan fold, fazladan üye ya da iki model klasörüne
yayılmış foldlar reddedilir: hepsi çalışır ve aynı adla skorlanır ama ölçülen
topluluk olmaz. Örnek dosya:
[`infra/gpu-host/imaging-model-manifest.example.json`](../../infra/gpu-host/imaging-model-manifest.example.json).

Model kökü, manifest, venv ve checkpoint'ler hostta yalnız güvenilir bakım
hesabı tarafından yönetilir; servis hesaplarının yazma izni yoktur.
Checkpoint yolları model köküne göre göreli olmalı; `..`, mutlak yol ve symlink
bileşenleri reddedilir. Boyut ve SHA-256 her executor başlangıcında capability
ilan edilmeden önce doğrulanır. `modelId` ve `modelVersion`, sonuç ZIP'indeki
`ResultManifest` ile birebir aynı olmalıdır.

## Process protocol

Executor çalıştırıcıyı aşağıdaki biçimde başlatır:

```text
<MERGEN_IMAGING_VENV>/bin/python -P -m <runnerModule>
```

Tek bir JSON istek stdin'den gelir. `operation` değeri `preflight` veya `run`'dır.
Run isteği iş kimliğini, hastalık slug'ını, model/input/output dizinlerini, dört
modalite yolunu, model kimliğini ve azami sonuç boyutunu taşır. Preflight isteği
de model kimliğini taşır; runner kendi sabit kimliğiyle uyuşmayan manifesti
reddeder. Bu yolların veya iş verisinin loglanması sözleşme dışıdır.

Çalıştırıcı yanıtı `outputDir/.adapter-response.json` dosyasına en fazla 4096
baytlık JSON olarak atomik biçimde yazmalıdır:

```json
{"result":"result.zip"}
```

Runner kendisi için yalnız iki hata kodu bildirebilir: kaynak sınırı sonucu
güvenle üretmeyi engellerse `{"error":"resource-exhausted"}`, girdi modelin
sözleşmesinin dışındaysa `{"error":"input-invalid"}`. Executor bu ikisi dışında
yazılan her kodu okunamaz yanıt sayar; runner işin gerekçesini kendisi seçemez.
Başka hata metni, dosya yolu veya hasta metadata'sı süreç sınırından geçirilmez.

Girdi sözleşmesi voxel ızgarasını da kapsar. Referans hat resample ve reorient
etmediği için checkpoint yalnız incelenen ızgarayı görmüştür: 1 mm izotropik,
LPS, eksen hizalı. Başka bir uzaydaki hacim aynı güvenle ve aynı yanlışlıkla
skorlanacağından `input-invalid` ile reddedilir; sessizce yeniden örneklenmez.

`preflight` için de aynı yanıt biçimi kullanılır; isim dikkate alınmaz. Sıfırdan
farklı çıkış, eksik/geçersiz yanıt, timeout veya cancel başarısızlıktır. Executor
dönen adı ayrıca spool sonuç sözleşmesiyle doğrular; path traversal, symlink,
yanlış model kimliği veya geçersiz ZIP başarılı sayılmaz.

## Isolation and lifecycle

- Linux Landlock ABI 3+ yoksa model capability ilan edilmez.
- Alt sürecin tek yazılabilir ağacı o işin `work/output` dizinidir.
- `TMPDIR`, `TEMP` ve `TMP` bu dizini gösterir; bytecode yazımı kapalıdır.
- `MERGEN_CONTROL_*`, `MERGEN_WORKER_*` ve `MERGEN_VPS_*` alt sürece geçmez.
- Alt süreç yeni bir süreç grubunda çalışır. Cancel/timeout önce SIGTERM, kısa
  grace süresinden sonra SIGKILL ile bütün grubu kapatır.
- stdout ve stderr kullanıcı verisinin servis loguna taşınmaması için yutulur.

Landlock okuma erişimini sınırlandırmaz. Runner kodu ve bağımlılıkları güvenilir
kabul edilir; ayrı uid/mount namespace ile okuma izolasyonu bu sözleşmenin v1
kapsamında değildir.

Yazma kapatmasının tek istisnası NVIDIA compute düğümleridir. CUDA sürücüsü
`/dev/nvidiactl`, `/dev/nvidia-uvm`, `/dev/nvidia-uvm-tools` ve `/dev/nvidia0`
düğümlerini `O_RDWR` açmak zorundadır; kural verilmezse sürücü hiç başlamaz ve
runner "GPU yok" diye kapanır — GPU'su olmayan bir hosttan ayırt edilemeyen bir
belirti. Her düğüm tek tek adlandırılır ve yalnız dosya hakları taşır, dolayısıyla
`/dev` altında komşu düğüm açılamaz, yeni giriş yaratılamaz, düğüm silinemez.
Liste unit dosyasının `DeviceAllow` satırlarıyla aynı olmak zorundadır.

## Ürün kuralı ve sonuç raporu

Runner iki üyeyi sırayla çalıştırır ve aralarında cihazı boşaltır: önce nnU-Net
beş fold (ölçülen tepe 3,1 GiB), sonra Swin UNETR fold 0 (4,4 GiB). Olasılıklar
UWCSE v3 kuralıyla birleştirilir (bölge ağırlıkları TC 0,425 / WT 0,697 /
ET 0,447; eşik 0,5), ardından BraTS son işlemesi (küçük bileşen, ET_MIN,
TC_MIN) uygulanır ve `review_flags` okunur. Kural kodu model venv'i içindeki
`mergen_imaging/uwcse.py`'dedir; `models/imaging/test_live_product_rule.py` onu
araştırma hattındaki `uwcse_ensemble.py` ile aynı hacimler üzerinde
karşılaştırır, ayrıldıklarında CI düşer.

`report.json` v2 şunları taşır: `modelId`/`modelVersion` (ürün kimliği),
`members` (hangi ağlar ve foldlar), `rule` (ağırlıklar ve eşikler),
`regionVolumes` (TC/WT/ET voxel), `reviewFlags` (bulgu, gerekçe, sayılar),
`voxelCounts` ve araştırma uyarısı.

Swin checkpoint'i SHA-256 ile doğrulandıktan sonra yüklenir. Yayımlanmış dosya
NumPy scalar metadata içerdiği için PyTorch `weights_only=True` ile açılamaz;
`weights_only=False` yalnız doğrulanmış, operatörce yerleştirilmiş bu dosyada ve
Landlock sınırı kurulmuş alt süreçte kullanılır.
