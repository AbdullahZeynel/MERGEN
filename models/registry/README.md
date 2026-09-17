# Model kayıt defteri

Sistemin kullandığı ve aday olarak incelediği her model bileşeninin **kökeni,
lisansı, eğitim verisi dağılımı, yayımlanmış metrikleri, yerel varlık hash'leri ve
MERGEN'in kendi ölçümleri** burada, bileşen başına bir dizinde durur. Bu dizin
17 Eylül 2026'da GPU hostundan gelen dondurulmuş kanıt arşivinden alınmıştır;
arşivin kendi anlatımı ve dosya eşlemesi [`ARCHIVE.md`](ARCHIVE.md) içindedir.

Ağırlıklar, veri kümeleri, embedding'ler ve koşu çıktıları Git'te değildir. Kartlar
onları `<MERGEN_DATA_ROOT>` yer tutucusuyla anar; hosttaki gerçek yerleşim
[`LOCAL_ASSETS_HOST.md`](LOCAL_ASSETS_HOST.md), depo tarafındaki konumlar
[`docs/LOCAL_ASSETS.md`](../../docs/LOCAL_ASSETS.md) içindedir.

## Ürün seti

Doktor ekranı yalnız bu bileşenlerin çıktısını gösterir
([`docs/MODEL_INTEGRATION_PLAN.md`](../../docs/MODEL_INTEGRATION_PLAN.md)):

| Kol | Bileşen | Köken | Lisans | Durum |
|---|---|---|---|---|
| MRI | [`nnunet-brats21`](nnunet-brats21/MODEL_CARD.md) — birincil segmentasyon uzmanı, 5 fold | BAMF Health, Zenodo 11582627 | CC-BY-4.0 (atıf zorunlu) | `smoke_tested` |
| MRI | [`swin-unetr-brats21`](swin-unetr-brats21/MODEL_CARD.md) — ikincil uzman, fold 0 | MONAI | Apache-2.0 | `smoke_tested` |
| MRI | [`mergen-uwcse`](mergen-uwcse/MODEL_CARD.md) — iki uzmanı birleştiren **kural** (ağ değil): TC 0,425 / WT 0,697 / ET 0,447, `TC_MIN=250`, `review_flags` | MERGEN | proje lisansı | `coefficients_fitted_evaluated` |
| WSI | [`dinov2-vitb14`](dinov2-vitb14/MODEL_CARD.md) — dondurulmuş kare kodlayıcı | Meta AI | Apache-2.0 | `smoke_tested` |
| WSI | [`mergen-wsi-attention-mil`](mergen-wsi-attention-mil/MODEL_CARD.md) — A/O/G sınıflandırıcı, 5-fold ensemble, **MERGEN tarafından eğitildi** | MERGEN | proje lisansı | `trained_evaluated` |

Harici ağırlıklar ekip tarafından eğitilmiş gibi gösterilmez; arayüz ürün markası
olarak MERGEN adını kullanabilir, köken kartlarda ve
[`docs/ATTRIBUTIONS.md`](../../docs/ATTRIBUTIONS.md) içinde doğru yazılır.

## Ürüne girmeyenler

Kayıtları tutulur, doktor ekranına ve dağıtım paketine **alınmaz**:

| Bileşen | Neden |
|---|---|
| [`tum-radio-path-moe-mamba`](tum-radio-path-moe-mamba/MODEL_CARD.md) | Depoda lisans yok; Prov-GigaPath erişimi ister. Koşullu aday. |
| [`gmap`](gmap/MODEL_CARD.md) | Depoda lisans yok; UNI erişimi ister. Yerel TCGA kohortu bu model için bağımsız test **değildir**. |
| [`1p19qnet`](1p19qnet/MODEL_CARD.md), [`mil-pretrained`](mil-pretrained/MODEL_CARD.md) | Depoda lisans yok. |
| [`roam`](roam/MODEL_CARD.md) | GPL-3.0; eski yığın. Referans. |
| [`iucompath-glioma-subtyping`](iucompath-glioma-subtyping/MODEL_CARD.md) | Checkpoint yayımlanmamış; çevrimdışı karşılaştırma. |
| [`prov-gigapath`](prov-gigapath/MODEL_CARD.md), [`uni`](uni/MODEL_CARD.md) | Erişim onaylı encoder'lar; indirilmedi. |
| [`attention-deep-mil`](attention-deep-mil/MODEL_CARD.md) | Mimari referansı (MIT), ağırlık yok. |
| [`legacy-esm2-xgboost`](legacy-esm2-xgboost/MODEL_CARD.md) | Genomik prototip; çekirdek kapsam dışı, PR #28 ile depodan kaldırıldı. |
| [`doctor-rag`](doctor-rag/MODEL_CARD.md) | Ertelendi; model ve korpus seçilmedi. |

## Sayılar nasıl okunur

Rapora giren her sayının kaynak dosyası [`RESULTS_SUMMARY.md`](RESULTS_SUMMARY.md)
içindedir; sonuç türü sözlüğü (`locked test`, `5-fold CV`, `validation`, `smoke
test`, `upstream`) hangi sayının iddia olarak kullanılabileceğini söyler.
Kullanılmaması gereken sonuçlar silinmedi, işaretlendi:
[`INVALID_OR_EXCLUDED_RESULTS.md`](INVALID_OR_EXCLUDED_RESULTS.md). Özellikle:

- doğrulama skorları en iyi epoch seçiminden ötürü **+0,046** şişkindir;
- MRI ortalama Dice tek başına verilmez, `by_region_presence` ile birlikte verilir;
- smoke Dice'ları performans iddiası değildir.

## Dizin düzeni

```text
models/registry/
├── README.md                         bu dosya
├── ARCHIVE.md                        arşivin kök anlatımı + dosya eşlemesi
├── RESULTS_SUMMARY.md                kaynaklı sayı tablosu
├── INVALID_OR_EXCLUDED_RESULTS.md    kullanılmayacak sonuçlar ve nedenleri
├── SUMMARY.md                        2026-09-14 envanter raporu (tarihli)
├── index.yaml                        bileşen listesi, durumlar, durum sözlüğü
├── assets.lock.json / assets.yaml    veri kökündeki dosyaların yol/bayt/SHA-256/kaynak kaydı
├── LOCAL_ASSETS_HOST.md              hostta ne nerede
├── _evidence/                        kohort çakışma analizi
├── report/                           REPORT.md, MODEL_GUIDE.md, figures/
├── smoke/                            MSD/1p19q çalışırlık koşuları
├── invalid/                          karantinaya alınmış sonuç
└── <model-id>/
    ├── MODEL_CARD.md                 üretilmiş kart
    ├── assets.json                   yerel dosyalar + SHA-256
    ├── data_distribution.json        eğitim/doğrulama/test kohortları
    ├── metrics.json                  upstream (kaynaklı) + mergen_reproduced
    ├── local_verification.json       hash / torch-load kontrolü
    ├── smoke/                        yerel çalıştırma (varsa)
    ├── training/                     eğitim logları (MERGEN bileşenleri)
    └── results/                      değerlendirme çıktıları (MERGEN bileşenleri)
```

## Durum sözlüğü

`index.yaml` içindeki `status_legend` bağlayıcıdır; kısaca:

| Durum | Anlamı |
|---|---|
| `trained_evaluated` | MERGEN eğitti; doğrulama ve kilitli test bölmelerinde ölçüldü |
| `coefficients_fitted_evaluated` | Öğrenilen ağırlığı olmayan kural; katsayılar ayrı doğrulamada sabitlendi, bağımsız vakalarda ölçüldü |
| `smoke_tested` | Ağırlık doğrulandı ve gerçek girdiyle uçtan uca çalıştırıldı; bağımsız klinik değerlendirme değildir |
| `weights_verified` | İndirildi, boyut ve SHA-256 kaydedildi; ortam/smoke/değerlendirme ayrı kapılar |
| `weights_verified_dependencies_gated` / `_license_unclear` | Doğrulandı ama erişim onaylı bağımlılık ister ya da lisans belirsiz |
| `gated_access_required` · `metadata_only` · `code_reference` · `deferred` | İndirilmedi · yalnız meta veri · ağırlıksız kod · kapsam dışı |

Hazır olma kuralı: kaynak + lisans + sürüm + hash + ortam + smoke test + yerel
değerlendirme. Bir ağırlığın diskte bulunması tek başına hazır anlamına gelmez.

## Bu depoda **olmayanlar**

- Kartları üreten ve hash'leri doğrulayan betikler (`build_registry.py`,
  `verify_assets.py`, smoke betikleri) GPU hostundaki çalışma kopyasındadır; buradaki
  kartlar **dondurulmuş anlık görüntüdür**, elle düzenlenmez, hostta yeniden üretilir.
- Figürler, PDF rapor, örnek vaka klasörleri ve eski genomik kaynak kodu:
  `<EVIDENCE_ROOT>` (`.local/evidence-2026-09-17/`, Git dışı).
- Çalışan çıkarım/eğitim kodu: MRI için `models/imaging/`, patoloji için
  `models/pathology/` (M2 sprinti).
