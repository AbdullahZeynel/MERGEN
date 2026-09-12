# MERGEN arayüzü

React + TypeScript + Vite. Vaka listesi, filtre/arama, demo ve canlı ayrımı, tüm FLAIR kesitleri, etkileşimli 3D yüzeyler, genomik boş durum ve asistan paneli. Fontlar build'e dahildir; çalışma sırasında CDN gerekmez.

## Yerel çalıştırma

Node.js 22.22.2+, 24.15+ veya 26+ ve npm gerekir. Demo hazırlama bağımlılıkları `scripts/requirements-demo.txt` içindedir; servis kurulumundan ayrıdır. Node alt sürüm sınırını test ortamı bağımlılığı belirler.

```bash
cd frontend
npm ci
npm run dev
```

Adres: `http://127.0.0.1:5173/`. Eksik Python bağımlılıklarını sistem ortamına zorla kurmayın; ayrı bir venv kullanın. Hazırlama kaynağının varsayılanı `models/imaging/results/`; `--source` ile değiştirilebilir.

Önce [demo servis rehberini](../docs/DEMO_SERVICES.md) izleyerek API ve MCP'yi başlatın. Manifest, PNG ve mesh dosyaları MCP'nin özel veri dizininde Git dışıdır; frontend `public/` içinde tutulmaz. Temiz klonda veriler otomatik indirilmez. Paket yalnızca anonim, yayımlanabilir demo vakaları içermelidir.

## Kontroller

```bash
npm run check
```

Testler vaka/sohbet bağlamı, demo–canlı sınırı, filtreler, hata durumları, kesit sınırları/eksen hafızası, mesh doğrulaması ve büyütme modalını kapsar. `npm run build` TypeScript kontrolü ve üretim build'i yapar. `npm run preview` build'i `http://127.0.0.1:4173/` üzerinden sunar; aynı API proxy'sini kullanır.

## Sınırlar ve sonraki sprint

- Üç eksenin bütün kesitleri kaydırıcı, düğmeler ve odaklı alanda ok tuşlarıyla gezilir. Gerçek ensemble mesh, 3D döndürme/yakınlaştırma, bölge görünürlüğü ve tümör opaklığı bağlandı. 2D/3D büyütme hem eni hem boyu kullanır; Escape ile kapanır.
- `prepare_demo.py` sürüm 2 paketine yaklaşık MR dış yüzeyi ekler. Bu korteks segmentasyonu değildir. Eski hedef ezilmez; yeni çıktı dizini kullanın. WebGL hatası açıkça gösterilir; Three.js kaynakları temizlenir.
- Mevcut görüntü vakalarına eşlenmiş genomik sonuç yoktur; XGBoost puanı veya SHAP açıklaması üretilmez.
- Asistan ve canlı API bağlı değildir. “AI servisi bağlı değil” entegrasyon durumudur; makinenin çevrimdışı olduğuna dair ölçüm değildir. Demo API/MCP sağlık ucu `/api/health` uygulanmıştır.
- Eksen adları veri dizisinin eksenleridir. Anatomik yön ve voxel aralığı doğrulanmadan R/L işaretleri, mm ölçümleri veya 2D–3D çapraz konumlama gösterilmez.
- `data/contracts.ts` demo paketini çalışma anında doğrular. F4 canlı sözleşmesi ayrı doğrulanarak `DataSource` katmanına eklenecek; API hatası demo sonuçlarına dönüşmez.
- Arayüz yalnızca backend ile konuşacak; GPU/MCP anahtarı tarayıcıya gelmez. F1'de frontend `.env` ihtiyacı yoktur. Sonradan eklenen `VITE_*` değerleri herkese açık build içeriğidir; sır içeremez.

VPS dağıtımı: [infra/vps/README.md](../infra/vps/README.md). Eski HTML gösterimi `legacy/` altında korunur; yeni uygulamanın bağımlılık taramasına dahil edilmez.
