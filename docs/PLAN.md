# Mimari ve çalışma sırası

## Hedef yapı

`Tarayıcı → Cloudflare → VPS/Caddy → backend → Tailscale → Ubuntu/model servisleri`

- **VPS:** arayüz, oturumlar, iş kuyruğu, hazır demo ve tamamlanan sonuçlar. Başlangıç tasarımı: SQLite iş kayıtları, 10 aktif oturum, kullanıcı başına 1 iş, aynı anda 1 ağır analiz. Değerler ölçümle değiştirilecek.
- **Ubuntu:** mevcut görüntü ve genomik modeller; ayrı bağımlılık ortamları ve işe özel çıktı dizinleri.
- **MCP:** ileride backend işlevlerine araç erişimi; kuyruk veya backend yerine geçmez. Sohbet LLM'si ayrı gelecek işidir.
- **Demo:** Ubuntu kapalıyken gösterim devam etmeli; canlı hata sessizce demo sonucuna dönüşmemeli. İnternetsiz sunum için yerel bağımlılıklar hazırlanmalı.

## İş sırası

1. **Kaynak düzeni (bu adım):** bileşenleri ayır, Git dışı dosyaları tanımla, kuralları ve README'yi oluştur.
2. **Ortam doğrulama:** tam dört-modaliteli örnek MR, doğru checkpoint, ESM cache ve Python/CUDA sürümlerini gerçek makinede kontrol et. Mevcut v5 değerlendirme yolları yerel veriyle uyuşmuyor; veri sürümü doğrulanmadan ad değiştirme.
3. **Ortak veri sözleşmesi:** vaka/iş kimliği, `demo|live`, model sürümü, durum, dosya referansları ve uzamsal metadata. Eksik girdiler açık hata olmalı.
4. **Demo arayüzü:** hazır vakalar, 2D/3D, genomik sonuç görünümü; CDN bağımlılıklarını yerelleştir. Eğitim örneği ile bağımsız test metriklerini ayır.
5. **Canlı adaptörler:** eğitim ve değerlendirmeyi tetiklemeden tek-vaka çıkarımı; referans etiketini zorunlu kılma. Sonra VPS kuyruğu ve Tailscale bağlantısı.
6. **Sunum provası:** 10 oturum, tek analiz, tekrar istek, bağlantı kesintisi, servis yeniden başlama ve dosya bütünlüğü. Gerçek süre/bellek ölçümlerini kaydet.
7. **MCP/chatbot:** ilk iki analiz modülü kararlı çalıştıktan sonra ortak servislere bağla.

## Kapsam sınırı

Bu aşama model eğitimi, klinik füzyon doğrulaması veya hastane/PACS entegrasyonu değildir. Yeni arayüz, API ve MCP klasörleri planlanan bileşenlerdir; çalışır servis olarak sunulmaz. Donanım ve hız bilgileri ölçülmedikçe varsayımdır.

## Taşıma kararı

Model bileşenleri `models/` altında toplandı. Veri ve ağırlıkların mevcut bileşen-içi yolları korundu; hepsi Git dışıdır. Böylece algoritmaları ve üçüncü taraf yapılandırmalarını yalnızca klasör estetiği için değiştirmiyoruz. Canlı adaptörler oluşturulurken ortak `data/`, `weights/`, `artifacts/` yolları açık yapılandırma ile tanımlanabilir.

`VeriOdakliCozum` adı mevcut Python importlarını korur. Dashboard HTML'i `frontend/legacy/`, sunucusu `backend/legacy/` altındadır. Eski araştırma notları güncel plan yerine kullanılmaz. Taşımadan önceki README, ignore ve değiştirilen kaynaklar `.local/reorganization-2026-09-12/` altında saklanır.
