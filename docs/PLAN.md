# Mimari ve çalışma sırası

## Hedef yapı

`Tarayıcı → Cloudflare → VPS/Caddy → backend → Tailscale → Ubuntu/model servisleri`

- **VPS:** arayüz, oturumlar, iş kuyruğu, hazır demo ve tamamlanan sonuçlar. Başlangıç tasarımı: SQLite iş kayıtları, 10 aktif oturum, kullanıcı başına 1 iş, aynı anda 1 ağır analiz. Değerler ölçümle değiştirilecek.
- **Ubuntu:** görüntü modeli; kilitli bağımlılık ortamı ve işe özel çıktı dizinleri.
- **MCP:** hazır demo araçları VPS'te uygulanmıştır. API demo dosyalarını MCP üzerinden okur; MCP kuyruk veya backend yerine geçmez. Sohbet LLM'si ayrı gelecek işidir.
- **Demo:** Ubuntu kapalıyken gösterim devam etmeli; canlı hata sessizce demo sonucuna dönüşmemeli. İnternetsiz sunum için yerel bağımlılıklar hazırlanmalı.

## İş sırası

1. **Kaynak düzeni (bu adım):** bileşenleri ayır, Git dışı dosyaları tanımla, kuralları ve README'yi oluştur.
2. **Ortam doğrulama:** tam dört-modaliteli örnek MR, doğru checkpoint ve Python/CUDA sürümlerini gerçek makinede kontrol et. Mevcut v5 değerlendirme yolları yerel veriyle uyuşmuyor; veri sürümü doğrulanmadan ad değiştirme.
3. **Ortak veri sözleşmesi:** vaka/iş kimliği, `demo|live`, model sürümü, durum, dosya referansları ve uzamsal metadata. Eksik girdiler açık hata olmalı.
4. **Demo arayüzü:** hazır vakalar ve 2D/3D görüntüleme; CDN bağımlılıklarını yerelleştir. Eğitim örneği ile bağımsız test metriklerini ayır.
5. **Canlı adaptörler:** eğitim ve değerlendirmeyi tetiklemeden tek-vaka çıkarımı; referans etiketini zorunlu kılma. Sonra VPS kuyruğu ve Tailscale bağlantısı.
6. **Sunum provası:** 10 oturum, tek analiz, tekrar istek, bağlantı kesintisi, servis yeniden başlama ve dosya bütünlüğü. Gerçek süre/bellek ölçümlerini kaydet.
7. **MCP/chatbot:** görüntü hattı kararlı çalıştıktan sonra ortak servislere bağla.

Canlı oturum, GPU worker, modül/hastalık bazlı demo kataloğu, tahmin/referans
katmanları ve indirme formatlarının ayrıntılı uygulama sırası
[`SYSTEM_SPRINTS.md`](SYSTEM_SPRINTS.md) belgesindedir.

## Kapsam sınırı

Bu aşama model eğitimi, klinik füzyon doğrulaması veya hastane/PACS entegrasyonu
değildir. Arayüz, salt okunur demo API'si, MCP ve canlı oturum/kuyruk temeli
çalışır; izole Swin UNETR runner'ı sentetik fixture ile gerçek GPU'da uçtan uca
çalıştı (41 s, tepe 5794 MiB), VPS kuyruğuyla uçtan uca kabul yapılmamıştır.
Runner M5'te ürün yapılandırmasını (`mergen-uwcse` / `v3`: beş nnU-Net foldu +
Swin, UWCSE v3 kuralı) tarif eder; sözleşme, orkestrasyon ve kural eşitliği
testlerle kapalıdır ama **nnU-Net üyesi gerçek ağırlıklarla hiç çalıştırılmadı**,
yani canlı ürün çıktısı ölçülmemiştir (#48). Diğer donanım ve hız bilgileri
ölçülmedikçe varsayımdır.
Güncel demo kurulumu: `docs/DEMO_SERVICES.md`.

## Model yerleşimi

Görüntü bileşenleri `models/imaging/`, patoloji bileşenleri `models/pathology/`
altındadır; her bileşenin kökeni, lisansı ve ölçümleri `models/registry/` kayıt
defterindedir. Veri ve ağırlıklar Git dışıdır. Canlı adaptör oluşturulurken `data`, `weights` ve `artifacts` yolları
açık yapılandırma ile tanımlanacaktır. Kapsam dışı eski bileşenler kaldırılmıştır.
