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
| CGGA gen frekans tablosu (türetilmiş) | `models/VeriOdakliCozum/modeller/cgga_gen_frekans.v1.json` |
| ESM-2 | `facebook/esm2_t30_150M_UR50D`; Hugging Face cache veya yapılandırılmış model yolu |
| Takım logosu kaynağı | `~/Assets/Sosyal Medya PP 3 (2).png` (Git dışı; türevleri `frontend/public/` içinde izlenir) |

ESM varsayılan cache'i kullanıcı dizinindeki `.cache/huggingface/hub/` altındadır; `HF_HOME` / `HF_HUB_CACHE` gibi ayarlar farklı bir yere yönlendirebilir. Cache'i repoya kopyalamayın.

Çıkarım adaptörü ağırlığı yalnız yerelden yükler ve şu sırayla arar:
`MERGEN_ESM_YEREL_YOL` (doğrudan snapshot dizini) → `MERGEN_ESM_CACHE_DIZINI`
→ `HF_HUB_CACHE` / `HF_HOME` → `~/.cache/huggingface/hub`. Bulamazsa açık hata
verir; indirme yalnızca hazırlık adımında `MERGEN_ESM_INDIRME_IZNI=1` ile
yapılır. Genomik model ve veri dizinleri de taşınabilir:
`MERGEN_GENOMIK_MODEL_DIZINI`, `MERGEN_GENOMIK_VERI_DIZINI`,
`MERGEN_GENOMIK_SONUC_DIZINI`. Değişken verilmezse yollar eskisi gibi paket
içindedir.

CGGA frekans tablosu `python -m VeriOdakliCozum.semayi_uret --cgga` ile yerel
CGGA WESeq_286 dosyasından üretilir; kaynağın sha256'sı ve örneklem sayısı
tablonun içinde tutulur. Tablo Git dışıdır, ona ait sağlama toplamı ise Git'te
izlenen `models/VeriOdakliCozum/semalar/ozellik_semasi.v1.json` dosyasında
kayıtlıdır. Çıkarım adaptörü tablo yoksa sıfır frekans varsaymaz, hata verir.

Arayüzdeki `frontend/public/ergenekon-logo.png` ve `frontend/public/favicon.png`
dosyaları kaynak logodan türetilmiştir; kaynak siyah zemin üzerine beyaz kartaldır
ve alfa kanalı yoktur. Türetme `python frontend/scripts/prepare_logo.py "<kaynak>"`
ile tekrarlanır: parlaklık kanalı alfaya taşınır, RGB beyaza sabitlenir. Kaynak
dosya repoya kopyalanmaz.

Yeni makinede bu dosyalar ayrıca sağlanmalı. Kaynak URL'si, lisans, sürüm ve hash doğrulandıktan sonra varlık manifestine kaydedilmeli; eksik bilgi uydurulmamalı. Model servisi paketlenirken bu manifest tamamlanacak.

Veri hazırlama betiğindeki `--duplicate-missing` yalnızca sahte modaliteli duman testidir; ürettiği sonuçlar gerçek demo veya performans kanıtı olarak kullanılmaz. Bu hazırlıkta çalıştırılmadı.
