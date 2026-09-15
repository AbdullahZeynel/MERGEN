# Model runner contract v1

G4-A'da executor ile görüntü modeli aynı Python ortamını veya süreci paylaşmaz.
Bu dosya yerel süreç sınırını tanımlar; VPS, ağ ve dispatcher sözleşmesi değildir.

## Operator-managed model manifest

`MERGEN_MODEL_ROOT/manifest.json` UTF-8 JSON'dur:

```json
{
  "schemaVersion": 1,
  "modelId": "swin-unetr-brats21",
  "modelVersion": "fold0-f48-ep300",
  "runnerModule": "mergen_imaging.runner",
  "checkpoints": [
    {
      "path": "pretrained_models/model.pt",
      "size": 123,
      "sha256": "64 lowercase hex characters"
    }
  ]
}
```

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
modalite yolunu, model kimliğini ve azami sonuç boyutunu taşır. Bu yolların veya
iş verisinin loglanması sözleşme dışıdır.

Çalıştırıcı yanıtı `outputDir/.adapter-response.json` dosyasına en fazla 4096
baytlık JSON olarak atomik biçimde yazmalıdır:

```json
{"result":"result.zip"}
```

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
