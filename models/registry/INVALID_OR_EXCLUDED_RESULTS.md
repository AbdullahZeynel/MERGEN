# Geçersiz veya Rapor Dışı Sonuçlar

Bu dosyadaki sonuçlar **silinmemiştir** — hatanın kaydı olarak saklanıyorlar. Hiçbiri
"nihai performans" olarak gösterilmemelidir. Her biri için neden geçersiz olduğu ve yerine
hangi sayının kullanılacağı aşağıdadır.

---

## 1. Sızıntılı ensemble sonucu — macro-F1 0,923 (KULLANMAYIN)

**Dosya:** `invalid/ensemble_val.INVALID_train_overlap.json`

**Ne oldu.** `cv_train.py --mode kfold` fold'ları **train+val havuzunda** (639 hasta) oluşturuyor.
Dolayısıyla kilitli doğrulama bölmesindeki 115 hastanın **tamamı**, 5 fold modelinden **4'ünün**
eğitim setinde yer alıyor. `ensemble cv_v1 val` komutu bu modelleri o hastalarda değerlendirince
macro-F1 **0,9234** çıktı. Bu sayı ezberi ölçüyor, genellemeyi değil.

**Doğrulama (2026-09-15):**

```
fold0: eğitim 511 hasta, 102'si kilitli val'den
fold1: 93   fold2: 86   fold3: 85   fold4: 94
→ 115 val hastasının 115'i de 5 modelden tam 4'ünün eğitim setinde
→ test bölmesiyle kesişim: 0 (test temiz kaldı)
```

**Yerine kullanılacak sayı:** ürün modelinin kilitli test sonucu **macro-F1 0,790 [0,708–0,863]**
(`mergen-wsi-attention-mil/results/ensemble_cv_v1/eval_test.json`).

**Alınan önlem.** `ensemble_eval.py` artık her checkpoint'in yanındaki `config.json`'dan eğitim
hasta listesini okuyup değerlendirilen bölmeyle kesişimi hesaplıyor ve kesişim varsa çalışmayı
**reddediyor** (`--allow-train-overlap` ile zorlanan sonuç JSON'a `INVALID` damgasıyla yazılır).

---

## 2. Doğrulama skorları — ürün iddiası olarak kullanılamaz

**Dosyalar:** `mergen-wsi-attention-mil/results/*/eval_val.json`

Doğrulama macro-F1 değerleri (0,86–0,89) **en iyi epoch'un kendi doğrulama verisinde seçilmesi**
nedeniyle iyimserdir. Bu şişkinlik eğitim loglarından ölçüldü — en iyi epoch skoru eksi 10. epoch
sonrasının medyanı, 10 koşuda **+0,046 ± 0,014** makro-F1.

Kanıt: `mergen-wsi-attention-mil/training/*/train_log.jsonl`

**Yerine:** out-of-fold havuz **0,827 [0,793–0,857]** (n=639) veya kilitli test **0,790**.

---

## 3. Smoke test Dice değerleri — performans iddiası değildir

**Dosyalar:** `nnunet-brats21/smoke/`, `swin-unetr-brats21/smoke/`, `smoke/`

MSD Task01 üzerinde ölçülen Dice değerleri (nnU-Net TC 0,798 / WT 0,851 / ET 0,754 gibi)
**çalışırlık, süre ve VRAM ölçümleridir**. MSD Task01 BraTS türevidir; kullanılan vakalar bu
modellerin eğitim verisiyle örtüşebilir. Bağımsız performans için UCSF-PDGM sonuçları kullanılmalıdır
(`mergen-uwcse/uwcse_v3/segmentation_metrics.json`).

---

## 4. MRI ortalama Dice — tek başına yanıltıcı

`uwcse_v3` ortalama Dice değerleri doğrudur ama **tek başına verilmemelidir**. Test vakalarının
üçte birinde referansta hiç tümör çekirdeği (68/192) ya da kontrast tutan bölge (72/192) yoktur;
bu vakalarda Dice "ne kadar örtüştün" değil "hiçbir şey öngörmeyebildin mi" sorusunu ölçer.

Ayrıştırılmış tablo `segmentation_metrics.json` içindeki `by_region_presence` bloğundadır ve
raporda ortalamayla **birlikte** verilmelidir.

---

## 5. `uwcse_v1` — ağırlık örneklemi temsili değil

**Dosya:** `mergen-uwcse/uwcse_v1/segmentation_metrics.json`

İlk koşuda ağırlıkların ölçüldüğü 10 vaka rastgele seçildi ve 7'si grade 4 çıktı; kontrast tutmayan
düşük dereceli tümörler ölçüme neredeyse hiç girmedi. Sonuç: TC ağırlığı 0,530 ile nnU-Net'e yaslandı
ve model çekirdeği olmayan 68 vakanın 60'ında var olmayan çekirdek işaretledi.

**Arşivde tutulma sebebi:** düzeltmenin (grade'e orantılı tabakalı ölçüm → `uwcse_v2`/`uwcse_v3`)
ne kazandırdığını göstermek için gereklidir. Raporda "önce/sonra" karşılaştırması olarak kullanılabilir,
**nihai performans olarak kullanılamaz**.

---

## 6. Reddedilen fikir: gömü-tabanlı dağılım-dışılık kapısı

**Kaynak:** `docs/SISTEM_MIMARISI_2026-09-16.md` bölüm 6 (Bilinen sınırlar)

Patoloji tarafında "kendinden emin yanlışlar dağılım dışı slaytlar mı" hipotezi test edildi ve
**çürütüldü**: hataların eğitim dağılımına Mahalanobis uzaklığı doğru vakalardan *daha düşük*
(medyan 4,45 vs 5,05, Mann-Whitney p=0,013) ve en dışarıdaki 20 val slaytının doğruluğu 1,00.
Böyle bir kapı modelin doğru bildiği slaytları işaretlerdi. Rapora "denendi ve reddedildi" olarak
girebilir; bir bileşen olarak sunulamaz.

---

## Kapsam dışı bırakılanlar (geçersiz değil, cutoff sonrası)

Gazi Brains 2020 veri kümesiyle yapılan hiçbir çalışma bu arşivde **yoktur**: benchmark, ön işleme
düzeltmesi, 3B/2B ince ayar ve bunların sonuçları. Bunlar geçersiz değildir — arşivin kapsam
sınırının (cutoff) dışındadır ve canlı depoda durur.
