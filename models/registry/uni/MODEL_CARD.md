# UNI — Mahmood Lab patoloji encoder (erişim onaylı, CC-BY-NC-ND-4.0)

- **Kayıt kimliği:** `uni`
- **Alan / tür:** pathology / frozen_encoder
- **Köken:** external_pretrained
- **Üründeki rolü:** dependency_of_gmap
- **Ürün kararı (2026-09-14):** `dependency` — Koşullu modellerin ihtiyaç duyduğu encoder.
- **Durum:** `gated_access_required` — HF 'gated'; ticari olmayan lisans; indirilmedi. GMAP checkpointleri UNI özellikleri bekler.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** CC-BY-NC-ND-4.0, erişim onaylı
- **Kod lisansı:** Depo lisansı (NOASSERTION)
- **Not:** Yarışma/ticari kullanım için lisans uygunluğu ayrıca değerlendirilmeli.
- Kod: https://github.com/mahmoodlab/UNI
- Ağırlık (HF, gated): https://huggingface.co/MahmoodLab/UNI
- hf_sha: `b55a5ec6cade1a39edfe6534189a9b8ca7a022f0`
- retrieved: `2026-09-14`

Atıf:

- Chen RJ, Ding T, Lu MY, et al. Towards a general-purpose foundation model for computational pathology. Nat Med 2024;30:850–862. https://doi.org/10.1038/s41591-024-02857-3

## Mimari

ViT-L/16 (DINOv2 tarifi), 1024-d, Mass-100K üzerinde eğitilmiş.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "Mass-100K (≈100.000 WSI, MGH/BWH + GTEx)",
    "note": "TCGA içermez (makale)."
  },
  "notes": []
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: GMAP bağımlılığı olarak tutulur.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

Yerel ağırlık/dosya yok.

## Yerel kod ve ortam

- Ortam: timm + torch; HF token.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | 🟡 | ✅ | ❌ | ❌ | ❌ | – |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

`huggingface-cli login` sonrası `timm.create_model('hf-hub:MahmoodLab/UNI', pretrained=True, init_values=1e-5, dynamic_img_size=True)`.
