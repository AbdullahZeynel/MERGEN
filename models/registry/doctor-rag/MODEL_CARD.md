# Doktor RAG yardımcısı

- **Kayıt kimliği:** `doctor-rag`
- **Alan / tür:** knowledge / retrieval_augmented_assistant
- **Köken:** team_component
- **Üründeki rolü:** phase3_doctor_assistant
- **Ürün kararı (2026-09-14):** `planned` — Sonraki faz.
- **Durum:** `deferred` — LLM, embedding modeli ve doküman korpusu seçilmedi.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** n/a
- **Kod lisansı:** Proje lisansı
- retrieved: `2026-09-14`

## Mimari

Retrieval (vektör + kelime) + LLM + güvenlik kuralları; kaynaklı cevap.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "note": "Model eğitimi yok."
  },
  "notes": []
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Retrieval recall, citation precision, faithfulness ve güvenli-red testleri planlanmıştır.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

Yerel ağırlık/dosya yok.

## Yerel kod ve ortam

- Ortam: Seçilmedi.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| – | – | – | – | ❌ | ❌ | ❌ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

Faz 3.
