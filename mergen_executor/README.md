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

## Adaptör arayüzü (G4)

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
  `output_dir`'e yazmak ve `cancelled()`'a uymak sözleşmesinin parçasıdır; G3'te
  bunu zorlayan bir mekanizma yoktur.

G3 üretim kaydında adaptör yoktur (`default_imaging_adapter()` → `None`); testler
sahte adaptörle koşar. Gerçek görüntü adaptörü, NVML/CUDA preflight'ı ve NVIDIA
cihaz izinleri G4'tedir.

### G3'te adaptör güvenilir koddur, güvenlik sınırı değildir

Adaptör executor sürecinin içinde, aynı kullanıcı (`mergen-executor`) ve grupla
(`mergen-svc`), executor'ın açık dosyaları ve belleğiyle çalışır. Bu yüzden:

- Executor'ın yazabildiği her yere yazabilir: `/var/lib/mergen/executor` ve
  `/var/lib/mergen/runtime` altındaki her şey; başka işlerin dizinleri,
  `status.json`, `result.zip`, `executor.json` ve dispatcher'ın grup-yazılabilir
  dosyaları dahil. Adaptöre yalnız `work/input` ve `work/output` yollarının
  verilmesi onu bu dizinlere kapatmaz;
  `test_the_adapter_is_handed_job_specific_paths` yalnız hangi yolların verildiğini
  doğrular.
- Executor'ın durumunu ve kodunu (kilitler, `finalize`, `cancelled()`, beklenen
  model kimliği) değiştirebilir ve `cancel`'ı yok sayabilir. Zaman aşımı yoktur;
  executor'ın adaptörü tek başına durdurma yolu yoktur, yalnız servisin tamamı
  durdurulabilir.
- Unit'teki `ProtectSystem=strict`, `ReadWritePaths`, `PrivateNetwork=true` ve
  diğer kısıtlar gerçek bir OS sınırıdır, ama bütün servisin çevresindedir;
  adaptörle executor arasında sınır yoktur.

Dispatcher'ın özet ve boyut doğrulaması, arşiv denetimi ve VPS'in yeniden
doğrulaması bozuk bir sonucun VPS'e ulaşmasını sınırlar; adaptörün yerel dosyalara
yazmasını engellemez.

Gerçek bir adaptör etkinleştirilmeden önce G4 şunları sağlamalı ve testle
kanıtlamalıdır:

1. Adaptör ayrı bir süreçte ve ayrı, kilitli bir venv'de çalışır; executor'ın
   belleğini, açık dosyalarını ve spool kilitlerini devralmaz.
2. Adaptör kendi süreç grubunda başlar; zaman aşımında, `cancel`'da ve executor
   dururken bütün grup sonlandırılır (önce SIGTERM, süre dolunca SIGKILL).
3. Yazma alanı OS düzeyinde yalnız o işin `work/output`'una daraltılır (ayrı uid
   ya da mount namespace); spool'un geri kalanına, `executor.json`'a ve durum
   dizinine yazma denemesinin başarısız olduğu test edilir.

## Çalıştırma ve test

Yapılandırma yalnız ortamdan okunur:
[`executor.env.example`](../infra/gpu-host/executor.env.example). Geçersiz değer
veya güvensiz spool 2 çıkış koduyla durdurur. Loglar yalnız 8 karakterlik iş
etiketi, durum, hata kodu ve istisna türü taşır.

```bash
python -m unittest discover -s mergen_executor -t .
```
