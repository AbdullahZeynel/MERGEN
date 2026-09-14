# 3D mesh performans kaydı

Bu kayıt hazır demo mesh biçiminin JSON'dan GLB'ye geçişini ölçer. Model çıktısı,
vertex, yüz ve koordinatlar değiştirilmedi; sadeleştirme uygulanmadı. Böylece görsel
geometri aynı kalırken sayıların metin olarak ayrıştırılması kaldırıldı.

## Boyut

22 yayımlanabilir görüntü vakasında legacy JSON toplamı 27.326.630 byte, GLB toplamı
12.548.904 byte oldu: ham aktarımda **%54,1 azalma**.

| Örnek | JSON | GLB | Azalma | gzip JSON | gzip GLB |
|---|---:|---:|---:|---:|---:|
| Küçük — UCSF-PDGM-0420 | 659.220 B | 312.204 B | %52,6 | 173.459 B | 156.396 B |
| Ortanca — UCSF-PDGM-0071 | 1.163.750 B | 543.940 B | %53,3 | 302.726 B | 270.832 B |
| Büyük — UCSF-PDGM-0452 | 2.086.353 B | 950.836 B | %54,4 | 532.743 B | 470.956 B |

gzip sayıları aynı payload'ların Python gzip seviye 6 ile çevrimdışı ölçümüdür;
Caddy'nin gerçek transfer boyutu olarak sunulmaz. GLB'nin asıl kazancı değişmez
cache URL'si ve tarayıcıda daha az ayrıştırma/kopyalamadır.

## Ayrıştırma ve çizilebilir geometri hazırlığı

Node.js 26.8.2 ve Three.js 0.186 ile her örnek bir ısınma ve on ölçüm çalıştırıldı.
JSON tarafında `JSON.parse`, typed-array üretimi ve normal hesabı; GLB tarafında
`GLTFLoader`, buffer view oluşturma ve normal hesabı ölçüldü. Dosya okuma ve WebGL
çizimi süreye dahil değildir.

| Örnek | JSON p50 | GLB p50 |
|---|---:|---:|
| Küçük | 13,04 ms | 5,71 ms |
| Ortanca | 29,05 ms | 6,86 ms |
| Büyük | 39,84 ms | 12,15 ms |

Tekrarlanabilir komut:

```bash
node frontend/scripts/benchmark_meshes.mjs \
  <LEGACY_CASES_ROOT> <GLB_CASES_ROOT> \
  UCSF-PDGM-0420 UCSF-PDGM-0071 UCSF-PDGM-0452
```

## Cache ve yükleme davranışı

- GLB dosya adı ve URL'si payload SHA-256 özetini taşır.
- MCP dosyanın özetini yeniden hesaplar; API URL özetiyle eşleşmeyen payload'ı
  reddeder.
- Hash'li GLB yanıtı `public, max-age=31536000, immutable` kullanır. Paket değişirse
  URL değişir; kısa süreli legacy `/mesh` ucu değişmez cache almaz.
- Frontend yalnız seçili vakanın mesh'ini yükler. Mevcut mesh başladıktan 2,5 saniye
  sonra tarayıcı boş kaldığında yalnız listedeki bir sonraki GLB düşük öncelikli
  cache isteğine alınır. Genomik modül bütün mesh'leri indirmez.

## Açık ölçüm

Gerçek Caddy → API → MCP zincirinde soğuk/sıcak transfer ve seçimden ilk WebGL
karesine p50 henüz ölçülmedi. Issue #21'in 300 ms sıcak-cache yayın kapısı bu
tarayıcı ölçümü kaydedilmeden tamamlanmış sayılmaz. Ölçüm en küçük, ortanca ve en
büyük vaka için tarayıcı ağ cache'i açık/kapalı ayrı çalıştırılmalıdır.
