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
dönüştürülür; 3D yüzeyler içerik özetli binary GLB olarak yazılır. Bu iki 2D
katman arayüzde ayrı açılır. Tahmin maskeleri daha önce
üretilmiş sonuçlardır; kaynak T1/T2 kanalları yeniden sağlanmadan çıkarım ve Dice
skorları yeniden üretilemez. Beyin bağlamı aynı voxel koordinatlarında MR ön
planının en büyük bağlantılı bölgesinden türetilir. Bu yaklaşık dış yüzeydir;
sağlıklı doku/korteks segmentasyonu değildir. ET, kaynak etiketindeki *enhancing
tumor* kısaltmasıdır; arayüzde “Kontrast tutan tümör” yazılır.

Değerlendirme sırasında kaydedilmiş olasılık önbelleklerinden ek vaka hazırlamak
için `materialize_eval_cases.py` kullanılır. Betik model çalıştırmaz veya ağırlık
aramaz; `results_eval/optimal_weights.json` içindeki kayıtlı validation
ağırlıklarını uygular. Cache, veri, ara sonuç ve demo paketi Git dışında kalır.
Yayımlanacak vakalar `prepare_demo.py --cases ...` ile açıkça seçilir;
`--all-cases` yalnız kaynak dizindeki bütün vakalar gözden geçirildiyse kullanılır.

```bash
models/imaging/.venv/bin/python models/imaging/materialize_eval_cases.py \
  --cache models/imaging/results_eval/_probs_cache \
  --dataset models/imaging/UCSF-PDGM \
  --weights models/imaging/results_eval/optimal_weights.json \
  --output .local/eval-demo-source \
  --cases UCSF-PDGM-0026 UCSF-PDGM-0056

models/imaging/.venv/bin/python frontend/scripts/prepare_demo.py \
  --source .local/eval-demo-source \
  --output .local/demo-v3-expanded \
  --all-cases
```

Patoloji koleksiyonunu ve ölçülmüş MRI figürlerini ekleyerek paket v4 üretilir.
Betik model çalıştırmaz, bilimsel paket istemez: slayt görüntüleri, figürler ve
yanlarındaki sayılar dondurulmuş kanıt arşivinden kopyalanır, görüntü koleksiyonu
ise mevcut paketten alınır.

```bash
backend/.venv/bin/python frontend/scripts/prepare_demo_v4.py \
  --imaging-package .local/demo-v3-glb-22 \
  --wsi-cases .local/evidence-2026-09-17/06_figures/wsi/cases \
  --mri-examples .local/evidence-2026-09-17/06_figures/mri/cases \
  --output .local/demo-v4
```

17 Eylül 2026 arşiviyle çıktı 246 MB olur: 22 kopyalanmış görüntü vakası,
12 slayt vakası (5'i referansla çelişiyor, 2'si çekimserlik eşiğinin altında,
8 merkez) ve 5 MRI figürü. Kaynak pakette kalan `genomics` koleksiyonu kapsam
dışı olduğu için kopyalanmaz.

Betik arşivin kendisi hakkındaki iddialarını yeniden hesaplar: bildirilen sınıf
en yüksek olasılık olmalı, `correct` bayrağı gerçek karşılaştırmayla uyuşmalı,
klasör adı `<split>_<hasta>` kalıbıyla kaydın hastasını göstermeli ve bütün
slaytlar aynı model notunu taşımalı. Tutmayan vaka paketi düşürür; çıktı ancak
tamamlandığında tek `rename` ile yayımlanır. Yanlış sınıflanan vakalar
`agreesWithReference: false` etiketiyle pakette kalır, atılmaz. `thumbnail.jpg`
varsa alınır, yoksa o varlık hiç bildirilmez. MRI figürleri vaka değildir:
`examples/` altına yazılır ve vaka uçlarında görünmez.

Mevcut schema-v3 paketini kesitleri yeniden üretmeden GLB biçimine geçirmek için
kaynak korunarak yeni bir çıktı dizini oluşturulur:

```bash
models/imaging/.venv/bin/python frontend/scripts/migrate_demo_meshes.py \
  --source .local/demo-v3-expanded \
  --output .local/demo-v3-expanded-glb
```

Manifestteki mesh URL'si GLB içeriğinin SHA-256 özetini taşır. API bu özeti tekrar
doğrular ve yalnız bu URL'ye `public, max-age=31536000, immutable` verir. Paket
değiştiğinde URL de değişir; eski JSON paketleri geçiş süresince okunmaya devam
eder.

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
| `/api/demo/modules/{module}/diseases/{disease}/cases` | `list_cases` | Filtreli koleksiyon manifesti (v3 ya da v4) |
| `/api/demo/modules/{module}/diseases/{disease}/cases/{id}/...` | filtreli varlık aracı | Koleksiyona bağlı PNG/JSON varlığı |
| `/api/demo/modules/{module}/diseases/{disease}/cases/{id}/images/{kind}` | `get_pathology_image` | Slayt attention/en yüksek kare/thumbnail JPEG'i |
| `/api/demo/modules/{module}/diseases/{disease}/cases/{id}/report` | `get_case_report` | Vakanın hazır rapor JSON'u |
| `/api/demo/modules/{module}/diseases/{disease}/examples/{id}/figure` | `get_example_figure` | Doğrulama figürü PNG'si; vaka değildir |
| `/api/demo/cases` | `list_cases` | Mevcut arayüz için v2 uyumluluk yanıtı |
| `/api/demo/cases/{id}/slices/{axis}/{index}` | `get_slice` | PNG, sıfır tabanlı indeks |
| `/api/demo/cases/{id}/overlays/{layer}/{axis}/{index}` | `get_overlay` | Şeffaf tahmin veya referans PNG'si |
| `/api/demo/cases/{id}/mesh/{sha256}.glb` | `get_mesh` | İçerik özetli binary GLB yüzeyleri |
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

Smoke testi çalışan yerel servislerde her vakanın üç eksenindeki ilk/orta/son
kesitlerini, GLB başlığını, değişmez cache kuralını ve checksum'larını 10 eşzamanlı
HTTP isteğiyle kontrol eder. Bu bir kullanıcı kapasite testi değildir. VPS
kurulumu: [dağıtım rehberi](../infra/vps/README.md).
Boyut ve ayrıştırma karşılaştırması [3D mesh performans kaydındadır](3D_MESH_PERFORMANCE.md).
