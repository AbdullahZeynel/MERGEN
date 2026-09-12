# MERGEN arayüzü

React + TypeScript + Vite. F1: vaka listesi, filtre/arama, demo ve canlı ayrımı, gerçek FLAIR merkez kesit önizlemeleri, genomik boş durum ve asistan paneli. Fontlar build'e dahildir; çalışma sırasında CDN gerekmez.

## Yerel çalıştırma

Node.js 22.22.2+, 24.15+ veya 26+ (24 LTS önerilir), npm ve demo ihracı için NumPy/Pillow içeren Python ortamı gerekir. Alt sürüm sınırını test ortamı bağımlılığı belirler.

```bash
cd frontend
npm ci
# Repo içindeki hazır hacimlerden 2 vaka × 3 düzlem üretir; model çalıştırmaz.
python3 scripts/prepare_demo.py
npm run dev
```

Adres: `http://127.0.0.1:5173/`. Başka bir Python ortamı kullanılabilir. Eksik bağımlılıkları sistem Python'una zorla kurmayın; ayrı bir venv kullanın. Kaynak varsayılanı `models/imaging/results/`; `--source` ile değiştirilebilir.

Demo PNG'leri ve manifest `public/demo/` altında Git dışıdır. Paket yoksa anlaşılır hata gösterilir; temiz klonda görüntü otomatik indirilmez. Paket yalnızca anonim, yayımlanabilir demo vakaları içermelidir. Gerçek hasta verisi statik/public dizine konmaz.

## Kontroller

```bash
npm run check
```

Sekiz test: vaka/sohbet bağlamı değişimi, demo–canlı sınırı, arama ve filtre, eksik genomik kayıt, bozuk/boş manifest, görüntü yükleme hatası ve manifest kimlik/eksen doğrulaması. `npm run build` TypeScript kontrolü ve üretim build'i yapar. `npm run preview` build'i `http://127.0.0.1:4173/` üzerinden sunar.

## Sınırlar ve sonraki sprint

- F1, FLAIR hacminin her eksendeki merkez kesitini gösterir. Serbest kesit gezinme, katman/opacity, 3D mesh ve model karşılaştırması F2 kapsamındadır.
- Mevcut görüntü vakalarına eşlenmiş genomik sonuç yoktur; XGBoost puanı veya SHAP açıklaması üretilmez.
- Asistan, canlı API ve servis sağlık kontrolü henüz bağlı değildir. “AI servisi bağlı değil” entegrasyon durumudur; makinenin çevrimdışı olduğuna dair ölçüm değildir.
- Eksen adları veri dizisinin eksenleridir. Anatomik yön ve voxel aralığı doğrulanmadan R/L işaretleri, mm ölçümleri veya 2D–3D çapraz konumlama gösterilmez.
- `data/contracts.ts` demo paketini çalışma anında doğrular. F4 canlı sözleşmesi ayrı doğrulanarak `DataSource` katmanına eklenecek; API hatası demo sonuçlarına dönüşmez.
- Arayüz yalnızca backend ile konuşacak; GPU/MCP anahtarı tarayıcıya gelmez. F1'de frontend `.env` ihtiyacı yoktur. Sonradan eklenen `VITE_*` değerleri herkese açık build içeriğidir; sır içeremez.

VPS dağıtımı: [infra/vps/README.md](../infra/vps/README.md). Eski HTML gösterimi `legacy/` altında korunur; yeni uygulamanın bağımlılık taramasına dahil edilmez.
