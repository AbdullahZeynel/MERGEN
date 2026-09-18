# Canlı sistem ve model entegrasyonu sprintleri

Bu belge; mevcut VPS demosunu bozmadan görüntü modelini canlı sisteme
bağlama sırasını tanımlar. Kaynak veri, ağırlık ve gerçek çalışma çıktıları Git'e
girmez. Her sprint ayrı, kısa ömürlü bir dalda tamamlanır ve kabul ölçütleri
geçmeden sonraki sprint birleştirilmez.

## Mimari kararlar

```text
Tarayıcı
   │ HTTPS
   ▼
Caddy ──► VPS API ──► oturum + kuyruk + geçici dosya alanı
              │                                  ▲
              │ Tailscale                        │ sonuç yükleme
              ▼                                  │
       Yerel GPU iş istasyonu                    │
       ┌─────────────────────┐                   │
       │ dispatcher          │───────────────────┘
       │ claim/lease/transfer│
       └──────────┬──────────┘
                  │ Unix socket / yerel spool
       ┌──────────▼──────────┐
       │ executor            │
       │ doğrulama + GPU lock│
       └──────────┬──────────┘
                  └── görüntü adaptörü + venv

VPS API ──► salt okunur demo MCP ──► hazırlanmış demo paketleri
```

- MCP yalnızca yayımlanabilir, önceden hazırlanmış demo dosyalarını okur. Yükleme,
  oturum, kuyruk ve model çalıştırma API/worker katmanındadır. GPU makinesinde MCP
  gerekli değildir; ileride LLM araç çağrıları için ayrıca değerlendirilebilir.
- GPU hostundaki dispatcher işi VPS kuyruğundan **pull** eder. Böylece ev ağında
  model portu açılmaz. VPS, hosta bağlantı başlatmaz; claim, indirme ve sonuç
  yükleme Tailscale üzerinden dispatcher tarafından yapılır.
- Dispatcher ağ kimliği, lease ve dosya aktarımını; executor ise giriş doğrulama,
  adaptör seçimi ve GPU çalıştırmayı yönetir. Aralarındaki sürümlü yerel sözleşme
  Unix socket veya sınırlandırılmış spool dizini üzerinden kurulur.
- Home dizini ve sınırlı bakım sudo'su bulunan `mergen` insan/operatör hesabıdır.
  Uzun süre çalışan dispatcher ve executor, login ve sudo yetkisi bulunmayan ayrı
  servis hesaplarıyla çalışır.
- Host günlük kullanım ile inference işlerini paylaşır. Worker kullanıcıya ait GPU
  süreçlerini sonlandırmaz; tek iş kilidi, yapılandırılabilir VRAM/kullanım eşiği ve
  bakım duraklatmasıyla GPU meşgulse claim'i erteler.
- Tarayıcı model servisine, MCP'ye veya Tailscale adresine doğrudan bağlanmaz.
- Demo ve canlı sonuç birbirine dönüşmez. Canlı GPU erişilemiyorsa açık hata veya
  kuyruk durumu gösterilir.
- Sistem yalnız `imaging/glioma` profilini kabul eder; bilinmeyen modül veya
  hastalık güvenli biçimde reddedilir.

## Veri düzeni ve sözleşme

Hazır demo paketinin önerilen üçüncü sürümü:

```text
/srv/mergen/demo-v3/
  catalog.json
  imaging/
    glioma/
      manifest.json
      cases/<case-id>/
        input.json
        slices/<modality>/<axis>/<index>.png
        overlays/prediction/<axis>/<index>.png
        overlays/ground-truth/<axis>/<index>.png
        meshes/prediction.glb
        meshes/ground-truth.glb
        volumes/prediction.nii.gz
    <future-disease>/...
```

Katalog kaydı en az şu alanları taşır: `schemaVersion`, `module`, `disease`,
`caseId`, `mode`, `modelId`, `modelVersion`, `inputKind`, `hasPrediction`,
`hasGroundTruth` ve varlık referansları. Kimlikler modül içinde benzersizdir.

2D görünüm taban MR kesiti ile şeffaf maske katmanlarını ayrı ister. Kullanıcı
“Tahmin” ve, yalnızca mevcutsa, “Referans etiket” katmanlarını bağımsız açıp
kapatır ve opaklığı değiştirir. Canlı vakada `hasGroundTruth=false` olur; arayüz
referans düğmesini ve Dice gibi referansa bağlı metrikleri göstermez. Demo vakada
tahmin dolgu, referans sınır çizgisi olarak gösterilerek çakışma okunabilir tutulur.
Aynı kural 3D tahmin/referans mesh'leri için geçerlidir.

## Canlı oturum ve veri yaşam döngüsü

Canlı veri yalnızca şu dizinde tutulur:

```text
/srv/mergen/runtime/sessions/<opaque-session-id>/
  uploads/
  results/
  downloads/
```

- Oturum kimliği rastgele ve tahmin edilemez olur; kullanıcı dosya adı vaka
  kimliği yapılmaz. Tarayıcıya `HttpOnly`, `Secure`, `SameSite=Strict` cookie verilir.
- İstemci yaklaşık 30 saniyede bir heartbeat gönderir. Son etkinlikten sonra
  varsayılan **3 dakika** içinde oturum sona erer. Açık “Çıkış” çağrısı dizini ve
  kuyruk kayıtlarını hemen siler. Sekmenin kapanması güvenilir bir olay olmadığı
  için heartbeat zaman aşımı zorunludur. Ayrıca yapılandırılabilir mutlak oturum
  süresi bulunur.
- İş `queued`, `claimed`, `running`, `completed`, `failed`, `expired` durumlarından
  geçer. Worker lease kullanır; süresi dolan iş başka worker tarafından alınabilir.
  Aynı iş iki kez sonuç yayımlayamaz.
- Dispatcher girdiyi işe özel geçici dizine indirir; executor yalnız bu iş dizinini
  görür. Dispatcher sonucu VPS'ye yükledikten sonra yerel kopyayı `finally`
  temizliğiyle kaldırır. Başlangıçta kalmış dizinleri süpüren ayrı bir temizlik
  görevi bulunur.
- VPS temizleyicisi her dakika sona eren oturumları, ilişkili dosyaları ve iş
  satırlarını kaldırır. Uygulama logları dosya adı, payload veya
  oturum kimliğinin tamamını içermez; yalnızca toplu süre/hata kodu tutulur.
- Oturum silme, dizini önce aynı dosya sistemindeki `.trash/sessions` alanına
  atomik taşıyıp veritabanı satırını kaldırır. Yeniden başlatma, yarım kararı
  satırın varlığına göre geri alır veya tamamlar. Eski ve kesin protokol adına
  sahip sahipsiz upload/job/session yolları silinmeden `.quarantine` alanına
  taşınır; yeni yollar aktif isteklerle karışmaması için varsayılan bir saatlik
  grace süresi dolmadan orphan sayılmaz.
- SSD'de dosya silmek fiziksel blokların anında geri döndürülemez silindiğini garanti
  etmez. Host disk şifrelemesi, kısa saklama süresi ve yedeklere runtime dizinini
  almamak tasarımın parçasıdır. Bu teknik tasarım tek başına KVKK uygunluk beyanı
  değildir; aydınlatma, açık rıza/hukuki dayanak, erişim ve olay süreçleri ayrıca
  ele alınmalıdır.
- Sunum için kullanılan kamuya açık demo paketi bu yaşam döngüsünden ayrıdır ve
  oturum kapanınca silinmez.

## İndirilebilir çıktılar

Her canlı görüntü işi, oturum açıkken tek ZIP üretir:

```text
MERGEN-<job-id>.zip
  report.json
  report.pdf                 # rapor sprintinde
  prediction.nii.gz          # voxel maskesi, affine/spacing korunur
  prediction.glb             # 3D görüntüleyicide doğrudan açılabilir yüzey
  checksums.sha256
  README.txt                 # formatlar, model sürümü ve klinik prototip notu
```

`NIfTI (.nii.gz)` 3D Slicer/ITK-SNAP gibi tıbbi görüntü araçları için asıl bilimsel
çıktıdır. `GLB` web/3D araçlarında hazır açılan görselleştirme kopyasıdır; NIfTI'nin
yerini tutmaz. DICOM SEG ancak kaynak DICOM kimlikleri ve geometrisi doğrulanıp ayrı
bir sprintte uygulanır. İndirme yanıtı `no-store` olur ve oturum sahipliği her
istekte doğrulanır.

## Sprint sırası

| Sprint / dal | Kapsam | Kabul ölçütü |
|---|---|---|
| S0 — `docs/live-system-contracts` | Bu kararları API şemalarına çevir; demo-v3 katalog, vaka, iş, sonuç ve hata sözleşmelerini örnek JSON'larla tanımla | Demo/canlı ve prediction/ground-truth alanları sözleşme testlerinden geçer |
| S1 — `feat/demo-catalog-v3` | Demo dosyalarını modül ve hastalık bazında üret; MCP'ye filtreli katalog/asset araçları ekle; mevcut iki glioma demosunu taşı | v2 geri dönüş veya kontrollü tek seferlik geçiş çalışır; bilinmeyen modül/hastalık/vaka reddedilir; mevcut site kesintisiz açılır |
| S2 — `feat/imaging-overlays-export` | Prediction ve ground-truth 2D overlay üretimi, ayrı 3D katmanlar, NIfTI+GLB export; frontend katman düğmeleri | Demo vakada iki katman bağımsız açılır; canlı sözleşme fixture'ında GT görünmez; eksen/indeks/affine tutarlılık testi geçer |
| G0 — `docs/native-gpu-host-audit` | Paylaşımlı host envanteri, dosya sistemi/şifreleme, mevcut NVIDIA kullanımı, snapshot/rollback ve runtime'ın yedek dışı bırakılması | Kurulum öncesi geri dönüş noktası ve geri yükleme adımı doğrulanır; hasta verisi/sırlar snapshot kapsamına girmez |
| G1 — `chore/native-gpu-host-bootstrap` | `mergen` bakım hesabı, ayrı yetkisiz servis hesapları, dizin/izin standardı, Tailscale ACL, sürücü ve CUDA'lı PyTorch doğrulaması | Servisler sudo/login olmadan çalışır; sırlar ayrılır; yeniden başlatma sonrası Tailscale ve GPU smoke testi geçer |
| G2 — `feat/gpu-dispatcher` | Eski pull-worker çekirdeğini dispatcher'a uyarla; claim, lease, checksum, indirme, sonuç yükleme, yeniden deneme ve temizlik | Sahte executor ile uçtan uca iş tamamlanır; ağ kesintisi/yeniden başlatmada iş kaybolmaz veya iki kez yayımlanmaz |
| G3 — `feat/gpu-executor` | Yerel iş sözleşmesi, manifest doğrulama, adaptör registry, `flock`, GPU boşluk eşiği, pause/resume ve systemd sınırları | Meşgul GPU'da iş ertelenir ve kullanıcı süreci öldürülmez; tek inference sınırı ile sahte adaptör testi geçer |
| G4 — `feat/gpu-model-adapter` | Kilitli görüntü ortamı, sürümlü model dizini, gerçek adaptör, başlangıç preflight'ı ve adaptörün süreç yalıtımı | Görüntü fixture'ı gerçek modelle çalışır; eksik ağırlık/şema capability olarak ilan edilmez; adaptör ayrı süreç ve venv'de, kendi süreç grubunda çalışır; zaman aşımı ve cancel bu grubu sonlandırır; yazma alanı OS düzeyinde işin `work/output`'una daraltılır ve dışına yazma denemesinin başarısız olduğu test edilir |
| G5 — `feat/live-end-to-end` | Mevcut VPS oturum/kuyruk katmanını dispatcher'a bağla; canlı UI, ilerleme, sonuç varlıkları ve ZIP indirme | Kullanıcı yalnız kendi işini görür/indirir; 3 dk idle/logout GPU+VPS kopyalarını siler; bağlantı kopması demo sonucu gibi görünmez |
| G6 — `chore/resilience-privacy-drill` | Yedek host, servis boot, disk sınırı, log denetimi, veri yaşam döngüsü ve sunum provası | GPU kapalıyken demo çalışır; yedek elle devreye alınır; 10 oturum/1 GPU işi ve temizlik kanıtı kaydedilir |
| M1 — `feat/model-registry` | 17 Eylül 2026 kanıt arşivini `models/registry/` olarak al: kartlar, kaynaklı metrikler, envanter, geçersiz sonuçlar; atıflar ve yerel varlık konumları | `repo_guard` temiz; gerçek host yolu yok; kart içi bağlantılar çözülür; ürün/referans ayrımı kayıtta açık (#44) |
| M2 — `feat/uwcse-v3-rule` | `uwcse_ensemble.py` senkronu (`TC_MIN=250`, `review_flags`), nnU-Net/evaluate env taşıması, `models/pathology/` kodu; kural birim testleri ve CI adımı | Testler CI'da geçer; modüller torch'suz import edilir; demo vakalarının eski kuralla üretildiği belgelidir (#45) |
| M3 — `feat/demo-v4-pathology` | `pathology/glioma` koleksiyonu sözleşmesi; 12 WSI + 5 MRI örnek vakasından üretici; MCP/API varlık uçları | Bilinmeyen koleksiyon 404; yol koleksiyon kökü dışına çıkamaz; MRI ile WSI aynı vaka gibi sunulmaz; yanlış sınıflanan vakalar etiketli kalır (#46) |
| M4 — `feat/pathology-workspace` | Modül seçici, patoloji ekranı (thumbnail + attention, en yüksek kareler, A/O/G kartı, çekimserlik), MRI `review_flags` bandı, krediler, doğrulama bölümü, i18n | Sözleşme ve arayüz testleri; yalnız kilitli test sayıları ve üç uyarı birlikte; `MCP/VPS/spool` ekranda geçmez (#47) |
| M5 — GPU host görevi | Canlı MRI'ı UWCSE v3'e yükselt: nnunetv2, çoklu checkpoint manifesti, runner orkestrasyonu, 22 demo vakasının v3 ile yeniden üretimi | Fixture kabulü hostta geçer; `modelId` `mergen-uwcse`/`v3`; hacim ve bayraklar raporda (#48) |
| M6 — koşullu | Canlı patoloji: `pathology` capability, `infer_slide.py` sarmalı, slayt girdi sözleşmesi | Karar: slayt boyutu vs VPS yükleme sınırı; TEKNOFEST kapsamı (#49) |

S0–S2 demo ve sözleşme temeli `main` üzerinde bulunur. Yeni canlı yol G0 ile başlar;
G1, G0'ın geri dönüş ve veri kapsamı kararı olmadan uygulanmaz. G2 ile G3 yerel iş
sözleşmesi birleştikten sonra paralel ilerleyebilir. G4 ikisine, G5 gerçek G4
çıktısına bağlıdır. G6 bütün zincirin yayın kapısıdır. Frontend chunk ayrıştırması
ve demo mesh optimizasyonu bu zincirden bağımsız kısa performans sprintleridir.

M serisi 17 Eylül 2026 kanıt arşiviyle gelen ürün setini (MRI'da UWCSE v3, patolojide
DINOv2 + Attention-MIL) depoya ve arayüze taşır. M1–M4 GPU istemez ve sırayla
ilerler; M5 hostu ister ve G4/G5 ile birleşir; M6 ayrı bir karar bekler. Kanıt
arşivinin ürün seti, sayı okuma kuralları ve ürüne girmeyen modeller
[`models/registry/README.md`](../models/registry/README.md) içindedir.

### S1 güncel durum

`main`, kök katalog ile `module/disease/cases` ayrımını, filtreli MCP/API uçlarını,
22 görüntü vakasını içerir.
MCP eski v2 paketini okumaya, `/api/demo/cases` ise mevcut arayüzün beklediği v2
yanıtını vermeye devam eder. Böylece kod ve veri paketi VPS'ye ayrı adımlarda
alınabilir. Bilinmeyen koleksiyonlar 404 alır; varlık yolları seçilen koleksiyon
kökü dışına çıkamaz.

### Güncel dal durumu

`main` üzerinde canlı VPS temeli hazırdır: erişim kodlu ve CSRF korumalı oturum,
10 aktif oturum sınırı, ZIP
doğrulama, SQLite iş/lease kuyruğu, tek eşzamanlı claim, Tailscale'e bağlı worker
API'si, sonuç/varlık indirme ve 3 dakika temizlik timer'ı. Gerçek VPS kurulumu ve
dispatcher/executor ile uçtan uca prova yapılmadan G5 tamamlanmış sayılmaz.

### G2 güncel durum

`mergen_dispatcher` VPS'ten iş çeker, girdiyi boyut sınırı ve SHA-256 ile akış
halinde indirir, `backend.archive_io` sözleşmesiyle doğrular ve işi `staging/`
altında hazırlayıp fsync'ten sonra tek `rename` ile executor'a açar. Executor ile
yalnız sürümlü yerel spool sözleşmesi (`mergen_spool`, bkz.
[`contracts/README.md`](contracts/README.md)) üzerinden konuşur; model veya alt
süreç çalıştırmaz, GPU cihazı açmaz. Lease arka planda yenilenir; 409 veya son
bilinen süre dolarsa `cancel` işareti bırakır, sonucu yüklemez ve hata bildirmez.
Başlangıçta `staging/` silinir, yayımlanmış işler lease yenilemesiyle devralınır ya
da atılır. Sahte kontrol API'si ve sahte executor ile test edildi; gerçek hostta,
Tailscale üzerinden ve G3 executor'la uçtan uca denenmedi.

### G3 güncel durum

`mergen_executor` spool'dan başka kanalı olmayan, ağ istemcisi, VPS adresi veya
token'ı bulunmayan ayrı bir süreçtir ve yalnız `imaging` yeteneğini ilan eder.
Başlarken spool'un ve kendi durum dizininin izin, sahiplik ve grup üyeliğini
doğrular, bayat `executor.json`'u `acceptingJobs: false` ile değiştirir ve yarım
kalan işleri `failed/internal-error` yapar. Pause dosyası, enjekte edilen GPU
probe'u veya başka bir sürecin tuttuğu `gpu.lock` varken iş başlatmaz. İşi dizin
tanımlayıcısı üzerinden kilitler; `job.json`'u ve girdinin boyutunu/SHA-256'sını
yeniden doğrular, arşivi `backend.archive_io` ile denetleyip `work/input`'a açar ve
adaptöre işe özel giriş/çıkış dizinleri verir. Sonucu geçici adla kopyalar, fsync
eder, doğrular ve `rename` ile yayımlar; `completed` ancak bundan sonra yazılır.
Sonuç manifesti adaptörün başlarken doğrulanan `modelId`/`modelVersion`'ını
taşımalıdır; kimliği geçersiz adaptör hiçbir yetenek ilan etmez. Terminal kararı dispatcher'ın `cancel` işaretiyle aynı `gate` kilidi altında yazar;
`rename`'den sonra ama karardan önce gelen `cancel` sonucu geri çektirir ve iş
`failed/cancelled` olur.
G3'te gerçek model yoktur: model ortamı yapılandırılmazsa hiçbir yetenek ilan
edilmez ve testler sahte adaptörle koşar. Gerçek görüntü çalıştırıcısı,
NVML/CUDA model preflight'ı ve NVIDIA cihaz izinleri G4-B'dedir.

### G4-A güncel durum

Model sınırı executor'dan ayrı süreç ve ayrı venv olarak uygulanmıştır. Güvenilir
bakım hesabınca yönetilen sürümlü manifest; model kimliğini, runner modülünü ve her
checkpoint'in yol/boyut/SHA-256 değerini capability ilanından önce doğrular.
Runner yeni süreç grubunda çalışır; cancel ve timeout bütün grubu SIGTERM,
ardından SIGKILL ile kapatır. Linux Landlock ABI 3+ ile runner'ın bütün yazma
erişimi yalnız mevcut işin `work/output` ağacına açılır; destek yoksa preflight
kapalı başarısız olur. Kontrol/VPS/worker ortam anahtarları aktarılmaz ve alt
süreç çıktısı servis loguna bağlanmaz. Ayrıntılı yerel protokol:
[`contracts/MODEL_RUNNER.md`](contracts/MODEL_RUNNER.md).

G4-A okuma izolasyonu değildir: runner hâlâ `mergen-executor` kullanıcısıyla
çalışır ve bu hesabın okuyabildiği dosyaları okuyabilir. Kod/venv/model ağacı bu
nedenle güvenilir ve servis hesaplarınca yazılamaz olmalıdır. Bu sınırın üzerine
kurulan gerçek model davranışı G4-B'de izlenir.

### G4-B güncel durum

Swin UNETR fold-0 runner'ı, referans çıkarımdaki `FLAIR,T1CE,T1,T2` kanal sırası,
nonzero/channel-wise normalizasyon, 128³ pencere, 0.6 overlap ve 0.5 eşikle
uygulanmıştır. Modalitelerin şekil/affine uyuşmazlığı reddedilir; resample veya
sahte modalite üretilmez. Runner canlı sözleşmeye uyan rapor, uint8 BraTS NIfTI,
GLB ve checksummed `result.zip` üretir; ölçülmeyen Dice/klinik skor yazmaz.

Girdi sözleşmesi voxel ızgarasını kapsar: referans hat resample ve reorient
etmediğinden yalnız incelenen ızgara (1 mm izotropik, LPS, eksen hizalı) kabul
edilir, başkası `input-invalid` ile reddedilir. Runner kendisi için yalnız bu
kodu ve `resource-exhausted` kodunu bildirebilir.

Model ortamı tam sürümlere kilitlidir. Preflight ortam sürümlerini, CUDA'yı,
manifest kimliğini ve checkpoint `state_dict` uyumunu denetler. Executor GPU
bellek/kullanımını `nvidia-smi` metni yerine NVML C API ile fail-closed ölçer;
eşikler model venv'i etkinleştiğinde zorunludur. Unit yalnız dört NVIDIA compute
cihazını açar ve ağ namespace'i kapalı kalır.

### G4-A/G4-B arasındaki Landlock çakışması

G4-A'nın yazma kapatması bütün `/dev` düğümlerini de kapatıyordu. CUDA sürücüsü
`/dev/nvidiactl` ve kardeşlerini `O_RDWR` açmak zorunda olduğundan izole runner
sürücüyü hiç başlatamıyor, `torch.cuda.is_available()` sandbox içinde `False`
dönüyor ve preflight `model-unavailable` ile kapanıyordu. Belirti GPU'su olmayan
bir hosttan ayırt edilemediği için ilk ölçümde "bu makinede CUDA yok" diye
okunmuştu; oysa aynı venv sandbox dışında GPU'yu açıyor. Sandbox artık dört
compute düğümünü tek tek, yalnız dosya haklarıyla açar; unit'in `DeviceAllow`
listesiyle aynı olmak zorundadır ve `/dev` altında komşu düğüm, yeni giriş veya
silme hâlâ reddedilir.

### G4-B ölçümü

Sentetik, kimliksiz dört-modalite fixture'ı (`mergen_imaging.make_fixture`) izole
sınırdan uçtan uca geçti: RTX 5060 Laptop / 8151 MiB üzerinde çıkarım 41 s,
preflight dahil 57 s, tepe VRAM 5794 MiB, sonuç canlı `ResultManifest`
doğrulamasından geçti ve üç bölge de GLB'ye girdi. 2 mm'ye ölçeklenmiş aynı
fixture `input-invalid` ile reddedildi. Checkpoint'in 159 anahtarı strict
yüklendi. Kalan iş dispatcher/VPS kuyruğuyla uçtan uca kabuldür; o tamamlanmadan
G4 bitmiş sayılmaz.

### M1 güncel durum

Arşivin metin ve JSON'ları (131 dosya, 1,4 MB) `models/registry/` altında; figürler,
PDF ve örnek vaka klasörleri `.local/evidence-2026-09-17/` (Git dışı). Hostun gerçek
kullanıcı yolu 30 dosyada `<MERGEN_DATA_ROOT>` ile değiştirildi; arşivin kendi
yolları depo yerleşimine çevrildi ve kart içi bağlantıların tamamı çözülüyor.
Kartlar dondurulmuş anlık görüntüdür; üreten betikler hostta kaldığı için burada
yeniden üretilmez. Arşivin `uwcse_ensemble.py`'si depodakinden yenidir
(`TC_MIN`, `review_flags`); kod senkronu M2'dedir ve bugünkü 22 demo vakası
eski kuralla üretilmiştir.

### M2 güncel durum

`models/imaging/uwcse_ensemble.py` arşivle eşitlendi: `TC_MIN=250` (küçük çekirdek
ödeme iner, doku WT'de kalır) ve `review_flags()` (kontrast tutmayan tümörde çekirdek
iddiası gerekçesi ve sayılarıyla işaretlenir). `evaluate_uwcse.py` ve
`nnunet_predictor.py` veri kökünü, fold listesini ve bölme büyüklüğünü ortamdan alır
(`MERGEN_DATA_ROOT`, `UCSF_DIR`, `UCSF_METADATA`, `SWIN_PATH`, `UWCSE_RESULTS`,
`N_VAL`, `N_TEST=0` = kalan hepsi, `NNUNET_FOLDS`); depodaki kanal adı çözümü
korundu. `refit_uwcse_weights.py` ve `sweep_uwcse_sampling.py` ürün katsayılarının
nasıl seçildiğini yeniden üretir. Patoloji hattı `models/pathology/` altındadır;
`infer_slide.py` canlı çıkarım sözleşmesidir, executor'a bağlanması M6'dadır.
Kural testleri (`test_uwcse_rules.py`, 12 test) CI'da torch'suz koşar. Bugünkü 22
demo vakası eski kuralla üretilmiştir; yeniden üretim olasılık önbelleğini ister
ve M5'te hostta yapılır.

### M3 güncel durum

`frontend/scripts/prepare_demo_v4.py` paket v4'ü üretir: kök katalog şeması 3'te
kalır, `pathology/glioma` koleksiyonu eklenir ve görüntü manifesti 4'e yükselip
`examples` dizisini taşır. 17 Eylül arşiviyle ölçülen çıktı 246 MB: 12 slayt
vakası (7 doğru, 5 yanlış — hepsi etiketli; 3'ü top-2 farkı 0,45'in altında
olduğu için uzman incelemesi bayrağıyla; 8 merkez), 5 MRI figürü ve 22
kopyalanmış görüntü vakası. Kaynak paketteki `genomics` koleksiyonu kopyalanmaz.

Kararı ürün yapılandırması verir: `--slide-predictions` ile 5-fold topluluğun
olasılıkları okunur, tek ağın kararı `singleModel` olarak kaydın içinde kalır.
Çekimserlik eşiği `--calibration` ile kayıt defterinden gelir (betikte sabit
yok), böylece slayttaki bayrak ile doğrulama ekranındaki eşik ayrışamaz. Isı
haritası her zaman tek ağdan (`mil_v1`) gelir; manifest haritayı çizen ağı ayrı
adlandırır ve kayıt haritanın hangi ölçekte çizildiğini (`raw_weight` ya da
`within_slide_percentile`) bildirir. Bugünkü arşiv ham ağırlık renderi taşıyor;
rapordaki figürlerin slayt içi yüzdelik ölçeği hostta yeniden üretilecek.

Store her manifesti yüklerken iddiaları yeniden türetir: `needsExpertReview`
bildirilen `reviewMargin` ile, `agreesWithReference` referansla, her varlık yolu
vakanın kendi kanonik yoluyla doğrulanır; referans hacmi olmadan `dice`/`hd95Mm`
yazılamaz ve hiçbir vaka başka bir vakanın varlığına işaret edemez. Üretici de
arşivin sınıf/doğruluk iddialarını ve klasör-hasta eşleşmesini yeniden hesaplar.
MRI figürleri gezilebilir vaka listesine girmez; kendi `ruleVersion`'ıyla ayrı
uçtan okunur, çünkü bugünkü 22 demo vakası eski kuralla, figürler UWCSE v3 ile
üretilmiştir. Arayüz tarafı (modül seçici, patoloji ekranı, `review_flags`
bandı) M4'tedir; `review_flags` arşivdeki beş figürde de boş geldiği için bant
bugün pozitif örneksizdir.

## Git ve ekip çalışma düzeni

- Bir sprint dalı bir sorumluluk alanını değiştirir. Aynı dosyaları değiştirecek iki
  kişi aynı anda farklı dallarda çalışmaz; önce sözleşme PR'ı birleştirilir.
- Sprintte genellikle 2–4 anlamlı commit yeterlidir: sözleşme/test, uygulama,
  entegrasyon/belge. Çalışır ara noktada commit yapılır; commit sayısı hedef değildir.
- Claude veya Codex'e görev verirken sprint satırı, izin verilen dizinler ve kabul
  komutları birlikte verilir. Görev sahibi kendi dalında çalışır; diğer ajan o dalı
  review eder.
- Merge öncesi: ilgili testler, secret/IP taraması, büyük dosya kontrolü, diff review
  ve gerekiyorsa gerçek GPU/VPS smoke testi. Sonra squash yerine anlamlı commitler
  korunarak PR merge edilir; bağımlı dal güncel `main` üzerinden açılır.
