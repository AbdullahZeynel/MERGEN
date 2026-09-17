# DINOv2 ViT-B/14 (distilled) — dondurulmuş tile encoder

- **Kayıt kimliği:** `dinov2-vitb14`
- **Alan / tür:** pathology / frozen_encoder
- **Köken:** external_pretrained
- **Üründeki rolü:** wsi_tile_encoder
- **Ürün kararı (2026-09-14):** `core` — Doktor akışında kullanılır.
- **Durum:** `smoke_tested` — Ağırlık ve kaynak kodu mevcut, hash doğrulandı; GPU smoke testi ayrı kayıtta (local_verification.json / dinov2_gpu_smoke.json); gerçek girdiyle yerel çalıştırma kaydı smoke/ altındadır.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Apache-2.0
- **Kod lisansı:** Apache-2.0
- **Not:** Depodaki 'FAIR Noncommercial Research License' notu yalnız xray_dino modelleri içindir; ViT-B/14 Apache-2.0'dır.
- Kod: https://github.com/facebookresearch/dinov2
- Ağırlık: https://dl.fbaipublicfiles.com/dinov2/dinov2_vitb14/dinov2_vitb14_pretrain.pth
- source_commit: `7764ea0f912e53c92e82eb78a2a1631e92725fc8`
- retrieved: `2026-09-12`

Atıf:

- Oquab M, Darcet T, Moutakanni T, et al. DINOv2: Learning Robust Visual Features without Supervision. TMLR 2024. https://arxiv.org/abs/2304.07193

## Mimari

ViT-B/14, 86 M parametre, 768-boyutlu CLS embedding; patch 14; giriş 224×224 (14'ün katı).

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "LVD-142M (etiketsiz, self-supervised)",
    "images": 142000000,
    "source": "https://github.com/facebookresearch/dinov2"
  },
  "notes": [
    "Patolojiye özgü değildir; genel görüntü encoder'ıdır. TCGA üzerinde eğitilmemiştir (WSI kohortumuzla veri sızıntısı riski yok)."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| image_classification | ImageNet-1k | k-NN top-1 | 0.821 | https://github.com/facebookresearch/dinov2 (README tablosu) |
| image_classification | ImageNet-1k | linear top-1 | 0.845 | https://github.com/facebookresearch/dinov2 (README tablosu) |

Not: Patoloji görevi metriği yoktur; encoder MERGEN MIL başlığı için özellik çıkarıcıdır.

## MERGEN sonuçları

Bu makinede (RTX 5060 Ti 16 GB, torch 2.14.0+cu130) yapılan yerel çalıştırma kayıtları `smoke/` altındadır. Bunlar çalışırlık, süre ve VRAM ölçümleridir; kullanılan vakalar eğitim verisiyle örtüşebildiğinden bağımsız klinik değerlendirme değildir. Ayrıntılı tablo ve grafikler `models/registry/report/REPORT.md` içindedir.

- `smoke/dinov2_wsi_smoke.json`
  - TCGA-E1-A7Z3-01Z-00-DX1: 4096 tile, uçtan uca 59.0 tile/s (okuma 67.0, embedding 497.1), tepe VRAM 785 MiB
  - TCGA-DB-A64R-01Z-00-DX1: 4096 tile, uçtan uca 51.0 tile/s (okuma 56.7, embedding 509.6), tepe VRAM 785 MiB
  - TCGA-S9-A7IX-01Z-00-DX1: 3166 tile, uçtan uca 143.7 tile/s (okuma 200.7, embedding 506.7), tepe VRAM 785 MiB

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| checkpoint | `models/dinov2-vitb14/dinov2_vitb14_pretrain.pth` | 346378731 | `0b8b82f85de91b42…` | present |
| source_archive | `models/dinov2-vitb14/dinov2-src-7764ea0f.tar.gz` | 2869642 | `c27dcdaf50e9fb5b…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- `models/pathology/ (planlanan)`
- Ortam: torch 2.14.0+cu130 (mergen-py314 venv) ile yüklenip GPU'da çalıştırıldı; xformers yok (standart attention).

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | – |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`dinov2.models.vision_transformer.vit_base(patch_size=14, img_size=518, init_values=1.0, block_chunks=0)` + `load_state_dict`.
