# Git dışındaki yerel dosyalar

Dosyanın Git'te olmaması makinede olmadığı anlamına gelmez. İddiada bulunmadan önce aşağıdaki yolu, yapılandırmayı ve varsa model önbelleğini kontrol edin.

| İçerik | Repo köküne göre konum |
|---|---|
| MR veri seti / metadata | `models/imaging/UCSF-PDGM/`, `models/imaging/UCSF-PDGM-metadata.csv` |
| Hazırlanmış MR girdisi | `models/imaging/example_dataset/` |
| nnU-Net | `models/imaging/nnUNet_data/nnUNet_results/Dataset002_BRATS19/nnUNetTrainer__nnUNetPlans__3d_fullres/fold_0/checkpoint_final.pth` |
| Swin UNETR | `models/imaging/SwinUNETR_BRATS21/pretrained_models/fold0_f48_ep300_4gpu_dice0_8854/model.pt` |
| Görüntü demo / değerlendirme | `models/imaging/results/`, `models/imaging/results_eval/` |
| Kanıt arşivi (17 Eylül 2026): figürler, PDF rapor, 12 WSI + 5 MRI örnek vaka klasörü, eski genomik kaynak kodu | `.local/evidence-2026-09-17/` — metin/JSON kısmı depoda `models/registry/` |
| GPU hostu veri kökü (ağırlıklar, TCGA WSI kohortu, embedding'ler, koşular) | `<MERGEN_DATA_ROOT>` = hostta `~/mergen-data`; yerleşim [`models/registry/LOCAL_ASSETS_HOST.md`](../models/registry/LOCAL_ASSETS_HOST.md), hash'ler `models/registry/assets.lock.json` |
| Takım logosu kaynağı | `~/Assets/Sosyal Medya PP 3 (2).png` (Git dışı; türevleri `frontend/public/` içinde izlenir) |

Arayüzdeki `frontend/public/ergenekon-logo.png` ve `frontend/public/favicon.png`
dosyaları kaynak logodan türetilmiştir; kaynak siyah zemin üzerine beyaz kartaldır
ve alfa kanalı yoktur. Türetme `python frontend/scripts/prepare_logo.py "<kaynak>"`
ile tekrarlanır: parlaklık kanalı alfaya taşınır, RGB beyaza sabitlenir. Kaynak
dosya repoya kopyalanmaz.

Yeni makinede bu dosyalar ayrıca sağlanmalı. Kaynak URL'si, lisans, sürüm ve hash doğrulandıktan sonra varlık manifestine kaydedilmeli; eksik bilgi uydurulmamalı. Model servisi paketlenirken bu manifest tamamlanacak.

Veri hazırlama betiğindeki `--duplicate-missing` yalnızca sahte modaliteli duman testidir; ürettiği sonuçlar gerçek demo veya performans kanıtı olarak kullanılmaz. Bu hazırlıkta çalıştırılmadı.
