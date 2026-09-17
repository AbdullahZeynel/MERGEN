# MERGEN UWCSE — nnU-Net + Swin UNETR bölge/belirsizlik füzyonu

- **Kayıt kimliği:** `mergen-uwcse`
- **Alan / tür:** mri / ensemble_rule
- **Köken:** team_component
- **Üründeki rolü:** primary_mri_output
- **Ürün kararı (2026-09-14):** `core` — Doktor akışında kullanılır.
- **Durum:** `coefficients_fitted_evaluated` — Katsayılar 30 doğrulama vakasında sabitlendi ve 172 bağımsız vakada (BraTS21 kohortu dışı UCSF-PDGM) değerlendirildi.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** n/a
- **Kod lisansı:** Proje lisansı
- **Not:** Öğrenilmiş checkpoint değildir; validation'da belirlenen katsayılarla çalışan ensemble kuralıdır.
- Yerel kod: models/imaging/uwcse_ensemble.py
- Değerlendirme betiği: models/imaging/evaluate_uwcse.py
- retrieved: `2026-09-14`

## Mimari

Sınıf bazlı ağırlık + voxel entropisi ile olasılık birleştirme ve son işleme; TC/WT/ET çıktısı.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "note": "Ağ eğitimi yok."
  },
  "validation": {
    "planned": "UCSF-PDGM BraTS21-dışı vakalar: 10 validation (katsayı) + 20 test (evaluate_uwcse.py tasarımı); veri yerelde yok."
  },
  "notes": []
}
```

## Yayımlanmış (upstream) sonuçlar

Yayımlanmış görev metriği yok.

Not: Yayımlanmış upstream sonucu yoktur. MERGEN'in yeniden üretilebilir sonuç artifacti henüz üretilmedi.

## MERGEN sonuçları

**Segmentasyon değerlendirmesi — `uwcse_v1`** · UCSF-PDGM v5, BraTS21 segmentasyon kohortu dışı vakalar · test n=192 (ağırlıkların ölçüldüğü n=10, uygun vaka havuzu 202, tohum 42).

| Varyant | Dice TC | Dice WT | Dice ET | Ortalama | %95 GA (ortalama) | iyi tek modele göre |
|---|---:|---:|---:|---:|---|---|
| nnUNet | 0.5745 | 0.9296 | 0.5954 | **0.6998** | 0.6600–0.7397 | -0.1604 [-0.1986, -0.1242] · 0/192 |
| SwinUNETR | 0.7550 | 0.9138 | 0.8315 | **0.8334** | 0.8021–0.8632 | -0.0269 [-0.0411, -0.0151] · 0/192 |
| V0_Naive | 0.7510 | 0.9208 | 0.8198 | **0.8306** | 0.7990–0.8601 | -0.0297 [-0.0457, -0.0165] · 86/192 |
| V1_CSW | 0.5890 | 0.9307 | 0.8329 | **0.7842** | 0.7553–0.8117 | -0.0761 [-0.0969, -0.0564] · 69/192 |
| V2_CSW+UNC | 0.5986 | 0.9294 | 0.8337 | **0.7873** | 0.7582–0.8149 | -0.0730 [-0.0935, -0.0538] · 73/192 |
| V3_CSW+PP | 0.5890 | 0.9307 | 0.8529 | **0.7909** | 0.7628–0.8168 | -0.0694 [-0.0906, -0.0493] · 70/192 |
| V4_UWCSE_Full **←ürün** | 0.5986 | 0.9294 | 0.8535 | **0.7939** | 0.7666–0.8199 | -0.0664 [-0.0877, -0.0473] · 73/192 |

Uydurulmuş nnU-Net ağırlıkları: TC 0.530 · WT 0.685 · ET 0.445 (0,5 üstü = nnU-Net ağır basıyor). Şekiller `results/uwcse_v1/figures/` altındadır.

> nnU-Net ve Swin UNETR BraTS21 Training üzerinde eğitildi; bu vakalar o kohortun dışındadır, dolayısıyla bağımsız testtir. Ağırlıklar yalnız val vakalarında uyduruldu. Ortalama Dice tek başına yanıltıcıdır: test vakalarının üçte birinde referansta hiç tümör çekirdeği/kontrast tutan bölge yoktur (kontrast tutmayan düşük dereceli gliomalar), orada Dice 'örtüşme' değil 'susabildin mi' sorusunu ölçer. by_region_presence bunu ayırır.

**Segmentasyon değerlendirmesi — `uwcse_v2`** · UCSF-PDGM v5, BraTS21 segmentasyon kohortu dışı vakalar · test n=172 (ağırlıkların ölçüldüğü n=30, uygun vaka havuzu 202, tohum 42).

| Varyant | Dice TC | Dice WT | Dice ET | Ortalama | %95 GA (ortalama) | iyi tek modele göre |
|---|---:|---:|---:|---:|---|---|
| nnUNet | 0.5895 | 0.9287 | 0.5962 | **0.7048** | 0.6617–0.7467 | -0.1558 [-0.1958, -0.1206] · 0/172 |
| SwinUNETR | 0.7617 | 0.9074 | 0.8262 | **0.8318** | 0.7993–0.8637 | -0.0288 [-0.0459, -0.0149] · 0/172 |
| V0_Naive | 0.7564 | 0.9175 | 0.8130 | **0.8289** | 0.7957–0.8617 | -0.0317 [-0.0484, -0.0167] · 78/172 |
| V1_CSW | 0.7631 | 0.9299 | 0.8276 | **0.8402** | 0.8086–0.8714 | -0.0204 [-0.0346, -0.0085] · 88/172 |
| V2_CSW+UNC | 0.7640 | 0.9288 | 0.8285 | **0.8404** | 0.8086–0.8715 | -0.0202 [-0.0344, -0.0081] · 88/172 |
| V3_CSW+PP | 0.7631 | 0.9299 | 0.8499 | **0.8476** | 0.8169–0.8768 | -0.0130 [-0.0276, +0.0003] · 88/172 |
| V4_UWCSE_Full **←ürün** | 0.7640 | 0.9288 | 0.8505 | **0.8478** | 0.8171–0.8769 | -0.0128 [-0.0275, +0.0005] · 88/172 |

Uydurulmuş nnU-Net ağırlıkları: TC 0.425 · WT 0.697 · ET 0.447 (0,5 üstü = nnU-Net ağır basıyor). Şekiller `results/uwcse_v2/figures/` altındadır.

> nnU-Net ve Swin UNETR BraTS21 Training üzerinde eğitildi; bu vakalar o kohortun dışındadır, dolayısıyla bağımsız testtir. Ağırlıklar yalnız val vakalarında uyduruldu. Ortalama Dice tek başına yanıltıcıdır: test vakalarının üçte birinde referansta hiç tümör çekirdeği/kontrast tutan bölge yoktur (kontrast tutmayan düşük dereceli gliomalar), orada Dice 'örtüşme' değil 'susabildin mi' sorusunu ölçer. by_region_presence bunu ayırır.

**Segmentasyon değerlendirmesi — `uwcse_v3`** · UCSF-PDGM v5, BraTS21 segmentasyon kohortu dışı vakalar · test n=172 (ağırlıkların ölçüldüğü n=30, uygun vaka havuzu 202, tohum 42).

| Varyant | Dice TC | Dice WT | Dice ET | Ortalama | %95 GA (ortalama) | iyi tek modele göre |
|---|---:|---:|---:|---:|---|---|
| nnUNet | 0.5895 | 0.9287 | 0.5962 | **0.7048** | 0.6617–0.7467 | -0.1558 [-0.1958, -0.1206] · 0/172 |
| SwinUNETR | 0.7617 | 0.9074 | 0.8262 | **0.8318** | 0.7993–0.8637 | -0.0288 [-0.0459, -0.0149] · 0/172 |
| V0_Naive | 0.7564 | 0.9175 | 0.8130 | **0.8289** | 0.7957–0.8617 | -0.0317 [-0.0484, -0.0167] · 78/172 |
| V1_CSW | 0.7631 | 0.9299 | 0.8276 | **0.8402** | 0.8086–0.8714 | -0.0204 [-0.0346, -0.0085] · 88/172 |
| V2_CSW+UNC | 0.7640 | 0.9288 | 0.8285 | **0.8404** | 0.8086–0.8715 | -0.0202 [-0.0344, -0.0081] · 88/172 |
| V3_CSW+PP | 0.8121 | 0.9299 | 0.8558 | **0.8659** | 0.8365–0.8938 | +0.0053 [-0.0137, +0.0262] · 89/172 |
| V4_UWCSE_Full **←ürün** | 0.8126 | 0.9288 | 0.8564 | **0.8659** | 0.8366–0.8939 | +0.0053 [-0.0138, +0.0261] · 89/172 |

Uydurulmuş nnU-Net ağırlıkları: TC 0.425 · WT 0.697 · ET 0.447 (0,5 üstü = nnU-Net ağır basıyor). Şekiller `results/uwcse_v3/figures/` altındadır.

> nnU-Net ve Swin UNETR BraTS21 Training üzerinde eğitildi; bu vakalar o kohortun dışındadır, dolayısıyla bağımsız testtir. Ağırlıklar yalnız val vakalarında uyduruldu. Ortalama Dice tek başına yanıltıcıdır: test vakalarının üçte birinde referansta hiç tümör çekirdeği/kontrast tutan bölge yoktur (kontrast tutmayan düşük dereceli gliomalar), orada Dice 'örtüşme' değil 'susabildin mi' sorusunu ölçer. by_region_presence bunu ayırır.

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

Yerel ağırlık/dosya yok.

## Yerel kod ve ortam

- `models/imaging/uwcse_ensemble.py`
- `models/imaging/evaluate_uwcse.py`
- `models/imaging/ensemble_inference.py`
- `models/imaging/compute_stats.py`
- Ortam: nnU-Net ve Swin ortamlarının ikisi de gerekir.

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | – | ✅ | ✅ | ✅ |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

İki temel model çalıştıktan sonra `evaluate_uwcse.py` ile katsayılar validation'da dondurulur.

## Notlar

- İki hard-coded demo vakası klinik kanıt sayılmaz.
