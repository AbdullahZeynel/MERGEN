# MERGEN

ERGENEKON takımının TEKNOFEST Onkolojide 3T için geliştirdiği çok modlu glioma karar destek prototipi.

- **Görüntü:** nnU-Net + Swin UNETR + UWCSE ile dört MR modalitesinden segmentasyon.
- **Genomik:** ESM-2 + AAindex + XGBoost ile missense varyant patojenite tahmini.

Mevcut kod araştırma/değerlendirme betikleri, eski sonuç görüntüleyicisi ve yeni React vaka arayüzünün F1 temelini içerir. Canlı API, iş kuyruğu, MCP ve sohbet asistanı henüz uygulanmadı. İki modülün çıktısını birlikte göstermek, doğrulanmış bir klinik füzyon modeli anlamına gelmez.

## Dizinler

| Yol | Sorumluluk |
|---|---|
| `models/imaging/` | Görüntü algoritmaları, çıkarım ve değerlendirme betikleri |
| `models/VeriOdakliCozum/` | Genomik Python paketi; mevcut import adı korundu |
| `frontend/legacy/` | Mevcut HTML/Three.js dashboard; yeni arayüz `frontend/` altında |
| `backend/legacy/` | Mevcut demo sunucusu; yeni uygulama API'si `backend/` altında |
| `mcp/` | Gelecekteki MCP araç katmanı |
| `infra/` | VPS, Ubuntu, Caddy ve Tailscale kurulum dosyaları için yer |
| `docs/PLAN.md` | Mimari kararlar, kapsam ve geliştirme sırası |
| `docs/LOCAL_ASSETS.md` | Git dışındaki ağırlık/veri/sonuçların konumları |
| `docs/references/`, `docs/archive/` | Yerel raporlar ve tarihsel notlar; Git dışı |

## Yeni arayüzü açma

```bash
cd frontend
npm ci
python3 scripts/prepare_demo.py
npm run dev
```

Yerel adres: `http://127.0.0.1:5173/`. Python adımı mevcut yerel FLAIR hacimlerinden önizleme üretir; NumPy/Pillow gerekir. Görüntü verileri Git dışıdır. Kurulum, testler ve F1 sınırları için [frontend rehberi](frontend/README.md); VPS paketleme için [dağıtım rehberi](infra/vps/README.md).

## Eski demoyu açma

Repo kökünde; görüntü ortamı hazırlanmış ve yerel sonuç dosyaları mevcutsa:

```bash
bash models/imaging/kurulum.sh
models/imaging/.venv/bin/python backend/legacy/serve_dashboard.py
```

Tarayıcı: `http://localhost:8000`. Kurulum betiği bağımlılık indirir; bu düzenleme sırasında çalıştırılmadı. Demo sunucusu geliştirme içindir; internete doğrudan açılmamalı. Arayüzün mevcut CDN bağımlılıkları nedeniyle henüz tam çevrimdışı değildir.

Genomik ortam ayrı kurulmalıdır:

```bash
python3 -m venv models/VeriOdakliCozum/.venv
models/VeriOdakliCozum/.venv/bin/python -m pip install -r models/VeriOdakliCozum/requirements.txt
```

`main.py` genomik modeli **eğitir**, görüntü betikleri **değerlendirme** içerir. Bunlar canlı kullanıcı isteği için servis komutu değildir. Veri/ağırlıklar Git klonuyla gelmez; ayrıntılar [yerel dosya rehberinde](docs/LOCAL_ASSETS.md).

## Geliştirme

Önce [AGENTS.md](AGENTS.md), ardından [planı](docs/PLAN.md) okuyun. Her işte kapsamı küçük tutun, bulguları kaynakla doğrulayın ve gerçekten çalıştırılan kontrolleri belirtin. Üçüncü taraf kodun lisanslarını koruyun; proje geneli için henüz lisans seçilmedi.

Frontend çalışma sırası [sprint planında](docs/FRONTEND_SPRINTS.md) tutulur. Yerel commitler sprint dalında biriktirilir; push ayrıca yapılır. Göndermeden önce `git status --short` ve `git diff --cached --stat` ile seçilen dosyaları inceleyin.
