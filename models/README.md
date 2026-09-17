# Modeller

| Dizin | İçerik |
|---|---|
| `registry/` | Her bileşenin kökeni, lisansı, veri dağılımı, metrikleri ve yerel varlık hash'leri; ürün / referans ayrımı. Başlangıç: [`registry/README.md`](registry/README.md) |
| `imaging/` | Glioma MR segmentasyonu: nnU-Net + Swin UNETR + UWCSE kuralı; çıkarım ve değerlendirme betikleri |
| `pathology/` | H&E slaytından A/O/G: DINOv2 kare kodlayıcı + Attention-MIL; kare çıkarma, embedding, eğitim, tek slayt çıkarımı (M2 sprintiyle gelir) |

Veri, ağırlık ve üretilen sonuçlar yerelde korunur, Git dışında tutulur. Konumlar:
[yerel dosyalar](../docs/LOCAL_ASSETS.md). Model çalıştırma VPS'nin ve dispatcher'ın
değil, ayrı GPU executor sürecinin sorumluluğudur.
