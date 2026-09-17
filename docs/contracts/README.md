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
üzerinden erişir; `job.json`, `input.zip` ve `cancel` dosyalarını yalnız okur,
`gate`'i yalnız kilitler. Executor durumu birer adım ilerletir: başlangıç →
`accepted` ya da `failed`, `accepted` → `running` ya da `failed`, `running` →
`completed` ya da `failed`. Adım atlanmaz, terminal durum yeniden yazılmaz. Durumu
okuyan dispatcher ara adımları kaçırabilir; bu yüzden yalnız geri gitmeyi ve
terminal durumdan çıkmayı reddeder. Sonuç `.result.zip.<rastgele>.tmp` adıyla
yazılıp fsync edilir, doğrulanır ve tek `rename` ile `result.zip` olur; `completed`
ancak bundan sonra yazılır. Sonucun `manifest.json`'ındaki `modelId` ve
`modelVersion`, adaptörün başlarken doğrulanan kimliğiyle aynı olmalıdır; değilse
iş `failed/inference-failed` olur. `cancel` varsa iş başlamaz.

### `cancel` ile kararın sırası

`cancel`'a bakıp sonra `completed` yazmak, arada `cancel`'ın gelebileceği bir boşluk
bırakır; ikinci bir bakış bu boşluğu yalnız daraltır, kapatmaz. Boşluğu `gate`
kapatır:

- Dispatcher `cancel`'ı yalnız `gate` üzerinde `flock(LOCK_EX)` tutarken oluşturur.
- Executor her terminal durumu (`completed` ve `failed`) aynı kilidi tutarken ve
  `cancel`'a son kez baktıktan sonra yazar. Bu bakış ile yazma karşı taraf için tek
  adımdır.
- Kilidi önce alan sırayı belirler. `cancel` önceyse executor `result.zip`'i geri
  çeker ve `failed/cancelled` yazar. Karar önceyse `cancel` kararı değiştirmez:
  dispatcher `cancel`'ı yalnız sonucunu yüklemeyeceği bir iş için yazar (lease kaybı
  ya da VPS'e bildirilen hata) ve ardından dizini atar; VPS de süresi dolmuş lease
  için sonuç kabul etmez.
- Kilit adaptör çalışırken tutulmaz; `cancel` çalışan işe hemen görünür. `flock`
  sahibi ölünce bırakılır, çöken bir süreç kilidi tutulu bırakamaz.
- `gate`'i olmayan, bağlantı olan ya da başka sürümde `gate`'i olan iş çalıştırılmaz
  (`failed/internal-error`). Executor kilidi 10 sn içinde alamazsa `completed`
  yazmaz, iş `failed/internal-error` olur; dispatcher alamazsa işareti yazmaz ve yine
  hiçbir şey yüklemez.

## Hazır demo paketleri

Hazır demo paketleri canlı iş ZIP'lerinden ayrıdır. Kök katalog örneği
`demo-catalog.v3.example.json`, görüntü koleksiyonu örneği
`demo-imaging-manifest.v3.example.json` dosyasındadır. Katalog yalnız modül,
hastalık ve göreli manifest yolunu taşır; API bu disk yolunu tarayıcıya açmaz.

### Paket v4 — patoloji koleksiyonu ve doğrulama figürleri

v4 kök kataloğun şemasını değiştirmez (`schemaVersion: 3`; modül, hastalık ve
göreli manifest yolu). Yeni olan iki şey koleksiyon manifestlerindedir.

**`pathology/glioma`** (`demo-pathology-manifest.v4.example.json`,
`schemaVersion: 4`): her vaka `prediction.class` ile üç sınıfın olasılığını,
varsa `reference.class` ve `agreesWithReference`'ı, `needsExpertReview`,
`attentionConcentration`, `split`, `whoGrade`, `sourceSite`, `tilesUsed` ve
`assets` alanlarını taşır. `assets` bildirilen varlık türünü kanonik genel yola
eşler (`attention`, `top_tiles`, `thumbnail`, `report`); store yalnız bildirilen
türü okur. Manifest uyguladığı `reviewMargin`'i bildirmek zorundadır ve yükleme
sırasında üç iddia yeniden hesaplanır: `needsExpertReview` ilk iki olasılığın
farkı eşiğin altındaysa `true` olmalıdır, `agreesWithReference` tahmin ile
referansın gerçek karşılaştırması olmalıdır (referans yoksa alan hiç bulunmaz) ve
her `assets` yolu vakanın kendi yolu olmalıdır. Tutmayan manifest yüklenmez.

**`imaging/glioma`** (`demo-imaging-manifest.v4.example.json`): isteğe bağlı ölçüm
bloğu (`regionVolumes` → `reference`/`prediction` × TC/WT/ET voxel, `dice`,
`hd95Mm`, `reviewFlags`) ve `examples` dizisi. **Referans hacmi bildirilmeden
`dice` veya `hd95Mm` yazılamaz**; karşılaştıracak şeyi olmayan bölge `null`
kalır. `examples` vaka değildir: her kayıt `kind: "figure"`, kendi
`ruleVersion`'ı ve kanonik `figure` yolunu taşır, vaka listesinde ve vaka
uçlarında görünmez. Hangi kuralın ürettiği vaka kaydından ayrı okunur; başka bir
kuralla ölçülmüş figür vakanın kendi sayısı gibi sunulamaz.

Hiçbir vaka kaydı başka bir vakanın ya da koleksiyonun varlığına işaret edemez:
kayıttaki her `/api/...` yolu o vakanın kendi ön ekiyle başlamalıdır. Bu, iki
modülün aynı hastayı paylaştığı izlenimini manifest düzeyinde engeller.

Boş bölge okuması arayüzün işidir: hem referans hem tahmin sıfır voxel iken Dice
1,0 olur. Bu sayı "mükemmel bölge" değil "iki tarafta da yok" demektir; arayüz
hacimlere bakıp bölgenin yokluğunu söylemelidir.
