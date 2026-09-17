# Git dışındaki yerel dosyalar

Dosyanın Git'te olmaması makinede olmadığı anlamına gelmez. İddiada bulunmadan önce aşağıdaki yolu, yapılandırmayı ve varsa model önbelleğini kontrol edin.

| İçerik | Repo köküne göre konum |
|---|---|
| MR veri seti / metadata | `models/imaging/UCSF-PDGM/`, `models/imaging/UCSF-PDGM-metadata.csv` |
| Hazırlanmış MR girdisi | `models/imaging/example_dataset/` |
| nnU-Net | `models/imaging/nnUNet_data/nnUNet_results/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_0/checkpoint_final.pth` |
| Swin UNETR | `models/imaging/SwinUNETR_BRATS21/pretrained_models/fold0_f48_ep300_4gpu_dice0_8854/model.pt` |
| Genomik XGBoost | `models/VeriOdakliCozum/modeller/mergen_xgb.json` veya `.joblib` |
| Genomik veriler / özellik matrisi | `models/VeriOdakliCozum/veri/` |
| Görüntü demo / değerlendirme | `models/imaging/results/`, `models/imaging/results_eval/` |
| Genomik sonuçlar | `models/VeriOdakliCozum/sonuclar/` |
| ESM-2 | `facebook/esm2_t30_150M_UR50D`; Hugging Face cache veya yapılandırılmış model yolu |
| TCGA glioma WSI | `<MERGEN_DATA_ROOT>/pathology/datasets/tcga_glioma/raw/full/` |
| WSI indirme durumu/manifestleri | `<MERGEN_DATA_ROOT>/pathology/state/full_download.json`, `<MERGEN_DATA_ROOT>/pathology/datasets/tcga_glioma/manifests/` |
| DINOv2 ViT-B/14 | `<MERGEN_DATA_ROOT>/models/dinov2-vitb14/dinov2_vitb14_pretrain.pth` (aynı dosya `pathology/weights/` altında hard-link) |
| nnU-Net BraTS21 (5 fold) | `<MERGEN_DATA_ROOT>/models/nnunet-brats21/weights/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_*/checkpoint_final.pth` |
| Swin UNETR BraTS21 fold-0 | `<MERGEN_DATA_ROOT>/models/swin-unetr-brats21/weights/fold0_f48_ep300_4gpu_dice0_8854/model.pt` |
| MONAI SegResNet BraTS18 bundle | `<MERGEN_DATA_ROOT>/models/monai-segresnet-brats18/models/model.pt` |
| TUM Radio-Path MoE checkpointleri + meta veri | `<MERGEN_DATA_ROOT>/models/tum-radio-path-moe-mamba/{ckpt,metadata}/` |
| GMAP checkpointleri + etiket listesi | `<MERGEN_DATA_ROOT>/models/gmap/{weights/GMAP,label}/` |
| ROAM checkpointleri | `<MERGEN_DATA_ROOT>/models/roam/checkpoints/ROAM_split{0..4}.pth` |
| 1p/19qNET, MIL_Pretrained, IUCompPath etiketleri, AttentionDeepMIL | `<MERGEN_DATA_ROOT>/models/{1p19qnet,mil-pretrained,iucompath-glioma-subtyping,attention-deep-mil}/` |
| PyTorch sanal ortamı (Python 3.14, torch 2.14.0+cu130) | `<MERGEN_DATA_ROOT>/envs/mergen-py314/` |

ESM varsayılan cache'i kullanıcı dizinindeki `.cache/huggingface/hub/` altındadır; `HF_HOME` / `HF_HUB_CACHE` gibi ayarlar farklı bir yere yönlendirebilir. Cache'i repoya kopyalamayın.

Yeni makinede bu dosyalar ayrıca sağlanmalı. Kaynak URL'si, lisans, sürüm ve hash doğrulandıktan sonra varlık manifestine kaydedilmeli; eksik bilgi uydurulmamalı. Model servisi paketlenirken bu manifest tamamlanacak.

Görüntü kodu önce `MERGEN_NNUNET_RESULTS` / `MERGEN_SWIN_MODEL_PATH`, ardından
`MERGEN_DATA_ROOT` değerini okur. Hiçbiri verilmezse varsayılan büyük-varlık kökü
`~/mergen-data` olur; yalnız orada varlık yoksa eski repo-içi yol kullanılır. `.env`
otomatik yüklenmez.

2026-09-14 yerel auditinde WSI indirmesi 762/762 dosya ve 616,530 GiB olarak
tamamlanmıştır. Aynı gün nnU-Net (5 fold), Swin UNETR (fold-0), MONAI SegResNet,
DINOv2, TUM MoE, GMAP, ROAM, 1p/19qNET ve MIL_Pretrained ağırlıkları veri köküne
indirilip SHA-256 ile kaydedilmiş ve torch ile yüklenmiştir (96 dosya, 3,47 GiB);
ayrıntı [`models/registry/SUMMARY.md`](SUMMARY.md). MRI örnek
verileri (UCSF-PDGM), ESM-2 cache'i, XGBoost ağırlığı ve yerel değerlendirme
sonuçları hâlâ yoktur. Güncel hash ve kaynak kayıtları
[`models/registry/assets.lock.json`](assets.lock.json) ve
[`assets.yaml`](assets.yaml) içindedir; `verify_assets.py` ile
doğrulanır. Bir yolun tabloda yazılması, dosyanın çalışır olduğu anlamına gelmez;
model bazlı çalışma ortamları ve smoke inference henüz yapılmamıştır. Repo-içi eski
yollar (`models/imaging/nnUNet_data/...`, `pretrained_models/...`) yalnız geriye dönük
uyumluluk içindir.

Veri hazırlama betiğindeki `--duplicate-missing` yalnızca sahte modaliteli duman testidir; ürettiği sonuçlar gerçek demo veya performans kanıtı olarak kullanılmaz. Bu hazırlıkta çalıştırılmadı.
