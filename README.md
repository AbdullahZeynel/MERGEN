# MERGEN

ERGENEKON takımının TEKNOFEST Onkolojide 3T için geliştirdiği çok modlu glioma karar destek prototipi.

- **Görüntü:** nnU-Net + Swin UNETR + UWCSE ile dört MR modalitesinden segmentasyon.
- **Genomik:** ESM-2 + AAindex + XGBoost ile missense varyant patojenite tahmini.

Mevcut kod araştırma/değerlendirme betikleri ve React vaka arayüzünü içerir. Hazır demo: tarayıcı → API → MCP → VPS diskindeki dosyalar. Tüm 2D kesitler, etkileşimli 3D tümör yüzeyleri ve yaklaşık MR dış yüzeyi hazırdır. Canlı oturum/kuyruk ve özel worker API'si geliştirme dalında hazırlanmıştır; GPU worker, model adaptörleri ve canlı arayüz henüz bağlı değildir. Sohbet asistanı ertelenmiştir. İki modülün çıktısını birlikte göstermek, doğrulanmış bir klinik füzyon modeli anlamına gelmez.

## Dizinler

| Yol | Sorumluluk |
|---|---|
| `models/imaging/` | Görüntü algoritmaları, çıkarım ve değerlendirme betikleri |
| `models/VeriOdakliCozum/` | Genomik Python paketi; mevcut import adı korundu |
| `frontend/legacy/` | Mevcut HTML/Three.js dashboard; yeni arayüz `frontend/` altında |
| `backend/legacy/` | Mevcut demo sunucusu; yeni uygulama API'si `backend/` altında |
| `mcp/` | VPS'teki salt okunur demo araçları |
| `infra/` | VPS, Ubuntu, Caddy ve Tailscale kurulum dosyaları için yer |
| `docs/PLAN.md` | Mimari kararlar, kapsam ve geliştirme sırası |
| `docs/SYSTEM_SPRINTS.md` | Canlı oturum, GPU worker, model entegrasyonu ve sprint planı |
| `docs/GENOMICS_AUDIT.md` | Genomik modelin denetim kaydı ve çıkarım adaptörünün sınırları |
| `docs/LOCAL_ASSETS.md` | Git dışındaki ağırlık/veri/sonuçların konumları |
| `docs/references/`, `docs/archive/` | Yerel raporlar ve tarihsel notlar; Git dışı |

## Yeni arayüzü açma

```bash
cd frontend
npm ci
npm run dev
```

Yerel adres: `http://127.0.0.1:5173/`. Önce [demo servis rehberindeki](docs/DEMO_SERVICES.md) API ve MCP'yi başlatın. Görüntü verileri Git dışıdır. Arayüz sınırları için [frontend rehberi](frontend/README.md); VPS paketleme için [dağıtım rehberi](infra/vps/README.md).

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
