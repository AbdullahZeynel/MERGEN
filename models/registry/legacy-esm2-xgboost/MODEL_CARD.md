# ESM-2 + AAindex + XGBoost missense varyant prototipi

- **Kayıt kimliği:** `legacy-esm2-xgboost`
- **Alan / tür:** genomics / variant_classifier
- **Köken:** team_component
- **Üründeki rolü:** out_of_core_scope
- **Ürün kararı (2026-09-14):** `out_of_scope` — Çekirdek kapsam dışı.
- **Durum:** `deferred` — Çekirdek glioma görüntü akışından çıkarıldı; yerel ağırlık, veri ve sonuç yok.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** n/a
- **Kod lisansı:** Proje lisansı
- **Not:** ESM-2 MIT lisanslıdır.
- Yerel kod: models/VeriOdakliCozum/
- ESM-2: https://huggingface.co/facebook/esm2_t30_150M_UR50D
- retrieved: `2026-09-14`

## Mimari

ESM-2 (t30_150M) log-olasılık skorları + AAindex fizikokimyasal farklar → XGBoost.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "note": "TCGA-GBM/LGG MAF missense varyantları; yerel veri yok."
  },
  "notes": [
    "Veri erişim hatasında demo/sentetik girdiye düşen yollar canlı servis öncesi fail-closed yapılmalıdır."
  ]
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Yeniden üretilmiş split ve metrik yoktur.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

Yerel ağırlık/dosya yok.

## Yerel kod ve ortam

- `models/VeriOdakliCozum/`
- Ortam: Ayrı venv (transformers, xgboost).

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | – | – | ❌ | ❌ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

Çekirdek dışı; ileride 'varyant yorumlama' araştırma modülü.
