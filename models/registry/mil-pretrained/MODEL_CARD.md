# MIL_Pretrained — TITAN/CARE damıtılmış MIL aggregator başlangıç ağırlıkları

- **Kayıt kimliği:** `mil-pretrained`
- **Alan / tür:** pathology / pretrained_mil_initialization
- **Köken:** external_pretrained
- **Üründeki rolü:** optional_initialization
- **Ürün kararı (2026-09-14):** `reference` — Yalnız karşılaştırma ve etiket doğrulama; üründe çalışmaz.
- **Durum:** `weights_verified_license_unclear` — 10 aggregator ağırlığı indirildi; depoda lisans yok; glioma görev başlığı içermez, yalnız başlangıç ağırlığıdır.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Belirtilmemiş (depoda LICENSE yok)
- **Kod lisansı:** Belirtilmemiş
- **Not:** Öğretmen modeller TITAN ve CARE; TITAN CC-BY-NC-ND-4.0 ve erişim onaylıdır.
- Kod + ağırlık: https://github.com/fu0201/MIL_Pretrained
- source_commit: `82906a6bf3e0045e46044897f5adbe30f9d8f77d`
- retrieved: `2026-09-14`

Atıf:

- Pretraining Multiple Instance Learning Networks with Multi-Teacher Distillation from Pathology Slide Foundation Models (depo README; yayın künyesi depoda verilmemiş).

## Mimari

ABMIL, CLAM-SB/MB, TransMIL, 2DMamba, AMDMIL, AEMMIL, DAGMIL, GDFMIL, WiKG aggregatorları (PIANO tabanlı); CONCH v1.5 özellikleriyle damıtılmış.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "note": "Damıtma verisi ve boyutu depoda açıklanmamış; ham WSI ve öğretmen checkpointleri depoda yok."
  },
  "notes": []
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Glioma görevine ait metrik yoktur; A/O/G sınıflandırıcı başlığı yeniden eğitilmeden kullanılamaz.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| init_abmil | `models/mil-pretrained/pretrained_weight/pretrained_abmil.pt` | 5124520 | `392b44d2d0abc3ec…` | present |
| init_clam_sb | `models/mil-pretrained/pretrained_weight/pretrained_clam_sb.pt` | 7094770 | `eec31207ce30ed74…` | present |
| init_clam_mb | `models/mil-pretrained/pretrained_weight/pretrained_clam_mb.pt` | 7096882 | `3af5fca3c4f21010…` | present |
| init_transmil | `models/mil-pretrained/pretrained_weight/pretrained_transmil.pt` | 12797703 | `757ba9b6d33f4d8b…` | present |
| init_2dmamba | `models/mil-pretrained/pretrained_weight/pretrained_2dmamba.pt` | 1598323 | `c782ad82c3082f2b…` | present |
| init_amdmil | `models/mil-pretrained/pretrained_weight/pretrained_amdmil.pt` | 11816303 | `692f975cdb4904d6…` | present |
| init_aemmil | `models/mil-pretrained/pretrained_weight/pretrained_aemmil.pt` | 4733308 | `0e95420d5f28bdcb…` | present |
| init_dagmil | `models/mil-pretrained/pretrained_weight/pretrained_dagmil.pt` | 3839879 | `018876440fbc531f…` | present |
| init_gdfmil | `models/mil-pretrained/pretrained_weight/pretrained_gdfmil.pt` | 3978603 | `762b42a60668cbd8…` | present |
| init_wikg | `models/mil-pretrained/pretrained_weight/pretrained_wikg.pt` | 8942692 | `b917d326e753d708…` | present |
| upstream_readme | `models/mil-pretrained/README.upstream.md` | 7372 | `834897673cabc667…` | present |
| upstream_requirements | `models/mil-pretrained/requirements.upstream.txt` | 522 | `a2a90d9a44cd5c5f…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: Python 3.10, PIANO tabanlı MIL kodu.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | – |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`--pretrained_weights pretrained_weight/pretrained_abmil.pt` ile MIL aggregator başlatılır; sınıflandırıcı başlığı A/O/G verisiyle eğitilir.

## Notlar

- Damıtma CONCH v1.5 özellik uzayına göre yapıldığı için DINOv2 (768-d) özellikleriyle doğrudan uyumlu olmayabilir; giriş boyutu kontrol edilmelidir.
