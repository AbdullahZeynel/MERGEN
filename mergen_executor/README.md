# GPU executor (G3 + G4-A isolation)

GPU hostunda dispatcher'ın yayımladığı işleri teker teker çalıştıran süreç. Ağ
istemcisi, VPS adresi veya worker token'ı yoktur; dispatcher ile yalnız
[`mergen_spool`](../mergen_spool/contract.py) sözleşmesi üzerinden konuşur ve yalnız
`imaging/glioma` işini kabul eder.

## Bir işin yolu

```
kabul: adaptör hazır · pause yok · GPU probe boş · gpu.lock alındı  → acceptingJobs=true
jobs/<id> → flock(LOCK_EX); dosyalara yalnız dizin tanımlayıcısı üzerinden erişilir
  durum yok + cancel var             → dokunulmaz
  job.json (v1, bu iş, glioma), gate v1  ─✗→ failed
accepted
  input.zip boyut + SHA-256 = job.json, archive_io, work/input'a açma  ─✗→ failed
running
  adaptör: work/input → work/output   ─✗→ failed
  cancel?                             → failed(cancelled), sonuç yayımlanmaz
  .result.zip.<rastgele>.tmp → fsync → sonuç sözleşmesi → rename result.zip → fsync
  work/ silinir
  flock(gate) + cancel?               → result.zip geri çekilir, failed(cancelled)
completed(result: sha256, boyut)       aynı gate kilidi altında yazılır
```

Durum birer adım ilerler: başlangıç → `accepted` ya da `failed`, `accepted` →
`running` ya da `failed`, `running` → `completed` ya da `failed`. Adım atlanmaz,
geri gidilmez, tekrarlanmaz; terminal durum yeniden yazılmaz. Okunamayan bir
`status.json`'a dokunulmaz, iş başarılı sayılmaz. `job.json`, `input.zip`, `cancel`
ve `gate` dispatcher'ındır; yalnız okunur, `gate` ayrıca kilitlenir.

| Durum | Hata kodu |
|---|---|
| `job.json` geçersiz ya da başka işe ait; girdinin boyutu veya özeti `job.json`'la uyuşmuyor; `gate` yok, bağlantı ya da başka sürüm; karar anında `gate` 10 sn içinde alınamadı | `internal-error` |
| Hastalık `glioma` değil; girdi arşivi sözleşmeye uymuyor; girdi executor sınırını aşıyor | `input-invalid` |
| Adaptörün `AdapterFailure` kodu (sözleşme dışıysa `internal-error`) | olduğu gibi |
| Adaptör istisnası; sonuç eksik, bağlantı, geçersiz ya da başka işe ait; sonucun `modelId`/`modelVersion`'ı adaptörün ilan ettiği model değil | `inference-failed` |
| Bellek bitti, sonuç sınırı aşıldı, disk doldu | `resource-exhausted` |
| Karardan önce görülen `cancel` işareti (`rename`'den sonra gelse de) | `cancelled` |

## Kilit, cancel ve yeniden başlatma

- Tek inference: işi başlatan süreç `MERGEN_GPU_LOCK_PATH` üzerinde `flock` tutar;
  kilit başkasındaysa iş başlamaz ve `acceptingJobs=false` yazılır.
- İş dizininin kilidi karar yazılana kadar tutulur; dispatcher sonucu doğrulamak
  ve dizini silmek için aynı kilidi bekler.
- `cancel` başlamadan önce varsa iş hiç açılmaz. Adaptör çalışırken `cancelled()`
  doğru döner; adaptör döndükten ve `rename`'den hemen önce yeniden bakılır.
- Bu bakışlar yalnız gereksiz işi keser; sırayı `gate` belirler. Her terminal durum
  `gate` üzerinde `flock` tutulurken ve `cancel`'a son kez bakıldıktan sonra yazılır;
  dispatcher `cancel`'ı yalnız aynı kilit altında oluşturur. `rename`'den sonra ama
  karardan önce gelen `cancel` `result.zip`'i geri çektirir ve iş `failed/cancelled`
  olur. Karardan sonra gelen `cancel` kararı değiştirmez; dispatcher o işin sonucunu
  zaten yüklemez. Kilit adaptör çalışırken tutulmaz. Ayrıntı:
  [spool sözleşmesi](../docs/contracts/README.md).
- Başlarken: bayat `executor.json` `acceptingJobs=false` ile değiştirilir, geçici
  dosyalar ve `work/` silinir, `accepted`/`running` kalmış işler
  `failed/internal-error` olur ve `completed` olmayan bir `result.zip` silinir.
- Pause dosyası veya meşgul GPU yeni işi başlatmaz; çalışan iş biter. Executor
  kullanıcının GPU süreçlerine dokunmaz.

## Adaptör arayüzü ve süreç sınırı (G4-A)

`mergen_executor.adapter.ImagingAdapter`, gerçek modelin takılacağı tek yerdir:

- `model_id` (slug) ve `model_version` (`ResultManifest.modelVersion` biçimi: harf
  ya da rakamla başlar, en çok 64 karakter, yalnız `A-Za-z0-9._+-`) başlarken sonuç
  sözleşmesinin kurallarıyla doğrulanır. Geçersizse `preflight()` çağrılmaz ve
  hiçbir yetenek ilan edilmez. Her sonucun `manifest.json`'ı başlarken doğrulanan
  bu kimliği aynen taşımalıdır; değilse iş `failed/inference-failed` olur.
- `preflight()` model hazır değilse `AdapterFailure("model-unavailable")` fırlatır;
  o zaman hiçbir yetenek ilan edilmez.
- `run(job)` doğrulanmış bir `ImagingJob` alır: `volumes` (T1, T1CE, T2, FLAIR →
  `work/input` altındaki NIfTI dosyaları), boş `output_dir`, `max_result_bytes` ve
  `cancelled()`. Sonuç ZIP'ini `output_dir`'e yazar ve yalnız dosya adını döndürür.
  ZIP, bu iş için `backend.live_contracts.ResultManifest`'e uyan `manifest.json` ile
  en az `report.json`, `prediction.nii.gz` ve `prediction.glb` taşır.
- Adaptör VPS'i, dispatcher'ı, token'ı veya spool yönetimini bilmez. Yalnız
  `output_dir`'e yazabilir.

`MERGEN_MODEL_ROOT` ve `MERGEN_IMAGING_VENV` birlikte ayarlanırsa
`ProcessImagingAdapter` seçilir. Model kökündeki bakım hesabınca yönetilen
`manifest.json`;
şema sürümünü, model kimliğini, çalıştırıcı modülünü ve her checkpoint'in göreli
yol/boyut/SHA-256 değerini taşır. Eksik, bağlantı üzerinden ulaşılan veya özeti
yanlış bir checkpoint capability olarak ilan edilmez. Biçim:
[`MODEL_RUNNER.md`](../docs/contracts/MODEL_RUNNER.md).

Çalıştırıcı executor'dan ayrı süreçte ve ayrı venv Python'ıyla çalışır. Linux
Landlock ABI 3+, bütün dosya sistemi yazma haklarını ele alıp yalnız o işin
`work/output` ağacına izin verir; destek yoksa preflight kapalı başarısız olur.
Alt süreç yeni bir oturum/süreç grubundadır. Cancel veya zaman aşımında önce
SIGTERM, `MERGEN_ADAPTER_TERM_GRACE_SECONDS` sonra SIGKILL uygulanır; başarıyla
dönen çalıştırıcının bıraktığı torun süreçler de öldürülür. Kontrol/worker/VPS
önekli ortam anahtarları alt sürece aktarılmaz ve stdout/stderr loga bağlanmaz.

Bu sınır yazma ve yaşam döngüsü sınırıdır; çalıştırıcı `mergen-executor`
kullanıcısıyla çalıştığı için executor'ın okuyabildiği dosyaları okuyabilir.
Model ağacı ve venv bu nedenle yalnız güvenilir bakım hesabınca yönetilmeli,
model kodu güvenilir olmalı ve hostta gerçek hasta verisi kullanılmadan önce okuma sınırı ayrıca
değerlendirilmelidir.

Bu değişiklik gerçek Swin çalıştırıcısını, NVML/CUDA model preflight'ını veya
NVIDIA `DeviceAllow` ayarını eklemez. `MERGEN_IMAGING_VENV` boş kaldığı sürece
adaptör yoktur ve executor capability ilan etmez; G4-B gelmeden servisleri canlı
iş kabul edecek biçimde açmayın.

## Çalıştırma ve test

Yapılandırma yalnız ortamdan okunur:
[`executor.env.example`](../infra/gpu-host/executor.env.example). Geçersiz değer
veya güvensiz spool 2 çıkış koduyla durdurur. Loglar yalnız 8 karakterlik iş
etiketi, durum, hata kodu ve istisna türü taşır.

```bash
python -m unittest discover -s mergen_executor -t .
```
