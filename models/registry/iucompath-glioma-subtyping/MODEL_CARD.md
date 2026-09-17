# IUCompPath WHO2021 glioma subtyping benchmark (Innani et al.)

- **Kayıt kimliği:** `iucompath-glioma-subtyping`
- **Alan / tür:** pathology / benchmark_framework
- **Köken:** literature_reference
- **Üründeki rolü:** offline_benchmark
- **Ürün kararı (2026-09-14):** `reference` — Yalnız karşılaştırma ve etiket doğrulama; üründe çalışmaz.
- **Durum:** `metadata_only` — Görev checkpointi yayımlanmamış; yalnız etiket CSV'leri ve splitler indirildi.
- **Kayıt tarihi:** 2026-09-14

## Kaynak, lisans ve atıf

- **Ağırlık lisansı:** n/a
- **Kod lisansı:** Belirtilmemiş (README: yalnız araştırma / ticari olmayan)
- **Not:** CLAM ve MambaMIL'e dayanır; foundation model lisansları ayrıca geçerlidir.
- Kod + etiketler: https://github.com/IUCompPath/glioma-subtyping
- Makale: https://doi.org/10.1093/neuonc/noaf189
- source_commit: `91c05a533f9a471ab919c8f73d89cc7b25d9bfd1`
- retrieved: `2026-09-14`

Atıf:

- Innani S, Bell WR, Nasrallah MP, Baheti B, Bakas S. AI-driven WHO 2021 classification of gliomas based only on H&E-stained slides. Neuro-Oncology 2026;28(1):282–296. https://doi.org/10.1093/neuonc/noaf189 (PMID 40888157)

## Mimari

8 patoloji FM × 9 MIL aggregator × çoklu büyütme (2.5×/5×/10×/20×) geç füzyon benchmark'ı.

## Eğitim / doğrulama / test verisi

```json
{
  "training": {
    "dataset": "TCGA-GBM/LGG",
    "wsis_paper": 1320,
    "wsis_repo_csv": 1322,
    "cases_repo_csv": 656,
    "class_by_case": {
      "Oligodendroglioma (label 0)": 141,
      "Astrocytoma (label 1)": 226,
      "Glioblastoma (label 2)": 289
    },
    "splits": "10 split; ≈529 eğitim / 59 doğrulama / 66 test vakası",
    "source": "https://github.com/IUCompPath/glioma-subtyping"
  },
  "test": {
    "EBRAINS": {
      "wsis": 794,
      "class": {
        "Astrocytoma": 151,
        "Oligodendroglioma": 173,
        "Glioblastoma": 470
      }
    },
    "IPD-Brain": {
      "wsis": 304,
      "cases": 209,
      "class": {
        "Oligodendroglioma": 68,
        "Glioblastoma": 69,
        "Astrocytoma": 72
      }
    }
  },
  "notes": [
    "Yerel kohortun 638 hastası bu TCGA listesindedir; WHO2021 etiketleri 638/638 uyumludur."
  ]
}
```

Yerel TCGA WSI kohortu (762 hasta) ile ilişki:

```json
{
  "overlap_with_local": 638,
  "label_agreement_with_local": {
    "A->A": 223,
    "G->G": 274,
    "O->O": 141
  },
  "label_disagreements": []
}
```

## Yayımlanmış (upstream) sonuçlar

| Görev | Kohort | Metrik | Değer | Kaynak |
|---|---|---|---|---|
| aog_subtyping | TCGA (eğitim kohortu, hold-out) | AUC (en iyi FM+AM+çoklu büyütme) | 0.9795 | Innani S, Bell WR, Nasrallah MP, Baheti B, Bakas S. AI-driven WHO 2021 classification of gliomas based only on H&E-stained slides. Neuro-Oncology 2026;28(1):282–296. https://doi.org/10.1093/neuonc/noaf189 (PMID 40888157) |
| aog_subtyping | EBRAINS (dış set 1) | AUC | 0.963 | Innani S, Bell WR, Nasrallah MP, Baheti B, Bakas S. AI-driven WHO 2021 classification of gliomas based only on H&E-stained slides. Neuro-Oncology 2026;28(1):282–296. https://doi.org/10.1093/neuonc/noaf189 (PMID 40888157) |
| aog_subtyping | IPD-Brain (dış set 2) | AUC | 0.9261 | Innani S, Bell WR, Nasrallah MP, Baheti B, Bakas S. AI-driven WHO 2021 classification of gliomas based only on H&E-stained slides. Neuro-Oncology 2026;28(1):282–296. https://doi.org/10.1093/neuonc/noaf189 (PMID 40888157) |

Not: Balanced accuracy, precision, recall ve F1 ekte raporlanır; tam metin açık erişimli değildir.

## MERGEN sonuçları

Bu bileşen için MERGEN tarafından üretilmiş yerel çalıştırma veya değerlendirme sonucu yoktur. Yerel dosya doğrulaması ve varsa state-dict yükleme testi `local_verification.json` içindedir; bu bir doğruluk ölçümü değildir.

## Yerel varlıklar (veri kökü: `<MERGEN_DATA_ROOT>`)

| Rol | Yol | Bayt | SHA-256 | Durum |
|---|---|---|---|---|
| labels_csv | `models/iucompath-glioma-subtyping/dataset_csv/tcga_2021_who_labels.csv` | 335188 | `ba20f9dacc8b9518…` | present |
| labels_csv | `models/iucompath-glioma-subtyping/dataset_csv/ebrains_2021_who_labels.csv` | 353431 | `0f3708ac5ceed58a…` | present |
| labels_csv | `models/iucompath-glioma-subtyping/dataset_csv/ipd_2021_who_labels_casewise_final.csv` | 15724 | `71745a0681d7e4eb…` | present |
| labels_csv | `models/iucompath-glioma-subtyping/dataset_csv/ipd_2021_who_labels_slidewise.csv` | 302871 | `da69b0580806d13c…` | present |
| labels_csv | `models/iucompath-glioma-subtyping/dataset_csv/tcga_slides_gbm_lgg_20x.csv` | 203992 | `754a75c137265221…` | present |
| labels_csv | `models/iucompath-glioma-subtyping/dataset_csv/tcga_slides_gbm_lgg_40x.csv` | 302362 | `82588414e808ad90…` | present |
| split_summary | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_summary.csv` | 325 | `060352c5a10b5c99…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_0.csv` | 82364 | `5821b4a3be0f2af1…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_1.csv` | 82445 | `f623424c7866bc2f…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_2.csv` | 82394 | `4e5219648ee4719b…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_3.csv` | 82415 | `a30703f4afe63171…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_4.csv` | 82472 | `eb1e69cc0d30e3c1…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_5.csv` | 82439 | `8b7c960dae4feb2f…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_6.csv` | 82418 | `fa6d2405be868b77…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_7.csv` | 82448 | `42fd6bc6b1447413…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_8.csv` | 82472 | `8f5b2375ebeb4740…` | present |
| split_csv | `models/iucompath-glioma-subtyping/splits/tcga_who_2021_100/splits_9.csv` | 82514 | `df98f1cdd920e716…` | present |
| upstream_readme | `models/iucompath-glioma-subtyping/README.upstream.md` | 13248 | `398b47ae7a7c1300…` | present |

Tam hash değerleri `assets.json` ve kayıt-geneli `assets.lock.json` içindedir.

## Yerel kod ve ortam

- Ortam: n/a (checkpoint yok).

## Hazır olma kapıları

| Kaynak | Lisans | Sürüm | Hash | Ortam | Smoke test | Yerel değerlendirme |
|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | – | – | – |

`ready` yalnız tüm kapılar geçince verilir; bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Kullanım

Etiket CSV'leri MERGEN etiketlerinin çapraz doğrulaması ve split tasarımı için kullanılır.
