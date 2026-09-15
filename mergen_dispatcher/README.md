# GPU dispatcher (G2)

GPU hostunda VPS worker kontrol API'sinden iş çeken süreç. Worker token'ını bilen
tek MERGEN bileşenidir; model, alt süreç veya GPU cihazı çalıştırmaz. Executor ile
yalnız [`mergen_spool`](../mergen_spool/contract.py) sözleşmesi üzerinden konuşur.

## Bir işin yolu

```
executor.json taze ve acceptingJobs → heartbeat → claim
claim → staging/<id>-<rastgele>/input.zip   akış, boyut sınırı, SHA-256
      → backend.archive_io ile manifest; modül/hastalık claim'le aynı
      → job.json, fsync (dosyalar + dizin) → rename → jobs/<id>/
jobs/<id>/status.json:  (yok) → accepted → running → completed | failed
completed → iş kilidi; result.zip bir kez açılır: boyut + SHA-256 + sonuç sözleşmesi
          → aynı tanımlayıcıdan yükleme, özet yeniden hesaplanır → trash/
failed    → /failure (executor'ın kodu)                           → trash/
lease yok → cancel işareti; yükleme ve hata bildirimi yok          → trash/
trash/<id>-<rastgele>/ → executor kilidi bırakınca silinir
```

Yayım sırasında dispatcher iş dizininin kilidini ve doğruladığı tanımlayıcıyı
yükleme bitene kadar tutar. `result.zip` yol üzerinden değiştirilirse gönderilen
baytlar değişmez. Aynı dosya yerinde değiştirilirse yükleme sırasında hesaplanan
özet tutmaz, son parça gönderilmez ve iş `internal-error` ile bildirilir. VPS de
gövde `X-Mergen-Result-Sha256` başlığındaki özetle uyuşmadıkça işi tamamlamaz.

Lease iş boyunca ayrı bir iş parçacığında yenilenir. 409 gelirse ya da son
başarılı yenilemenin süresi dolarsa lease kayıp sayılır; o andan sonra hiçbir
sonuç yüklenmez. Yanıtı kaybolan bir yüklemenin yeniden denemesine VPS 409 döner;
dispatcher bunu yayımlanmış olabilecek bir iş sayar ve hata bildirmez.

`cancel` işareti iş dizinindeki `gate` dosyasına `flock(LOCK_EX)` alınarak yazılır;
executor da terminal durumu aynı kilit altında yazar. Bu yüzden executor işareti ya
kararından önce görür ya da kararını işaretten önce yazmıştır. Kilit en fazla 10
saniye beklenir; alınamazsa işaret yazılmaz. Bu durumda da hiçbir sonuç yüklenmez:
lease kaybından sonra dispatcher yükleme yapmaz, VPS de süresi dolmuş lease'e sonuç
kabul etmez.

Yeniden başlatmada `staging/` silinir, `trash/` süpürülür, `jobs/` altındaki her
iş için lease yenilenir: yanıt 200 ise iş devralınır, 409 ise `cancel` bırakılıp
atılır. Çözülmemiş yerel iş varken yeni iş alınmaz.

Başlarken kök dizinin (2770, setgid) yanında `staging/` (2700), `jobs/` (2750)
ve `trash/` (2700) dizinlerinin modunu, sahibini ve grubunu doğrular. Sözleşme
dışı bir durum onarılmaz; servis 2 koduyla durur.

## Çalıştırma ve test

Yapılandırma yalnız ortamdan okunur:
[`dispatcher.env.example`](../infra/gpu-host/dispatcher.env.example). Eksik ya
da güvensiz değer 2 çıkış koduyla durdurur; mesaj değişkenin adını verir,
değerini yazmaz. Loglar token, adres, URL, girdi içeriği veya tam iş kimliği
taşımaz.

```bash
python -m unittest discover -s mergen_dispatcher -t .
python -m unittest discover -s mergen_spool -t .
```

Unit örneği ve sürüm düzeni: [GPU host runbook](../docs/GPU_HOST_RUNBOOK.md), 16. adım.
