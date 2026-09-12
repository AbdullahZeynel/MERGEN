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
              │                    ▲
              │ Tailscale          │ sonuç yükleme
              ▼                    │
       GPU worker (primary / standby)

VPS API ──► salt okunur demo MCP ──► hazırlanmış demo paketleri
```

- MCP yalnızca yayımlanabilir, önceden hazırlanmış demo dosyalarını okur. Yükleme,
  oturum, kuyruk ve model çalıştırma API/worker katmanındadır. GPU makinesinde MCP
  gerekli değildir; ileride LLM araç çağrıları için ayrıca değerlendirilebilir.
- GPU worker işi VPS kuyruğundan **pull** eder. Böylece ev ağında model portu
  açılmaz, birincil veya yedek worker aynı işi atomik olarak sahiplenebilir.
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
- GPU worker girdiyi işe özel geçici dizine indirir, sonucu VPS'ye yükledikten sonra
  kendi kopyasını `finally` temizliğiyle kaldırır. Başlangıçta kalmış dizinleri
  süpüren ayrı bir temizlik görevi bulunur.
- VPS temizleyicisi her dakika sona eren oturumları, ilişkili dosyaları ve iş
  satırlarını kaldırır. Uygulama logları dosya adı, payload, genomik değişken veya
  oturum kimliğinin tamamını içermez; yalnızca toplu süre/hata kodu tutulur.
- SSD'de dosya silmek fiziksel blokların anında geri döndürülemez silindiğini garanti
  etmez. Disk/VM image şifrelemesi, kısa saklama süresi ve yedeklere runtime dizinini
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
| S4 — `feat/gpu-worker-runtime` | Ubuntu Server VM kurulumu, NVIDIA/CUDA doğrulaması, görüntü ve genomik için ayrı venv/container; pull-worker, lease, health/capabilities | Worker gerçek checkpoint/modeli yükler; tek fixture uçtan uca tamamlanır; yeniden başlatmada yarım iş temizlenir; primary/standby aynı işi çift çalıştırmaz |
| S5 — `feat/live-session-api` | VPS oturum cookie'si, yükleme doğrulaması, SQLite kuyruk, 3 dk idle timeout, logout/cleanup, 5–10 aktif oturum sınırı | Çıkışta ve timeout'ta VPS+GPU dosyaları/DB satırları silinir; 11. oturum 429 alır; dosya boyutu/türü ve sahiplik testleri geçer |
| S6 — `feat/live-ui-downloads` | Arayüzde modül seçimi, modüle özel vaka listesi/yükleme, iş ilerlemesi, canlı sonuç ve ZIP indirme | Modül değişiminde eski vaka temizlenir; kullanıcı yalnız kendi işini görür/indirir; bağlantı kopunca demo sonucuymuş gibi gösterilmez |
| S7 — `chore/resilience-privacy-drill` | Yedek worker, Tailscale ACL, servis boot, disk sınırı, log denetimi, veri yaşam döngüsü ve sunum provası | GPU kapalıyken demo çalışır; standby elle devreye alınır; 10 oturum/1 ağır iş provası ve temizlik kanıtı kaydedilir |

S0 önce tamamlanır. S1 ile S3, sözleşmeler birleştikten sonra paralel yürüyebilir.
S2, S1 katalog biçimine; S4, S3 inference adaptörüne bağlıdır. S5 ve S4 birleşmeden
S6 başlanmaz. S7 bütün zincirin yayın kapısıdır.

### Güncel dal durumu

`feat/vps-control-plane` dalında S0 sözleşmeleri ile S5'in VPS temeli birlikte
hazırlanmıştır: erişim kodlu ve CSRF korumalı oturum, 10 aktif oturum sınırı, ZIP
doğrulama, SQLite iş/lease kuyruğu, tek eşzamanlı claim, Tailscale'e bağlı worker
API'si, sonuç/varlık indirme ve 3 dakika temizlik timer'ı. Gerçek VPS kurulumu ve
GPU worker ile uçtan uca prova yapılmadan S5 tamamlanmış sayılmaz.

## Genomik model için mevcut durum ve çıkış koşulu

Yerel çalışma klasöründe, Git dışında tutulan `mergen_xgb.joblib`,
`mergen_xgb.json` ve bir özellik matrisi vardır;
ESM-2 `facebook/esm2_t30_150M_UR50D` adıyla çalışma anında Transformers üzerinden
yüklenir. Mevcut `main.py` veri indirme, özellik çıkarımı, eğitim, değerlendirme ve
raporu tek çalıştırmada yapar; canlı tahmin komutu değildir.

S3 başlamadan şu denetim kayda geçirilir:

1. XGBoost dosyasının açılması, beklenen özellik adları/sırası ve kütüphane sürümü.
2. ESM-2 tokenizer/ağırlıklarının GPU VM'de çevrimdışı yüklenebilmesi ve checksum'u.
3. Eğitim matrisindeki ESM kolonlarının gerçekten ESM açıkken üretildiğinin kanıtı.
4. Bir varyant için gerekli minimum giriş: gen, protein değişimi, kanonik protein
   dizisi/erişim kimliği ve modelin beklediği diğer özelliklerin kaynağı.
5. Sentetik `X` dizisi ve sentetik COSMIC frekansı yollarının canlı adaptörde yasaklanması.
6. Sabit test fixture'ı, beklenen olasılık ve SHAP değerlerinin toleransla kaydı.

Bu altı madde geçmeden arayüzde genom modeli “çalışıyor” olarak gösterilmez.

Denetimin ölçülmüş sonucu, ne çalıştırıldığı ve özelliklerle ilgili üç bulgu
[`GENOMICS_AUDIT.md`](GENOMICS_AUDIT.md) belgesindedir.

### S3 güncel durum

`feat/genomics-inference-service` dalında tek-varyant çıkarım adaptörü
(`models/VeriOdakliCozum/cikarim.py`), sürümlenmiş özellik şeması
(`semalar/ozellik_semasi.v1.json`, 15 özellik + karar eşiği + sağlama
toplamları) ve üretici betik (`semayi_uret.py`) hazırlandı. Adaptör eğitim
modüllerini import etmez; sentetik `X` kontekst, eksik dizilim, vahşi tip
uyuşmazlığı, ESM'in sessiz sıfırı ve eksik CGGA tablosu açık hata verir.
16 test geçti; AAindex/CGGA/pozisyon özellikleri eğitim matrisine karşı
yeniden üretildi. Denetimin 1., 2. ve 6. maddeleri (xgboost ile özellik adı
doğrulaması, ESM çevrimdışı yükleme, olasılık/SHAP fixture'ı) gerçek ortam
gerektirdiği için açık; SHAP çıktısı ve genomik demo vakaları da S3'ün kalan
işidir.

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
