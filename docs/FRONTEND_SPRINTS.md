# Frontend sprintleri

Görsel yön: Cansağlığı sitesinden esinlenen lacivert/kırmızı vurgu, beyaz çalışma yüzeyi, koyu MR görüntüleme alanı. Öncelik vaka içinde rahat gezinme. Referans: https://cansagligivakfi.org/en/

| Sprint | Branch | Kabul çıktısı |
|---|---|---|
| F1 | `feat/frontend-foundation` | Vaka kabuğu, doğrulanan demo paketi, gerçek merkez kesitler, arama/filtre, hata/boş durum, genomik ve asistan alanı; build/deploy iskeleti |
| F2 | `feat/frontend-imaging-workspace` | 2D gezinme, gerçek katmanlar, etkileşimli Three.js mesh, istek iptali ve kaynak temizliği |
| F3 | `feat/frontend-analysis-panels` | Doğrulanmış genomik sonuç sözleşmesi, mevcutsa SHAP, sohbet mesaj görünümü |
| F4 | `feat/frontend-api-integration` | Backend sağlık/kuyruk/sonuç entegrasyonu, 10 oturum provası, VPS ve bağlantı kesintisi testi |

F1 bağımlılığı: `chore/security-guardrails` yerel commitini içerir. `main` değişmedi. Sprint içinde anlamlı yerel commitler oluşturulur; push sprint sonunda kullanıcıyla birlikte yapılır. Yeni sprint dalı, önceki sprint birleşince güncel main'den açılır.

Hazır merkez kesit, tamamlanmış görüntüleyici değildir. F2'de mevcut demo API yalnızca FLAIR ve görüntüye gömülü segmentasyon PNG'si sağlar; diğer modaliteler ve ayrı maskeler veri adaptörü desteği olmadan etkinleştirilmez. Doğrulanmış affine/spacing olmadan ölçüm veya 2D–3D eşzamanlama yapılmaz. GT/Dice yalnızca referans etiketi mevcut değerlendirme verisiyle gösterilir.

Bağımsız görüntü ve varyant kayıtları aynı hastanın sonucu gibi birleştirilmez. Chatbot/SHAP/canlı sağlık durumu mevcut veri olmadan taklit edilmez.

## F1 doğrulama kaydı

F2 ilk adımı: gerçek ensemble 3D görüntüleyici, bölge/opaklık kontrolleri, 2D/3D geniş modal pencereleri ve daha büyük asistan paneli eklendi. 10 test ve build geçti; 3D mesh ile iki büyütme penceresi gerçek tarayıcıda görüldü. Serbest 2D gezinme henüz tamamlanmadı. Dal, F1 henüz birleşmediğinden F1'in üzerine açıldı; push yapılmadı.

Tamamlandı: 8 frontend testi, TypeScript kontrolü ve üretim build'i; 5 deploy testi; Caddy şablon doğrulaması. Yerel Caddy altında demo dışlayan ve demo dahil paket kurulumları, 6 PNG, SPA yolu, eksik dosya 404 ve API 503 davranışları ve rollback doğrulandı. Tarayıcıda gerçek vaka/sohbet bağlamı değişimi ve 390px mobil görünüm incelendi. Canlı VPS/TLS, GPU çıkarımı, 10 oturum yük testi ve GitHub Actions koşusu yapılmadı; push henüz yapılmadı.
