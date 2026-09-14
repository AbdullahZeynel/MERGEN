# Kaynaklar ve atıflar

Bu depo kendi kodunu [Apache-2.0](../LICENSE) ile yayımlar. Kullandığı veri
kümeleri, model ağırlıkları ve depoya alınmış üçüncü taraf kaynak kodu kendi
şartlarına tabidir. Aşağıdaki liste, hangi çıktının hangi kaynaktan türediğini
ve o kaynağın istediği atfı kaydeder.

## Veri kümeleri

### UCSF-PDGM — MR görüntüleri

README'deki `docs/images/arayuz-goruntuleme.png`,
`docs/images/2d-kesit-koronal.png` ve `docs/images/3d-segmentasyon.gif`
dosyaları ile hazır demo paketindeki bütün MR kesitleri, segmentasyon
katmanları ve 3D yüzeyler bu koleksiyondan türetilmiştir. Koleksiyon
**CC BY 4.0** ile yayımlanır ve atıf ister.

**Veri atfı**

> Calabrese, E., Villanueva-Meyer, J., Rudie, J., Rauschecker, A., Baid, U.,
> Bakas, S., Cha, S., Mongan, J., Hess, C. (2022). The University of
> California San Francisco Preoperative Diffuse Glioma MRI (UCSF-PDGM)
> (Version 5) [dataset]. The Cancer Imaging Archive.
> <https://doi.org/10.7937/tcia.bdgf-8v37>

**Yayın atfı**

> Evan Calabrese, Javier E. Villanueva-Meyer, Jeffrey D. Rudie, Andreas M.
> Rauschecker, Ujjwal Baid, Spyridon Bakas, Soonmee Cha, John T. Mongan,
> Christopher P. Hess. (2022) *The UCSF Preoperative Diffuse Glioma MRI
> (UCSF-PDGM) Dataset*. Radiology: Artificial Intelligence.
> <https://doi.org/10.1148/ryai.220058>

Koleksiyon kaydı: <https://www.cancerimagingarchive.net/collection/ucsf-pdgm/>

Görüntüler insan katılımcılardan gelir; TCIA tarafından kimliksizleştirilmiş
ve kafatası çıkarılmış (skull-stripped) biçimde yayımlanır. Depoya alınan
türev görsellerde kişisel tanımlayıcı bulunmaz.

### BraTS — eğitim/ön eğitim verisi

Depoya alınan MONAI paketleri BraTS veri kullanım sözleşmesine ve istenen
atıflara bağlıdır; tam metin
[`models/imaging/brats_mri_segmentation/docs/data_license.txt`](../models/imaging/brats_mri_segmentation/docs/data_license.txt)
içindedir.

## Depoya alınmış üçüncü taraf kaynak kodu

Bu dosyalar kendi lisans bildirimleriyle birlikte dağıtılır; kök
`LICENSE` onların yerine geçmez.

| Yol | Kaynak | Lisans |
|---|---|---|
| `models/imaging/SwinUNETR_BRATS21/` | MONAI Consortium — Swin UNETR BraTS21 referans uygulaması | Apache-2.0 (dosya başlıklarında) |
| `models/imaging/brats_mri_segmentation/` | MONAI model paketi | Apache-2.0 ([`LICENSE`](../models/imaging/brats_mri_segmentation/LICENSE)) |

## Bağımlılık olarak kullanılan bileşenler

Depoda kaynağı bulunmaz; kendi dağıtım kanallarından alınır.

| Bileşen | Şart |
|---|---|
| nnU-Net (MIC-DKFZ) | Apache-2.0 |
| MONAI | Apache-2.0 |
| React, Three.js, TanStack Query, Zod | MIT |
| FastAPI, uvicorn, httpx | MIT / BSD-3-Clause |

Bu tablo bilgilendirme amaçlıdır. Bir bileşeni yeniden dağıtmadan önce
kendi lisans dosyasını kaynağından doğrulayın.
