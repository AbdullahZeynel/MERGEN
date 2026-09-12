# Geliştirme kuralları

Codex, Claude ve insan katkıcılar için ortak kaynak bu dosyadır.

1. **Önce oku:** README, `docs/PLAN.md` ve değiştireceğin kodu incele. Başka projedeki kuralları buraya kendiliğinden uygulama.
2. **Kaynakla doğrula:** Teknik iddiaya `dosya:satır` veya komut çıktısı göster. Doğrulanmayanı açıkça belirt. Proje klasöründe bulunmayan ağırlık için yapılandırılmış model cache'ini de kontrol et.
3. **Dar kapsam:** Yaklaşımı kısaca açıkla; yalnızca istenen işi yap. İlgisiz refactor, toplu biçimlendirme ve bağımlılık değişikliği ekleme.
4. **Sınırları koru:** Arayüz → backend → model servisleri. Model çalıştırma ve anahtarlar tarayıcıya taşınmaz. MCP ortak backend işlevlerini kullanır.
5. **Modelleri koru:** Açık talep olmadan yeniden eğitim, ağırlık/fold, eşik veya ön işleme değişikliği yapma. Eğitim/değerlendirme ile canlı çıkarımı ayrı tut.
6. **Sonuç uydurma:** Demo ve canlı sonucu etiketle. Eksik veri yerine sessizce sahte modalite, rastgele skor veya başarılı sonuç üretme. Farklı hastaları eşleştirme; referans etiketi olmadan Dice gösterme.
7. **Git temizliği:** Ağırlık, veri seti, sanal ortam, çıktı ve sırları commit etme. Dosyaları bilinçli seç; iç içe `.git` ve büyük dosyaları kontrol et. Üçüncü taraf lisanslarını koru.
8. **Doğrula:** Değişikliğe uygun kontrolleri çalıştır. Sözdizimi kontrolünü model/arayüz çalıştı diye sunma. Yapılmayan testi ve engelini yaz.
9. **Kayıt bırak:** Davranış veya kurulum değiştiğinde ilgili kısa belgeyi güncelle. Gelecek işler için ayrı dal/PR kullan; commit başlığı `feat:`, `fix:`, `docs:` veya `chore:` ile başlasın.
10. **Yetki ve belirsizlik:** Mevcut kullanıcı talebi kapsamındaki geri alınabilir işleri tamamla. Veri silme, geçmişi yeniden yazma veya izinsiz yayınlama yapma. Kritik belirsizlikte somut soruyu sor; aynı hatayı körlemesine tekrarlama.

## Sırlar ve örnek yapılandırmalar

- Gerçek VPS/ev/Tailscale IP'si, özel hostname, kullanıcı/parola, token, SSH anahtarı ve bağlantı sırrı kodda, belgede, testte veya logda yer almaz; yerel yapılandırmada tutulur.
- `.env.example`, `*.env.example` ve diğer örneklerde yalnızca boş değer veya açık yer tutucu kullan. `example.com`, `<VPS_HOST>` gibi örnekler uygundur; gerçek altyapı adresi veya çalışır credential kopyalama. `localhost`, `127.0.0.1`, `0.0.0.0` yerel/dinleme ayarı olarak kullanılabilir.
- `.env` otomatik yüklenmez: servis okuyucusunu açıkça yapılandır; gerekli sır eksikse anlaşılır hatayla dur, koda gömülü yedek sır kullanma. Tarayıcıya çıkan değişkenlere sır koyma.
- Commit/push öncesi seçilmiş diff'i credential ve altyapı adresleri açısından kontrol et; eşleşen sırrı çıktıya yazma. `.gitignore` içerik taramaz ve daha önce takip edilen dosyayı korumaz. Sır yayımlandıysa önce iptal/yenileme gerekir; dosyayı sonraki committe silmek geçmişten kaldırmaz.
- Bu kontrolün otomatik kısmı `python infra/ci/repo_guard.py`: takip edilen dosyalarda sır, gerçek IP/`.ts.net` adresi, ağırlık/veri uzantısı ve 1 MiB üstü dosya arar ve CI'da her değişiklikte çalışır. Bulguları değer yazdırmadan raporlar; gerçekten zararsız bir satırı `# repo-guard: allow` yorumuyla geçebilirsiniz. Betik elle incelemenin yerini tutmaz.
