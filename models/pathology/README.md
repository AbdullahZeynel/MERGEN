> **Depodaki yeri.** Bu dizin, GPU hostundaki `models/pathology/mil/` eğitim hattının
> 17 Eylül 2026 anlık görüntüsüdür; kodun kendisi buradadır, aşağıdaki anlatım hostun
> çalışma düzenini tarif eder. Burada **olmayanlar:** `run_training.sh` sarmalayıcısı
> (komutlar doğrudan `python <betik>` ile çalışır), DINOv2 kaynak kodu ve ağırlığı
> (`<MERGEN_DATA_ROOT>/models/dinov2-vitb14/`), TCGA kohortu, embedding'ler ve koşu
> çıktıları (`<MERGEN_DATA_ROOT>/pathology/`). Kilitli split ve sonuçlar depoda
> [`models/registry/mergen-wsi-attention-mil/`](../registry/mergen-wsi-attention-mil/MODEL_CARD.md)
> altındadır. Bağımlılıklar: [`requirements.txt`](requirements.txt). Canlı çıkarım
> sözleşmesi `infer_slide.py`'dır; executor'a bağlanması M6 sprintinin işidir.

# MERGEN WSI Attention-MIL eğitim hattı

H&E slaytından A/O/G olasılığı ve dikkat ısı haritası üreten, MERGEN tarafından eğitilen
tek model. Encoder (DINOv2 ViT-B/14) dondurulmuştur; yalnız gated Attention-MIL başlığı
(263.556 parametre) eğitilir.

## Ürün modeli (donduruldu, 2026-09-15)

**`cv_v1` 5-fold ensemble** — beş fold checkpoint'inin olasılık ortalaması. Kilitli testte
(n=113, hiçbir fold modeli görmedi): **makro-F1 0,790 [0,708–0,863]**, dengeli doğruluk 0,788,
doğruluk 0,805, AUROC 0,909, MCC 0,696. Tek model `mil_v1` aynı testte 0,770 [0,679–0,847] almıştı;
test bölmesi bu iki bakışla kapandı ve sonuçlar daima birlikte raporlanır.

Mimarinin genelleme tahmini için en güvenilir sayı 5-fold out-of-fold havuzudur (n=639):
**0,827 [0,793–0,857]**. Doğrulama skorları (0,86–0,89) en iyi epoch'un kendi doğrulama verisinde
seçilmesinden dolayı ortalama **+0,046** şişkindir; ürün iddiası olarak kullanılmaz.

Çıkarım: `./run_training.sh infer <slayt.svs>` (varsayılan koşu artık `cv_v1`). Slayt başına
~19 s, 1,1 GiB VRAM. Kalibrasyon `runs/cv_v1/calibration.json`: sıcaklık **T = 1** (ensemble
zaten kalibre — val ECE 0,071; sıcaklık ölçekleme ECE'yi kötüleştiriyordu), çekimserlik eşiği
ham top-2 farkı < **0,45** (val'de seçildi). Testteki davranışı: vakaların %80,5'i yanıtlanır,
tutulanlarda doğruluk 0,835 (genel 0,805), 22 hatanın 7'si yakalanır. **Bu bayrak bir güvenlik
ağı değil, sıralama yardımıdır** (hata-tespit AUROC 0,745 [0,69–0,80], OOF n=639'da ölçüldü).

```text
cohort.tsv (762 hasta)
   │  make_split.py            → splits_v1.json (train 532 / val 115 / test 115, kilitli)
   ▼
extract_embeddings.py        → features/<hasta>.npz  (≤8192 tile × 768, fp16; resumable)
   ▼
train.py                     → runs/<ad>/{last,best,epoch_XXX,interrupt}.pt + train_log.jsonl + status.json
   ▼
evaluate.py                  → eval_val.json / eval_test.json (+ bootstrap GA, karışıklık matrisi)
infer_slide.py               → tek slayt: olasılıklar + attention heatmap (ürün sözleşmesi)
```

## Veri dağılımına dair kararlar

| Konu | Karar | Neden |
|---|---|---|
| Split birimi | Hasta (= slayt; hasta başına 1 tanısal slayt) | Aynı hastanın tile'ları farklı bölmelere düşmez |
| Stratifikasyon | sınıf × grade (A/O/G × G2/G3/G4/NA) | TCGA'da G neredeyse hep grade 4; aksi halde model "grade" öğrenir |
| Oranlar | 70 / 15 / 15, tohum 20260914 | Test bölmesi kilitli; eşik/hyperparametre seçimi yalnız val'de |
| Merkezler | 32 merkez train'de; test'te train'de görülmeyen tek merkez (Asterand, küçük) | Merkez etkisi raporlanır; merkez-dışı test için `--holdout-sites` seçeneği var |
| Sınıf dengesizliği (345 / 255 / 162) | Sınıf ağırlıklı cross-entropy (ters frekans) | O sınıfı az; ağırlık makro-F1'i korur |
| Çözünürlük | Tüm slaytlar 0,5 µm/px'e (20×) normalize; 40× slaytlarda 448 px okunup 224'e küçültülür | 20×/40× karışık tarama |
| Tile sayısı | Doku tile'larından slayt başına ≤ 8192 (uniform rastgele, hasta tohumlu); eğitimde her epoch 4096'lık yeni alt küme | Bellek + veri artırma; değerlendirmede tüm saklanan tile'lar |
| Doku eşiği | HSV doygunluk maskesi, tile alanının ≥ %60'ı doku | Boş cam ve kalem izi büyük ölçüde dışarıda kalır |
| Sızıntı kontrolü | Bölmeler ayrık ve tam kapsayıcı (`report.leakage_check`) | make_split.py her koşuda doğrular |
| Erken durdurma | val makro-F1, 15 epoch sabır; en iyi checkpoint `best.pt` | Overfit'i sınırlar |

Bilinen sınır: TCGA tek kaynak. Genelleme iddiası için EBRAINS/IPD gibi dış veri gerekir.

## Komutlar (kullanıcı terminalinden)

```bash
cd models/pathology
./run_training.sh preflight          # ~10–15 dk: ortam, 6 slayt embedding, 2+2 epoch eğitim, kesinti+resume testi, tek slayt çıkarım
./run_training.sh extract            # tüm kohort; Ctrl+C güvenli, tekrar çalıştırınca kaldığı yerden devam eder
./run_training.sh extract-status     # ilerleme ve ETA
./run_training.sh train mil_v1       # checkpoint'li eğitim; aynı komut kesilen eğitimi devam ettirir
./run_training.sh status mil_v1
./run_training.sh eval mil_v1 val    # test'i bir kez, en son çalıştırın
./run_training.sh infer /yol/slayt.svs mil_v1
```

Ortam değişkenleri: `WORKERS` (varsayılan 6), `MAX_TILES` (8192), `EPOCHS` (100),
`BAG_SIZE` (4096), `PATIENCE` (15), `MERGEN_DATA_ROOT` (~/mergen-data).

## Varyans, kalibrasyon ve inceleme (mil_v1 sonrası)

Test bölmesi mil_v1 için bir kez açıldı; aşağıdaki komutların hiçbiri test'e dokunmaz
(yalnız `ensemble ... test` açık onayla dokunur). Eğitim dakikalar sürdüğü için hepsi
aynı akşam çalıştırılabilir.

| Komut | Ne yapar | Süre |
|---|---|---:|
| `./run_training.sh seeds` | Kilitli train/val ile 5 tohum; val makro-F1 ort. ± std ve tohum-ensemble skoru (`runs/seeds_v1/cv_summary.json`) | ~15 dk |
| `./run_training.sh cv` | Train+val havuzunda (647 hasta − QC) sınıf×grade stratifiye 5-fold; her hasta bir kez out-of-fold tahmin edilir; fold ort. ± std ve OOF metrikleri + GA (`runs/cv_v1/cv_summary.json`, `oof_predictions_seed1.csv`) | ~15 dk |
| `./run_training.sh calibrate mil_v1` | Val tahminlerinden sıcaklık (T) ve çekimserlik eşiği; ECE/Brier önce-sonra; `runs/mil_v1/calibration.json`. `infer` bunu otomatik kullanır | saniyeler |
| `./run_training.sh heatmaps mil_v1 val` | 3 doğru + 3 yanlış vakanın attention haritası ve en yüksek attention'lı 12 kare; `runs/mil_v1/heatmaps/review_sheet.png` | ~2 dk |
| `./run_training.sh ensemble seeds_v1 val` | Tohum modellerinin ortalama olasılığı (bunlar yalnız train'de eğitildi, val temiz) | ~1 dk |
| `./run_training.sh ensemble cv_v1 test` | **Yalnız nihai model için, bir kez.** Fold modelleri train+val havuzunda eğitildiği için val'de sızıntı olur; betik `val` isteğini reddeder. `test` için `--confirm-final` bayrağını kendisi ekler | ~1 dk |

Kesilen `seeds`/`cv` koşuları aynı komutla kaldığı yerden devam eder (biten fold'lar atlanır).

`ensemble_eval.py` her checkpoint'in yanındaki `config.json`'dan eğitim hasta listesini okur ve
değerlendirilen bölmeyle kesişim varsa çalışmayı reddeder (`--allow-train-overlap` ile zorlanan
sonuç JSON'a `INVALID` damgasıyla yazılır). 2026-09-15'te `ensemble cv_v1 val` tam da bu yüzden
şişkin bir skor (0,923) üretmişti; o çıktı `ensemble_val.INVALID_train_overlap.json` olarak
karantinaya alındı.

## Checkpoint ve devam

- Her epoch `last.pt`; en iyi val makro-F1'de `best.pt`; her 5 epoch `epoch_XXX.pt`.
- Ctrl+C veya SIGTERM: mevcut adım biter, `interrupt.pt` yazılır, çıkış kodu 130.
- `--resume auto` önce `interrupt.pt`, yoksa `last.pt` dosyasını yükler: model, optimizer,
  scheduler, RNG durumları, epoch, en iyi skor ve erken-durdurma sayacı geri gelir.
- Checkpoint içindeki kimlik (split hash, features dizini, model yapılandırması, bag
  boyutu, tohum) mevcut ayarlarla uyuşmazsa devam **reddedilir**.
- Embedding çıkarımı slayt bazında atomiktir: `.tmp` yazılır, sonra yeniden adlandırılır;
  yarım dosya kalmaz, tamamlanan slaytlar atlanır.

## İzleme

Terminalde tqdm çubukları ve her epoch bir özet satırı görünür. Aynı bilgiler dosyada:
`runs/<ad>/status.json` (anlık), `runs/<ad>/train_log.jsonl` (epoch başına),
`features/.../status.json` (çıkarım ETA'sı). Claude, kullanıcının açık terminalini
okuyabildiği için aynı çıktıyı takip edebilir.
