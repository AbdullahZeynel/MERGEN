# AttentionDeepMIL — gated attention MIL referans kodu

- **Kayıt kimliği:** `attention-deep-mil`
- **Alan / tür:** pathology / reference_code
- **Köken:** literature_reference
- **Üründeki rolü:** architecture_reference
- **Ürün kararı (2026-09-14):** `reference` — Yalnız karşılaştırma ve etiket doğrulama; üründe çalışmaz.
- **Durum:** `code_reference` — MIT lisanslı referans uygulama; ağırlık içermez.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** n/a
- **Kod lisansı:** MIT
- Kod: https://github.com/AMLab-Amsterdam/AttentionDeepMIL
- source_commit: `eb0434ba2795711a45d693d60120ae53532b1b93`
- retrieved: `2026-09-14`

Atıf:

- Ilse M, Tomczak JM, Welling M. Attention-based Deep Multiple Instance Learning. ICML 2018, PMLR 80:2127–2136. https://proceedings.mlr.press/v80/ilse18a.html

## Mimari

Attention ve gated-attention MIL havuzlama (model.py).

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "note": "MNIST-bags oyuncak örneği; patoloji verisi yok."
  },
  "notes": []
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Uygulanmaz.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| reference_code | `models/attention-deep-mil/model.py` | 4389 | `21775302071de4e8…` | present |
| license | `models/attention-deep-mil/LICENSE` | 1090 | `f652daf79344b562…` | present |
| upstream_readme | `models/attention-deep-mil/README.md` | 3747 | `1d7d29f80d71719d…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: n/a

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | – | – | – |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

MERGEN gated Attention-MIL'in mimari referansı.
