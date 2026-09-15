# GPU executor (G3)

GPU hostunda dispatcher'ın yayımladığı işleri teker teker çalıştıran süreç. Ağ
istemcisi, VPS adresi veya worker token'ı yoktur; dispatcher ile yalnız
[`mergen_spool`](../mergen_spool/contract.py) sözleşmesi üzerinden konuşur ve yalnız
`imaging/glioma` işini kabul eder.

## Bir işin yolu

```
kabul: adaptör hazır · pause yok · GPU probe boş · gpu.lock alındı  → acceptingJobs=true
jobs/<id> → flock(LOCK_EX); dosyalara yalnız dizin tanımlayıcısı üzerinden erişilir
  durum yok + cancel var             → dokunulmaz
  job.json (v1, bu iş, glioma)       ─✗→ failed
accepted
  input.zip boyut + SHA-256 = job.json, archive_io, work/input'a açma  ─✗→ failed
running
  adaptör: work/input → work/output   ─✗→ failed
  cancel?                             → failed(cancelled), sonuç yayımlanmaz
  .result.zip.<rastgele>.tmp → fsync → sonuç sözleşmesi → rename result.zip → fsync
completed(result: sha256, boyut)       work/ bu karardan önce silinir
```

Terminal durum yeniden yazılmaz; durum geri gitmez ve tekrarlanmaz. Okunamayan bir
`status.json`'a dokunulmaz, iş başarılı sayılmaz. `job.json`, `input.zip` ve
`cancel` dispatcher'ındır ve yalnız okunur.

| Durum | Hata kodu |
|---|---|
| `job.json` geçersiz ya da başka işe ait; girdinin boyutu veya özeti `job.json`'la uyuşmuyor | `internal-error` |
| Hastalık `glioma` değil; girdi arşivi sözleşmeye uymuyor; girdi executor sınırını aşıyor | `input-invalid` |
| Adaptörün `AdapterFailure` kodu (sözleşme dışıysa `internal-error`) | olduğu gibi |
| Adaptör istisnası; sonuç eksik, bağlantı, geçersiz ya da başka işe ait | `inference-failed` |
| Bellek bitti, sonuç sınırı aşıldı, disk doldu | `resource-exhausted` |
| `cancel` işareti | `cancelled` |

## Kilit, cancel ve yeniden başlatma

- Tek inference: işi başlatan süreç `MERGEN_GPU_LOCK_PATH` üzerinde `flock` tutar;
  kilit başkasındaysa iş başlamaz ve `acceptingJobs=false` yazılır.
- İş dizininin kilidi karar yazılana kadar tutulur; dispatcher sonucu doğrulamak
  ve dizini silmek için aynı kilidi bekler.
- `cancel` başlamadan önce varsa iş hiç açılmaz. Adaptör çalışırken `cancelled()`
  doğru döner; adaptör döndükten ve `rename`'den hemen önce yeniden bakılır.
- Başlarken: bayat `executor.json` `acceptingJobs=false` ile değiştirilir, geçici
  dosyalar ve `work/` silinir, `accepted`/`running` kalmış işler
  `failed/internal-error` olur ve `completed` olmayan bir `result.zip` silinir.
- Pause dosyası veya meşgul GPU yeni işi başlatmaz; çalışan iş biter. Executor
  kullanıcının GPU süreçlerine dokunmaz.

## Adaptör sınırı (G4)

`mergen_executor.adapter.ImagingAdapter`, gerçek modelin takılacağı tek yerdir:

- `preflight()` model hazır değilse `AdapterFailure("model-unavailable")` fırlatır;
  o zaman hiçbir yetenek ilan edilmez.
- `run(job)` doğrulanmış bir `ImagingJob` alır: `volumes` (T1, T1CE, T2, FLAIR →
  `work/input` altındaki NIfTI dosyaları), boş `output_dir`, `max_result_bytes` ve
  `cancelled()`. Sonuç ZIP'ini `output_dir`'e yazar ve yalnız dosya adını döndürür.
  ZIP, bu iş için `backend.live_contracts.ResultManifest`'e uyan `manifest.json` ile
  en az `report.json`, `prediction.nii.gz` ve `prediction.glb` taşır.
- Adaptör VPS'i, dispatcher'ı, token'ı veya spool yönetimini bilmez; başka bir yere
  yazmaz. Sistem sınırı unit'teki `ProtectSystem=strict` ve `ReadWritePaths`'tir.

G3 üretim kaydında adaptör yoktur (`default_imaging_adapter()` → `None`); testler
sahte adaptörle koşar. Gerçek görüntü adaptörü, NVML/CUDA preflight'ı ve NVIDIA
cihaz izinleri G4'tedir.

## Çalıştırma ve test

Yapılandırma yalnız ortamdan okunur:
[`executor.env.example`](../infra/gpu-host/executor.env.example). Geçersiz değer
veya güvensiz spool 2 çıkış koduyla durdurur. Loglar yalnız 8 karakterlik iş
etiketi, durum, hata kodu ve istisna türü taşır.

```bash
python -m unittest discover -s mergen_executor -t .
```
