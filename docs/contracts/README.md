# Canlı iş sözleşmesi v1

Tarayıcı, `input.json` ve orada bildirilen dosyaları tek ZIP olarak
`POST /api/live/jobs` ucuna gönderir. Görüntü/glioma profili tam olarak birer T1,
T1CE, T2 ve FLAIR NIfTI hacmi ister.
İstek gövdesi multipart değildir; ZIP doğrudan `Content-Type: application/zip`
ile akış halinde gönderilir ve boyut sınırı veri alınırken uygulanır.

GPU worker sonucu `manifest.json` ve bildirilen tüm varlıkları içeren tek ZIP olarak
özel worker API'sine yükler. Canlı sonuçta `hasGroundTruth` daima `false` olur.
Worker sonuç ZIP'ini de doğrudan `application/zip` gövdesi olarak gönderir ve ZIP'in
SHA-256'sını `X-Mergen-Result-Sha256` başlığında bildirir; VPS gelen gövde bu özetle
uyuşmadıkça işi tamamlamaz (422).
Görüntü sonucu en az `report-json`, `prediction-nifti` ve `prediction-glb`
varlığı içerir. Her varlığın SHA-256 ve byte boyutu
yüklemede doğrulanır.

Bu dizindeki değerler yalnız sözleşme örneğidir; hasta kaydı, gerçek tahmin veya
model metriği değildir. Asıl doğrulama `backend/live_contracts.py` içindeki Pydantic
modelleriyle yapılır.

## GPU spool sözleşmesi v1

GPU hostunda dispatcher ile executor yalnız `MERGEN_RUNTIME_ROOT` altındaki ortak
dizin üzerinden konuşur; soket, token veya VPS adresi paylaşmazlar. Her dosyanın
tek yazarı vardır, bu yüzden iki süreç aynı dosyada yarışmaz:

| Yol | Yazar | Mod | Anlamı |
|---|---|---|---|
| `executor.json` | executor | — | Yetenekler ve şu an iş kabul edip etmediği |
| `staging/` | dispatcher | 2700 | Hazırlanan işler; executor göremez |
| `jobs/` | dispatcher | 2750 | Executor listeler ve girer; iş ekleyemez, taşıyamaz |
| `jobs/<jobId>/` | dispatcher | 2770 | Executor burada `status.json` ve `result.zip` yazar |
| `jobs/<jobId>/job.json` | dispatcher | — | Bir kez, yayından önce yazılır |
| `jobs/<jobId>/input.zip` | dispatcher | — | Checksum'ı doğrulanmış girdi |
| `jobs/<jobId>/cancel` | dispatcher | — | Boş işaret: lease kaybedildi, sonuç yayımlanmayacak |
| `jobs/<jobId>/gate` | dispatcher | — | `mergen-spool-gate 1`; `cancel` ile terminal durumu `flock` altında sıralar |
| `jobs/<jobId>/status.json` | executor | — | `accepted → running → completed/failed`; atomik değiştirilir |
| `jobs/<jobId>/result.zip` | executor | — | `completed` yazılmadan önce tamamlanır |
| `jobs/<jobId>/work/` | executor | 2770 | Adaptörün işe özel giriş/çıkış dizinleri; karardan önce silinir |
| `trash/` | dispatcher | 2700 | Kilit serbest kalınca silinir |

Kök dizin tmpfiles'tan 2770 gelir. Dispatcher başlarken `staging/`, `jobs/` ve
`trash/` için modu, sahibin kendisi olduğunu ve grubun kökün grubu olduğunu
doğrular; sözleşme dışı bir durumu onarmaz, 2 koduyla durur.

İş `staging/` altında hazırlanır; dosyalar ve dizin fsync edilir, sonra tek
`rename` ile `jobs/` altına taşınır, böylece executor yarım iş görmez. Executor bir
iş dizininde çalışırken dizine `flock(LOCK_EX)` alır; dispatcher dizini yalnız bu
kilidi kendisi alabildiğinde siler. Şemalar `mergen_spool/contract.py` içindedir;
örnekler `gpu-spool-job.v1.example.json`, `gpu-spool-status.v1.example.json` ve
`gpu-executor-ready.v1.example.json` dosyalarındadır.

Executor da başlarken kökü (2770, sahibi `MERGEN_SPOOL_OWNER`, grubuna üyelik) ve
`jobs/` dizinini (2750) doğrular. İşe yalnız kilitlediği dizin tanımlayıcısı
üzerinden erişir ve `job.json`, `input.zip`, `cancel` dosyalarını yalnız okur.
Durum `accepted → running → completed | failed` sırasıyla ilerler; terminal durum
yeniden yazılmaz. Sonuç `.result.zip.<rastgele>.tmp` adıyla yazılıp fsync edilir,
doğrulanır ve tek `rename` ile `result.zip` olur; `completed` ancak bundan sonra
yazılır. `cancel` varsa iş başlamaz; çalışırken gelirse sonuç yayımlanmaz.

## Hazır demo paketleri

Hazır demo paketleri canlı iş ZIP'lerinden ayrıdır. Kök katalog örneği
`demo-catalog.v3.example.json`, görüntü koleksiyonu örneği
`demo-imaging-manifest.v3.example.json` dosyasındadır. Katalog yalnız modül,
hastalık ve göreli manifest yolunu taşır; API bu disk yolunu tarayıcıya açmaz.
