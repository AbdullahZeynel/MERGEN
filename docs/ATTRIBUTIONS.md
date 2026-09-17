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

Görüntüler insan katılımcılardan gelir. Veri toplama, UCSF kurumsal etik
kurulunca onaylanmış ve onam muafiyeti verilmiştir; koleksiyon kimliksizleştirilmiş
olarak TCIA üzerinden yayımlanır.

Hacimler kafatası çıkarılmış (skull-stripped) biçimdedir. Bunu TCIA değil,
veriyi hazırlayan ekip yapmıştır: eş kayıtlı veri, açık kaynak bir derin öğrenme
aracıyla (<https://github.com/ecalabr/brain_mask>) işlenmiştir ve TCIA bu aracı
"External Resources" altında, kendi barındırmadığı bir kaynak olarak listeler.
Sonucu olarak görüntüden yüz hatları da yeniden oluşturulamaz.

Depoya alınan türev görsellerde kişisel tanımlayıcı bulunmaz. Yukarıdaki
bilgiler koleksiyon sayfasından doğrulanmıştır (son kontrol: 17 Eylül 2026).

### TCGA-GBM / TCGA-LGG — H&E tam slayt görüntüleri (WSI)

Patoloji kolunun eğitim, doğrulama ve test verisi: 762 hastadan birer tanısal H&E
slaytı, GDC üzerinden açık erişimle alındı; A/O/G etiketleri cBioPortal datahub'ın
sabit bir commit'indeki `lgggbm_tcga_pub` çalışmasından türetildi. Kohort manifesti,
split ve kalite eşiği [`models/registry/mergen-wsi-attention-mil/`](../models/registry/mergen-wsi-attention-mil/MODEL_CARD.md)
içindedir. Görüntüler insan katılımcılardan gelir; TCGA verisi kimliksizleştirilmiş
olarak yayımlanır.

- Slaytlar: <https://portal.gdc.cancer.gov/> (files API: <https://api.gdc.cancer.gov/files>)
- Etiketler: <https://github.com/cBioPortal/datahub/tree/04f170590dbd1ac6e49c2d334decb4dbdb4c14b9/public/lgggbm_tcga_pub>

**Etiket şemasının dayanağı**

> Ceccarelli M, Barthel FP, Malta TM, et al. Molecular Profiling Reveals Biologically
> Discrete Subsets and Pathways of Progression in Diffuse Glioma. *Cell*
> 2016;164:550–563. <https://doi.org/10.1016/j.cell.2015.12.028>

### BraTS — eğitim/ön eğitim verisi

Depoya alınan MONAI paketleri BraTS veri kullanım sözleşmesine ve istenen
atıflara bağlıdır; tam metin
[`models/imaging/brats_mri_segmentation/docs/data_license.txt`](../models/imaging/brats_mri_segmentation/docs/data_license.txt)
içindedir.

## Hazır model ağırlıkları

Depoda bulunmaz; kaynak, sürüm ve SHA-256 değerleri
[`models/registry/assets.lock.json`](../models/registry/assets.lock.json) içindedir.

### nnU-Net v2 BraTS21 — 5 fold (BAMF Health, Zenodo)

**CC-BY-4.0, atıf zorunlu.**

> Murugesan GK, Van Oss J, McCrumb D. Pretrained model for 3D semantic image
> segmentation of the brain tumor, necrosis, and edema from MRI scans (v1.0.0).
> Zenodo, 2024. <https://doi.org/10.5281/zenodo.11582627>

> Isensee F, Jaeger PF, Kohl SAA, Petersen J, Maier-Hein KH. nnU-Net: a
> self-configuring method for deep learning-based biomedical image segmentation.
> *Nat Methods* 2021;18:203–211. <https://doi.org/10.1038/s41592-020-01008-z>

> Baid U, et al. The RSNA-ASNR-MICCAI BraTS 2021 Benchmark on Brain Tumor
> Segmentation and Radiogenomic Classification. arXiv:2107.02314 (2021).
> <https://arxiv.org/abs/2107.02314>

### Swin UNETR BraTS21 — fold 0 (MONAI)

Apache-2.0. Kaynak kodu bu depoda `models/imaging/SwinUNETR_BRATS21/` altındadır
(aşağıdaki tablo); ağırlık MONAI-extra-test-data 0.8.1'den alınmıştır.

> Hatamizadeh A, Nath V, Tang Y, Yang D, Roth HR, Xu D. Swin UNETR: Swin
> Transformers for Semantic Segmentation of Brain Tumors in MRI Images. BrainLes
> 2021. <https://arxiv.org/abs/2201.01266>

### DINOv2 ViT-B/14 (Meta AI) — dondurulmuş kare kodlayıcı

Apache-2.0 (ViT-B/14 ağırlığı ve kod). Patolojiye özgü değildir; hiç eğitilmedi,
yalnız özellik çıkarıcı olarak kullanılır.

> Oquab M, Darcet T, Moutakanni T, et al. DINOv2: Learning Robust Visual Features
> without Supervision. *TMLR* 2024. <https://arxiv.org/abs/2304.07193>

### MERGEN Gated Attention-MIL — ekip tarafından eğitildi

Mimari Ilse ve ark. 2018'e dayanır; kod ve ağırlık MERGEN'e aittir.

> Ilse M, Tomczak JM, Welling M. Attention-based Deep Multiple Instance Learning.
> *ICML* 2018, PMLR 80:2127–2136. <https://proceedings.mlr.press/v80/ilse18a.html>

### Ürüne alınmayan referans modeller

TUM Radio-Path MoE/Mamba, GMAP, 1p/19qNET, ROAM (GPL-3.0), MIL_Pretrained,
IUCompPath, Prov-GigaPath ve UNI kayıt defterinde referans olarak tutulur. Bir kısmının
deposunda açık yazılım lisansı yoktur, bir kısmı erişim onaylı encoder ister; yazılı
izin ve erişim netleşmeden ürün paketine alınmazlar. Ayrıntı ve kaynaklı metrikler
[`models/registry/README.md`](../models/registry/README.md).

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
