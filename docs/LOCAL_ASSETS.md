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

ESM varsayılan cache'i kullanıcı dizinindeki `.cache/huggingface/hub/` altındadır; `HF_HOME` / `HF_HUB_CACHE` gibi ayarlar farklı bir yere yönlendirebilir. Cache'i repoya kopyalamayın.

Yeni makinede bu dosyalar ayrıca sağlanmalı. Kaynak URL'si, lisans, sürüm ve hash doğrulandıktan sonra varlık manifestine kaydedilmeli; eksik bilgi uydurulmamalı. Model servisi paketlenirken bu manifest tamamlanacak.

Veri hazırlama betiğindeki `--duplicate-missing` yalnızca sahte modaliteli duman testidir; ürettiği sonuçlar gerçek demo veya performans kanıtı olarak kullanılmaz. Bu hazırlıkta çalıştırılmadı.
