# Demo servisleri

Karar: **Demo verileri ve MCP VPS'te**. Akış: tarayıcı → Caddy `/api/*` → FastAPI → Streamable HTTP MCP → VPS demo dizini. Ubuntu kapalıyken hazır vakalar açılır. Yerelde aynı üç süreç çalışır; Vite `/api` proxy'sini kullanır. Tarayıcıya altyapı adresi/anahtar verilmez.

## Yerelde

Repo kökünde Python 3.11+ ile servis ortamı; veri hazırlamak için bilimsel paketlerin desteklediği Python sürümü gerekir (mevcut hazırlama ortamı 3.14):

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
# Veri hazırlama yalnızca geliştirme makinesinde; VPS için bu paketler gerekmez.
backend/.venv/bin/python -m pip install -r frontend/scripts/requirements-demo.txt
backend/.venv/bin/python frontend/scripts/prepare_demo.py
```

Hazırlama `.local/demo-v3` üretir; mevcut hedefi ezmez, gerekirse `--output` ile
yeni dizin seçin. Kök `catalog.json`, vakaları `imaging/glioma/cases/` altında
tutan koleksiyon manifestine yönlendirir. MCP geçiş süresince eski v2 paketini de
okur. Kaynak `models/imaging/results/` içindeki iki gözden geçirilmiş vakadır.
Kaynak hacimler, tahmin maskeleri ve tümör mesh'leri değiştirilmez. Her eksendeki
tüm FLAIR kesitleri ile şeffaf ensemble tahmin/referans katmanları PNG'ye
dönüştürülür; bu iki katman arayüzde ayrı açılır. Tahmin maskeleri daha önce
üretilmiş sonuçlardır; kaynak T1/T2 kanalları yeniden sağlanmadan çıkarım ve Dice
skorları yeniden üretilemez. Beyin bağlamı aynı voxel koordinatlarında MR ön
planının en büyük bağlantılı bölgesinden türetilir. Bu yaklaşık dış yüzeydir;
sağlıklı doku/korteks segmentasyonu değildir. ET, kaynak etiketindeki *enhancing
tumor* kısaltmasıdır; arayüzde “Kontrast tutan tümör” yazılır.

Üç ayrı terminalde, repo kökünden:

```bash
MERGEN_DEMO_ROOT="$PWD/.local/demo-v3" backend/.venv/bin/python mcp/server.py
```
```bash
backend/.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 9000
```
```bash
cd frontend
npm ci
npm run dev
```

`http://127.0.0.1:5173/` üzerinden açın. `.env` kendiliğinden yüklenmez; yukarıdaki atama MCP sürecine açıkça aktarır. Hazır paket `frontend/public` içinde tutulmaz; frontend paketi demo dosyası taşımaz.

## Sözleşme ve sınırlar

| HTTP GET | MCP aracı | Sonuç |
|---|---|---|
| `/api/demo/catalog` | `list_catalog` | Modül/hastalık listesi; disk yolu içermez |
| `/api/demo/modules/{module}/diseases/{disease}/cases` | `list_cases` | Filtreli v3 koleksiyon manifesti |
| `/api/demo/modules/{module}/diseases/{disease}/cases/{id}/...` | filtreli varlık aracı | Koleksiyona bağlı PNG/JSON varlığı |
| `/api/demo/cases` | `list_cases` | Mevcut arayüz için v2 uyumluluk yanıtı |
| `/api/demo/cases/{id}/slices/{axis}/{index}` | `get_slice` | PNG, sıfır tabanlı indeks |
| `/api/demo/cases/{id}/overlays/{layer}/{axis}/{index}` | `get_overlay` | Şeffaf tahmin veya referans PNG'si |
| `/api/demo/cases/{id}/mesh` | `get_mesh` | JSON yüzeyler |
| `/api/health` | `list_cases` | Demo MCP hazır; canlı AI bağlı değil |

Kaydırıcı bir tabanlıdır; HTTP indeksi sıfır tabanlıdır. Her eksen son seçilen kesitini korur; vaka değişimi bağlamı sıfırlar. Yeni kesit yüklenirken eski kesit yeni numarayla gösterilmez. Anatomik yön/voxel aralığı doğrulanmadığı için mm ve R/L işaretleri yoktur.

MCP bilinmeyen modül, hastalık, vaka, eksen, sınır dışı indeks ve dizin dışına
çıkan yolları reddeder. Varlık başına 8 MiB sınırı, gateway'de SHA-256 denetimi ve
15 saniye zaman aşımı vardır. Aynı anda dört MCP çağrısı işlenir; bu **10 kullanıcı
oturum sınırı değildir**. Bu uçlar yalnızca yayımlanabilir demo verisi içindir;
gerçek hasta verisi yükleme yoktur. API hatası demo/canlı geçişini tetiklemez.
Canlı model bağlantısı ve chatbot henüz bağlı değildir.

## Kontrol

```bash
backend/.venv/bin/python -m unittest backend.test_demo
backend/.venv/bin/python infra/vps/smoke-demo.py
```

Smoke testi çalışan yerel servislerde her vakanın üç eksenindeki ilk/orta/son kesitlerini, mesh ve checksum'larını 10 eşzamanlı HTTP isteğiyle kontrol eder. Bu bir kullanıcı kapasite testi değildir. VPS kurulumu: [dağıtım rehberi](../infra/vps/README.md).
