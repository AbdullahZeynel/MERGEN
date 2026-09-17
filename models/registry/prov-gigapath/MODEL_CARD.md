# Prov-GigaPath — patoloji tile/slide foundation model (erişim onaylı)

- **Kayıt kimliği:** `prov-gigapath`
- **Alan / tür:** pathology / frozen_encoder
- **Köken:** external_pretrained
- **Üründeki rolü:** dependency_of_tum
- **Ürün kararı (2026-09-14):** `dependency` — Koşullu modellerin ihtiyaç duyduğu encoder.
- **Durum:** `gated_access_required` — Ağırlıklar Hugging Face'te 'gated' (koşul kabulü + hesap gerekir); indirilmedi. TUM MoE checkpointleri bu embeddingleri (1536-d) bekler.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** Apache-2.0 (HF model kartı), erişim koşullu
- **Kod lisansı:** Apache-2.0
- **Not:** Kullanıcı HF hesabıyla koşulları kabul etmeli; token yerelde tutulmalı, depoya yazılmamalı.
- Kod: https://github.com/prov-gigapath/prov-gigapath
- Ağırlık (HF, gated): https://huggingface.co/prov-gigapath/prov-gigapath
- hf_sha: `64f9e26c15019f2d4f6d9113c6822f88bb16b01b`
- retrieved: `2026-09-14`

Atıf:

- Xu H, Usuyama N, Bagga J, et al. A whole-slide foundation model for digital pathology from real-world data. Nature 2024;630:181–188. https://doi.org/10.1038/s41586-024-07441-w

## Mimari

ViT-g/14 tile encoder (1536-d) + LongNet slide encoder.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "Providence Health real-world data",
    "wsis": "≈171.000 WSI (makale)",
    "note": "EBRAINS/TCGA içermez (TUM makalesi)."
  },
  "notes": []
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Bu kayıtta TUM zinciri için bağımlılık olarak tutulur; kendi görev metrikleri makalede.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

Yerel ağırlık/dosya yok.

## Yerel kod ve ortam

- Ortam: timm + torch; HF token.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | – |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`huggingface-cli login` sonrası `timm.create_model('hf_hub:prov-gigapath/prov-gigapath', pretrained=True)`.
