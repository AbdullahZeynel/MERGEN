# Canlı sistem ve model entegrasyonu sprintleri

Bu belge; mevcut VPS demosunu bozmadan görüntü ve genomik modelleri canlı sisteme
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
                  ├── görüntü adaptörü + venv
                  └── genomik adaptörü + venv

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
- “Görüntü” ve “Genomik” ayrı çalışma alanlarıdır. Modül değişince vaka listesi,
  seçili vaka ve sonuç durumu sıfırlanır; bağımsız örnekler aynı hastaya aitmiş gibi
  birleştirilmez.

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
  genomics/
    glioma-variant-pathogenicity/
      manifest.json
      cases/<genomic-case-id>/
        input.json
        result.json
        explanation.json
```

Katalog kaydı en az şu alanları taşır: `schemaVersion`, `module`, `disease`,
`caseId`, `mode`, `modelId`, `modelVersion`, `inputKind`, `hasPrediction`,
`hasGroundTruth` ve varlık referansları. Kimlikler modül içinde benzersizdir;
görüntü ve genomik vaka kimlikleri eşleşme anlamına gelmez.

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
  satırlarını kaldırır. Uygulama logları dosya adı, payload, genomik değişken veya
  oturum kimliğinin tamamını içermez; yalnızca toplu süre/hata kodu tutulur.
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

Genomik iş için ZIP; girdi özeti, olasılık/sınıf, kullanılan özellikler, model sürümü
ve mevcutsa SHAP açıklamasını JSON/PDF olarak taşır. Sentetik protein dizisi veya
sentetik COSMIC değeriyle başarılı canlı sonuç üretilmez.

## Sprint sırası

| Sprint / dal | Kapsam | Kabul ölçütü |
|---|---|---|
| S0 — `docs/live-system-contracts` | Bu kararları API şemalarına çevir; demo-v3 katalog, vaka, iş, sonuç ve hata sözleşmelerini örnek JSON'larla tanımla | Görüntü/genomik örnekleri ayrıdır; demo/canlı ve prediction/ground-truth alanları sözleşme testlerinden geçer |
| S1 — `feat/demo-catalog-v3` | Demo dosyalarını modül ve hastalık bazında üret; MCP'ye filtreli katalog/asset araçları ekle; mevcut iki glioma demosunu taşı | v2 geri dönüş veya kontrollü tek seferlik geçiş çalışır; bilinmeyen modül/hastalık/vaka reddedilir; mevcut site kesintisiz açılır |
| S2 — `feat/imaging-overlays-export` | Prediction ve ground-truth 2D overlay üretimi, ayrı 3D katmanlar, NIfTI+GLB export; frontend katman düğmeleri | Demo vakada iki katman bağımsız açılır; canlı sözleşme fixture'ında GT görünmez; eksen/indeks/affine tutarlılık testi geçer |
| S3 — `feat/genomics-inference-service` | Mevcut genomik pipeline'ı denetle; eğitim kodundan tek-varyant inference adaptörünü ayır; model/feature şemasını sürümle; genomik demo vakaları oluştur | Sabit fixture aynı sonucu verir; model ve kolon sırası doğrulanır; eksik dizi/özellik açık hata verir; eğitim tetiklenmez |
| G0 — `docs/native-gpu-host-audit` | Paylaşımlı host envanteri, dosya sistemi/şifreleme, mevcut NVIDIA kullanımı, snapshot/rollback ve runtime'ın yedek dışı bırakılması | Kurulum öncesi geri dönüş noktası ve geri yükleme adımı doğrulanır; hasta verisi/sırlar snapshot kapsamına girmez |
| G1 — `chore/native-gpu-host-bootstrap` | `mergen` bakım hesabı, ayrı yetkisiz servis hesapları, dizin/izin standardı, Tailscale ACL, sürücü ve CUDA'lı PyTorch doğrulaması | Servisler sudo/login olmadan çalışır; sırlar ayrılır; yeniden başlatma sonrası Tailscale ve GPU smoke testi geçer |
| G2 — `feat/gpu-dispatcher` | Eski pull-worker çekirdeğini dispatcher'a uyarla; claim, lease, checksum, indirme, sonuç yükleme, yeniden deneme ve temizlik | Sahte executor ile uçtan uca iş tamamlanır; ağ kesintisi/yeniden başlatmada iş kaybolmaz veya iki kez yayımlanmaz |
| G3 — `feat/gpu-executor` | Yerel iş sözleşmesi, manifest doğrulama, adaptör registry, `flock`, GPU boşluk eşiği, pause/resume ve systemd sınırları | Meşgul GPU'da iş ertelenir ve kullanıcı süreci öldürülmez; tek inference sınırı ile sahte adaptör testi geçer |
| G4 — `feat/gpu-model-adapters` | Görüntü ve genomik için ayrı venv, sürümlü model dizini, gerçek adaptörler ve başlangıç preflight'ı | Bir görüntü ve bir genom fixture'ı gerçek modelle çalışır; eksik ağırlık/şema capability olarak ilan edilmez |
| G5 — `feat/live-end-to-end` | Mevcut VPS oturum/kuyruk katmanını dispatcher'a bağla; canlı UI, ilerleme, sonuç varlıkları ve ZIP indirme | Kullanıcı yalnız kendi işini görür/indirir; 3 dk idle/logout GPU+VPS kopyalarını siler; bağlantı kopması demo sonucu gibi görünmez |
| G6 — `chore/resilience-privacy-drill` | Yedek host, servis boot, disk sınırı, log denetimi, veri yaşam döngüsü ve sunum provası | GPU kapalıyken demo çalışır; yedek elle devreye alınır; 10 oturum/1 GPU işi ve temizlik kanıtı kaydedilir |

S0–S3 demo ve sözleşme temeli `main` üzerinde bulunur. Yeni canlı yol G0 ile başlar;
G1, G0'ın geri dönüş ve veri kapsamı kararı olmadan uygulanmaz. G2 ile G3 yerel iş
sözleşmesi birleştikten sonra paralel ilerleyebilir. G4 ikisine, G5 gerçek G4
çıktısına bağlıdır. G6 bütün zincirin yayın kapısıdır. Frontend chunk ayrıştırması
ve demo mesh optimizasyonu bu zincirden bağımsız kısa performans sprintleridir.

### S1 güncel durum

`main`, kök katalog ile `module/disease/cases` ayrımını, filtreli MCP/API uçlarını,
22 görüntü vakasını ve dört genomik demo vakasını içerir.
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

## Genomik model için mevcut durum ve çıkış koşulu

Yerel çalışma klasöründe, Git dışında tutulan `mergen_xgb.joblib`,
`mergen_xgb.json` ve bir özellik matrisi vardır;
ESM-2 `facebook/esm2_t30_150M_UR50D` adıyla çalışma anında Transformers üzerinden
yüklenir. Mevcut `main.py` veri indirme, özellik çıkarımı, eğitim, değerlendirme ve
raporu tek çalıştırmada yapar; canlı tahmin komutu değildir.

S3 başlamadan şu denetim kayda geçirilir:

1. XGBoost dosyasının açılması, beklenen özellik adları/sırası ve kütüphane sürümü.
2. ESM-2 tokenizer/ağırlıklarının GPU hostunda çevrimdışı yüklenebilmesi ve checksum'u.
3. Eğitim matrisindeki ESM kolonlarının gerçekten ESM açıkken üretildiğinin kanıtı.
4. Bir varyant için gerekli minimum giriş: gen, protein değişimi, kanonik protein
   dizisi/erişim kimliği ve modelin beklediği diğer özelliklerin kaynağı.
5. Sentetik `X` dizisi ve sentetik COSMIC frekansı yollarının canlı adaptörde yasaklanması.
6. Sabit test fixture'ı, beklenen olasılık ve SHAP değerlerinin toleransla kaydı.

Bu altı madde geçmeden arayüzde genom modeli “çalışıyor” olarak gösterilmez.

Denetimin ölçülmüş sonucu, ne çalıştırıldığı ve özelliklerle ilgili üç bulgu
[`GENOMICS_AUDIT.md`](GENOMICS_AUDIT.md) belgesindedir.

### S3 güncel durum

Tek-varyant çıkarım adaptörü
(`models/VeriOdakliCozum/cikarim.py`), sürümlenmiş özellik şeması
(`semalar/ozellik_semasi.v1.json`, 15 özellik + karar eşiği + sağlama
toplamları) ve üretici betik (`semayi_uret.py`) hazırlandı. Adaptör eğitim
modüllerini import etmez; sentetik `X` kontekst, eksik dizilim, vahşi tip
uyuşmazlığı, ESM'in sessiz sıfırı ve eksik CGGA tablosu açık hata verir.
Runtime doğrulaması, SHAP çıktısı ve genomik demo vakaları `main` üzerinde yer
alır. `TP53 p.P72R` bulgusu gerçek model çıktısı olarak korunur; bunun gen düzeyi
kestirme öğrenme ve kalibrasyon denetimi tamamlanmadan canlı genom yeteneği hazır
ilan edilmez. Bu bilimsel yayın kapısı issue #15 altında izlenir.

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
