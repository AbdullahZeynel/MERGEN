# Backend

`api.py` loopback üzerinde tarayıcıya demo ve canlı oturum uçlarını sunar. Demo
okumalarını MCP araçlarına devreder. `live_api.py` geçici yükleme, oturum ve sonuç
indirmeyi; `live_store.py` SQLite kuyruğunu yönetir. Model kodu VPS'te çalışmaz.

`control.py`, GPU worker'ların Tailscale üzerinden iş çektiği ayrı ve kimlik
doğrulamalı uygulamadır. `run_control.py` bu uygulamayı yalnız yapılandırılmış
Tailscale adresine bağlar. `cleanup.py` süresi dolan oturumları silen tek seferlik
systemd timer işidir. Genel API ile worker API aynı dinleme adresini paylaşmaz.

Hazır demo kurulumu: [demo servisleri](../docs/DEMO_SERVICES.md). Canlı mimari ve
sprintler: [sistem sprintleri](../docs/SYSTEM_SPRINTS.md). `legacy/` eski sunucuyu korur.
