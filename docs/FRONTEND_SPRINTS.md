# Frontend sprintleri

Görsel yön: Cansağlığı sitesinden esinlenen lacivert/kırmızı vurgu, beyaz çalışma yüzeyi, koyu MR görüntüleme alanı. Öncelik vaka içinde rahat gezinme. Referans: https://cansagligivakfi.org/en/

| Sprint | Branch | Kabul çıktısı |
|---|---|---|
| F1 | `feat/frontend-foundation` | Vaka kabuğu, doğrulanan demo paketi, gerçek merkez kesitler, arama/filtre, hata/boş durum, genomik ve asistan alanı; build/deploy iskeleti |
| F2 | `feat/frontend-imaging-workspace` | 2D gezinme, gerçek katmanlar, etkileşimli Three.js mesh, istek iptali ve kaynak temizliği |
| F3 | `feat/frontend-analysis-panels` | Doğrulanmış genomik sonuç sözleşmesi, mevcutsa SHAP, sohbet mesaj görünümü |
| F4 | `feat/frontend-api-integration` | Backend sağlık/kuyruk/sonuç entegrasyonu, 10 oturum provası, VPS ve bağlantı kesintisi testi |

F1 bağımlılığı: `chore/security-guardrails` yerel commitini içerir. `main` değişmedi. Sprint içinde anlamlı yerel commitler oluşturulur; push sprint sonunda kullanıcıyla birlikte yapılır. Yeni sprint dalı, önceki sprint birleşince güncel main'den açılır.

F2 demo API bütün FLAIR kesitlerini ve ensemble mesh'lerini sağlar; kesitlere segmentasyon overlay'i henüz eklenmedi. Diğer modaliteler ve ayrı maskeler veri adaptörü desteği olmadan etkinleştirilmez. Doğrulanmış affine/spacing olmadan ölçüm veya 2D–3D eşzamanlama yapılmaz. GT/Dice yalnızca referans etiketi mevcut değerlendirme verisiyle gösterilir.

Bağımsız görüntü ve varyant kayıtları aynı hastanın sonucu gibi birleştirilmez. Chatbot/SHAP/canlı sağlık durumu mevcut veri olmadan taklit edilmez.

## F2 güncel durum

Tüm 2D kesitlere kaydırıcı/düğme/klavye erişimi, eksen hafızası ve yaklaşık MR dış yüzeyi tamamlandı. Demo API→MCP entegrasyonu F4'ten öne alındı; veri ve MCP VPS'te olacak. 11 frontend, 5 API/store ve 5 deploy testi geçti. Yerel gerçek MCP üzerinden iki mesh ve 18 kesit, SHA-256 bütünlüğü ve 10 eşzamanlı HTTP isteği kontrol edildi. Bu 10 kullanıcı kapasite testi değildir. VPS servis kurulum betiği/systemd/Caddy örnekleri hazır; gerçek VPS kurulumu ve TLS provası henüz yapılmadı.

### Önceki aşama kayıtları

Son ek doğrulama: gerçek yerel Caddy → API → MCP üzerinden sağlık/vaka/PNG akışı çalıştı; eski statik demo yolu ve dış MCP yolu 404 döndü. Tarayıcıda koronal kesit gezintisi ve iki büyütülmüş görünüm incelendi.

F2 ilk adımı: gerçek ensemble 3D görüntüleyici, bölge/opaklık kontrolleri, 2D/3D geniş modal pencereleri ve daha büyük asistan paneli eklendi. 10 test ve build geçti; 3D mesh ile iki büyütme penceresi gerçek tarayıcıda görüldü. Serbest 2D gezinme henüz tamamlanmadı. Dal, F1 henüz birleşmediğinden F1'in üzerine açıldı; push yapılmadı.

Tamamlandı: 8 frontend testi, TypeScript kontrolü ve üretim build'i; 5 deploy testi; Caddy şablon doğrulaması. Yerel Caddy altında demo dışlayan ve demo dahil paket kurulumları, 6 PNG, SPA yolu, eksik dosya 404 ve API 503 davranışları ve rollback doğrulandı. Tarayıcıda gerçek vaka/sohbet bağlamı değişimi ve 390px mobil görünüm incelendi. Canlı VPS/TLS, GPU çıkarımı, 10 oturum yük testi ve GitHub Actions koşusu yapılmadı; push henüz yapılmadı.
