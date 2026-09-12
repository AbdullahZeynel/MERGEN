# Altyapı — planlanan

VPS ve Ubuntu kurulumları, Caddy yönlendirmesi, Tailscale erişim kuralları ve servis yaşam döngüsü burada belgelenecek. [VPS frontend paketleme, kurulum ve rollback](vps/README.md) hazırdır; canlı sunucuda uygulanmadı. [Tailscale hazırlık notları ve kurulum sırası](tailscale/README.md) yazıldı; hiçbir makinede uygulanmadı. Ubuntu/model servisleri henüz kurulmadı. Sırlar ve makineye özel ayarlar Git dışında tutulur; örnek dosyalarda yalnızca yer tutucular bulunur.

Gerçek ayarlar: `backend.env`, `imaging.env`, `genomics.env` gibi yerel dosyalar (Git dışı). Örnekleri `.env.example` veya `*.env.example` olarak Git'e girebilir; boş değer/açık yer tutucu içerir. Gerçek IP, özel hostname veya çalışan sır bulunmaz. Servislerin bu dosyaları okuması ayrıca yapılandırılacaktır. Örneklerin Git'e alınması güvenlik kontrolünü atlatmaz; `AGENTS.md` kuralları geçerlidir.
