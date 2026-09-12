# Genomik model denetim kaydı (S3)

[`SYSTEM_SPRINTS.md`](SYSTEM_SPRINTS.md) S3'ün başlama koşulu altı maddelik bir
denetimdir. Bu belge o denetimin sonucunu, hangi kontrolün gerçekten
çalıştırıldığını ve arayüzde ne söylenebileceğini kaydeder. Ölçümler
geliştirme makinesindeki Git dışı `models/VeriOdakliCozum/veri/` ve
`modeller/` dosyaları üzerinde yapıldı.

Denetlenen eğitim çıktısı: `ozellik_matrisi.csv`,
sha256 `c7616ea36f5abfb11d4f1567e2ff6c5abb4297bd35525649f59f192e2e7a7684`,
1151 satır, 207 gen, 827 patojenik / 324 benign, 15 özellik.
Model: `mergen_xgb.json`, sha256 `6e5d99f1…c785`.

## Altı maddelik denetim

| # | Madde | Durum |
|---|---|---|
| 1 | XGBoost dosyasının açılması, özellik adları/sırası, kütüphane sürümü | **Geçti** — `mergen_xgb.json` XGBoost 3.4.1 ile açıldı; dosya kendi içinde `version: [3,4,1]` bildiriyor. Modelin taşıdığı 15 özellik adı şemayla ve eğitim matrisinin kolon sırasıyla birebir aynı. Şemada `featureNamesVerifiedFromModel: true`, `traceColumnsVerifiedFromTrainingModule: true`. |
| 2 | ESM-2 ağırlıklarının çevrimdışı yüklenmesi ve checksum'u | **Geçti** — ağırlık yerel snapshot'tan `local_files_only=True` ile yüklendi; revision ve dosya checksum'ları aşağıda. Fixture koşusu soket düzeyinde ağ kapatılarak yapıldı ve indirme denenmedi. |
| 3 | ESM kolonlarının gerçekten ESM açıkken üretildiği kanıtı | **Geçti** — `esm_llr` 1151 satırda 459 benzersiz sürekli değer taşıyor (min −13.5809, maks 3.3797, ortalama −2.5833). `--esm-yok` yolu bu kolonu sabit 0.0 yapar; matris o yoldan gelmemiş. |
| 4 | Bir varyant için gerekli minimum giriş | **Tanımlandı** — aşağıdaki "Minimum girdi" bölümü. |
| 5 | Sentetik `X` dizisi ve sentetik COSMIC yollarının canlıda yasaklanması | **Uygulandı** — `cikarim.py` reddediyor, `test_cikarim.py` bunu test ediyor. |
| 6 | Sabit fixture, beklenen olasılık ve SHAP değerleri | **Geçti** — IDH1 p.R132H için gerçek olasılık, ESM LLR ve TreeSHAP katkıları `fixtures/idh1_r132h.json` içinde toleranslarıyla kilitlendi. |

Altı madde de kapandı. Bu, modelin klinik olarak doğrulandığı anlamına gelmez;
yalnız çalışma zamanının tekrar üretilebilir ve sessiz varsayılansız olduğunu
gösterir. Aşağıdaki "Katkı dağılımı" bölümü sunumda dikkat edilmesi gereken
noktayı içerir.

## Özellik tanımının yeniden üretilebilirliği

Adaptörün eğitimle aynı sayısal tanımı kullandığı, eğitim matrisine karşı
ölçülerek doğrulandı (`test_cikarim.py::EgitimMatrisiYenidenUretimTesti`,
16/16 test geçti):

- 9 AAindex delta kolonu ve `grantham_yakl`: maksimum mutlak fark `1.4e-14`
  (kayan nokta gürültüsü).
- `cgga_missense_frekans`: CGGA WESeq_286 dosyasından yeniden üretildi,
  maksimum fark `9.7e-17`.
- `nispi_pozisyon`: ima edilen dizilim uzunluğu her satırda tamsayıya
  `4.4e-11` içinde oturuyor ve gen başına tek uzunluk çıkıyor — eğitimde
  kullanılan izoform belirsizliği yok.

AAindex tabloları ve delta formülü, `ozellik_cikarimi.py` içinden
bağımlılıksız `moduller/aa_ozellikler.py` modülüne **değiştirilmeden** taşındı;
eski import yolu korunuyor. Böylece çıkarım adaptörü torch yüklemeden aynı
tanımı kullanıyor.

## Özellikler hakkında üç bulgu

Bunlar model kusuru değil, **raporda ve sunumda düzeltilmesi gereken iddia**
sorunlarıdır.

1. **`cosmic_frekans_log` eğitimde tamamen ölü.** 1151 satırın hepsinde `0.0`
   (tek benzersiz değer). Zincir: `veri/CosmicMutantExport.tsv` yok →
   `veri_indirme.cosmic_frekans_oku` boş tablo döndürüyor
   (`moduller/veri_indirme.py:533`) → `np.log1p(fillna(0))`
   (`moduller/ozellik_cikarimi.py:273`). Model bu özellikten hiçbir sinyal
   öğrenmedi. Buna karşılık `moduller/rapor.py:77` onu gerçek bir girdi gibi
   tanımlıyor ve `VeriOdakliCozum/__init__.py` paket açıklamasında "COSMIC"
   veri kaynağı olarak sayılıyor. Final raporundaki COSMIC iddiası bu hâliyle
   savunulamaz: ya COSMIC TSV sağlanıp model yeniden eğitilmeli, ya da özellik
   ve iddia kaldırılmalı. Adaptör şu an eğitimdeki sabiti (`0.0`) kullanıyor ve
   raporun `notes` alanına bunu yazıyor.
2. **`esm_llr` ile `esm_pathojenite` aynı değişken.** İkisinin toplamı her
   satırda tam olarak `0.0`; `esm_pathojenite = -esm_llr`
   (`ozellik_cikarimi.py`). 15 özelliğin 2'si tek bilgi taşıyor. Ağaç
   modelinde zarar vermez ama "çok modlu 15 özellik" ifadesi yanıltıcı;
   SHAP önem sıralaması da bu ikiliye bölünür.
3. **`cgga_missense_frekans` kaba ve gen düzeyinde.** 207 genin 145'i sıfırdan
   büyük ama yalnızca 15 farklı değer var (hepsi k/286). IDH1 `0.4650` ve TP53
   `0.3741`, üçüncü sıradaki PIK3CA `0.0524`'ün çok üzerinde: özellik pratikte
   "bu varyant IDH1/TP53'te mi?" sorusunu kodluyor. `teshis.py`'nin ölçtüğü
   gen-kimliği overfit riski büyük ölçüde buradan gelir; yeni/rare genlerde
   katkısı yok.

Ek olarak etiket dengesi 827/324 (%72 patojenik); metrik sunulurken taban
oranın belirtilmesi gerekir.

## Minimum girdi

Tek varyant için zorunlu alanlar (`docs/contracts/genomics-input.v1.example.json`):

| Alan | Zorunlu | Not |
|---|---|---|
| `variant.gene` | evet | CGGA frekans tablosu bu sembolle aranır |
| `variant.proteinChange` | evet | `p.R132H` veya `p.Arg132His`; yalnız missense |
| `variant.proteinSequence` | evet (canlı) | Kanonik dizilim; yalnız 20 standart amino asit |
| `variant.uniprotAccession` | hayır | Sözleşmede var; adaptör henüz çözümlemiyor |

Adaptörün ürettiği özelliklerden yalnız ikisi girdi dışı kaynak ister:
`cgga_missense_frekans` (üretilmiş tablo) ve `esm_llr` (ESM-2 ağırlıkları).
`cosmic_frekans_log` şemadaki sabitten gelir.

Reddedilen durumlar — hepsi açık hata, sessiz varsayılan yok:

- missense olmayan değişim (`p.R132*`, `c.395G>A`, indel…),
- dizilim verilmemiş ya da standart olmayan harf içeriyor (`X` dolgusu dâhil),
- pozisyon dizilim dışında,
- bildirilen vahşi tip dizilimdeki harfle uyuşmuyor,
- ESM-2 yüklenemiyor veya tam `0.0` döndürüyor (eğitim hattında bu değer
  "skor üretilemedi"nin sessiz karşılığıdır),
- CGGA tablosu veya özellik şeması yok.

## Üretim ve çalıştırma

```bash
cd models
# Türetilmiş varlıklar (CGGA tablosu Git dışı, şema Git'te)
python -m VeriOdakliCozum.semayi_uret --cgga --sema
# Testler
python -m unittest VeriOdakliCozum.test_cikarim -v
# Tek varyant
python -m VeriOdakliCozum.cikarim --gen IDH1 --degisim p.R132H \
    --dizilim-dosyasi /yol/IDH1.fasta --cikti /tmp/mergen-cikarim
```

Gerçek ortamda (xgboost + torch + transformers kurulu) kapatılacak kontroller:

1. `semayi_uret --sema` çıktısında `featureNamesVerifiedFromModel: true` ve
   `traceColumnsVerifiedFromTrainingModule: true` olması.
2. ESM-2'nin ağdan bağımsız yüklenmesi ve ağırlık checksum'unun kaydı.
3. Bir sabit varyant için olasılığın ve SHAP değerlerinin toleransla bu
   belgeye yazılması.

## Çalışma zamanı doğrulaması

Nerede koştu: bu oturumun Linux konteynerinde, **CPU üzerinde**. Kullanıcının
Arch + RTX 5060 kurulumu değil; ağırlıklar ve model dosyaları oradan checksum
doğrulanarak kopyalandı. Farklı donanım `esm_llr`'yi son basamaklarda
kaydırabilir — fixture toleransları bunun içindir.

| Bileşen | Sürüm |
|---|---|
| Python | 3.12.11 |
| xgboost | 3.4.1 (model dosyası `version: [3,4,1]` bildiriyor) |
| torch | 2.14.0+cu130, `cuda.is_available()=False` |
| transformers | 5.17.0 |
| shap | 0.52.0 (yalnız çapraz kontrol için) |
| scikit-learn / pandas / numpy / joblib | 1.9.1 / 3.0.5 / 2.5.3 / 1.6.0 |

### Varlık checksum'ları

| Dosya | SHA-256 | Bayt |
|---|---|---|
| `mergen_xgb.json` | `6e5d99f1…c785` | 1 159 701 |
| `ozellik_matrisi.csv` | `c7616ea3…7684` | 296 641 |
| `cgga_gen_frekans.v1.json` | `4b067493…97af` | 240 557 |

### ESM-2 kaynağı

- Model kimliği: `facebook/esm2_t30_150M_UR50D`
- Revision: `a695f6045e2e32885fa60af20c13cb35398ce30c`
- `model.safetensors`: `c3f1da8aea53bddd32c246c86168c23b9fd72341fb9db9a94436f855f5053566` (595 257 706 bayt)
- `config.json`: `e512f68e…72dc` · `vocab.txt`: `0b82cc0a…8e03` · `tokenizer_config.json`: `7e9161ec…a29d` · `special_tokens_map.json`: `3aedcd42…9ee1`

Yükleme yolu `MERGEN_ESM_YEREL_YOL`, `MERGEN_ESM_CACHE_DIZINI` veya HF cache
üzerinden çözülür. Varsayılan çevrimdışıdır; indirme yalnız
`MERGEN_ESM_INDIRME_IZNI=1` verilen hazırlık adımında yapılır. Ağırlık
bulunamazsa `ESMYokHatasi` ile durulur, sessizce indirilmez.

### Sabit fixture — IDH1 p.R132H

Kaynak: UniProtKB `O75874` (IDHC_HUMAN), dizi sürümü SV=2, 414 aminoasit,
`https://rest.uniprot.org/uniprotkb/O75874.fasta`, erişim 2026-09-12.
132. pozisyondaki vahşi tip amino asidin gerçekten `R` olduğu dosyadan
doğrulandı. Dizi SHA-256 `5c99fe8b…3415`, dosya SHA-256 `65fa7147…dfdf`.
Kamuya açık referans dizidir; hasta verisi içermez.

| Çıktı | Değer | Tolerans |
|---|---|---|
| `esm_llr` | −0.20437836647033691 | 1e-3 |
| Patojenite olasılığı | 0.9996862411499023 | 1e-3 |
| Sınıf / eşik | `pathogenic` / 0.50 | — |
| SHAP taban değeri | 1.063351393 | — |
| Ham margin | 8.066596985 | — |
| Toplamsallık hatası | 2.03e-07 | 1e-4 |

SHAP uzayı **ham margin (log-odds)**, bağlantı fonksiyonu logit; olasılık
değil. `taban + katkılar = margin` ve `sigmoid(margin) = olasılık` her
çıkarımda doğrulanır, tutmazsa çıkarım hata verir. Katkılar XGBoost'un kendi
`pred_contribs` çıkışıdır (tam TreeSHAP, ek bağımlılık yok); `shap` paketinin
`TreeExplainer` sonucuyla karşılaştırıldı: en büyük fark 4.83e-10, taban
farkı 2.54e-10. Arka arkaya iki koşu bit düzeyinde aynı sonucu verdi.

### Katkı dağılımı — sunumda dikkat

Margin'in tabandan sapmasının büyük kısmı tek bir özellikten geliyor:

| Özellik | Katkı |
|---|---|
| `cgga_missense_frekans` | +4.734 |
| `nispi_pozisyon` | +0.737 |
| `esm_pathojenite` | +0.623 |
| `delta_hidrofobiklik` | +0.373 |
| `cosmic_frekans_log` | 0.000 |

Yani model bu vakada esas olarak "varyant IDH1'de mi?" bilgisine dayanıyor;
ESM'in evrimsel sinyali (`esm_llr` = −0.204) zayıf kalıyor. Yukarıdaki üç
bulgunun ikisi burada sayıyla doğrulanmış oluyor: COSMIC katkısı tam sıfır,
CGGA gen-kimliği vekili baskın. Doğru olasılık üretmesi modelin bilinen
sürücü genlerde iyi, yeni/rare genlerde zayıf olacağı anlamına gelir.

### Çalıştırılan komutlar

```bash
python -m VeriOdakliCozum.semayi_uret --sema
python -m VeriOdakliCozum.cikarim --gen IDH1 --degisim p.R132H \
    --dizilim-dosyasi VeriOdakliCozum/fixtures/IDH1_O75874.fasta
python -m unittest VeriOdakliCozum.test_cikarim -v
```

Sonuç: 28 test, hepsi geçti (varlıklar mevcutken atlama yok). Testler
arasında ağırlık eksikken açık hata, özellik sırası bozulunca çıkarımın
reddi, ağ soketleri kapatılmışken fixture koşusu ve canlı çıkarımın eğitim
modüllerini (`pandas`, `requests` dâhil) hiç yüklememesi de var.

## Kapsam dışı

Bu denetim yeniden eğitim, eşik değiştirme, ön işleme değişikliği veya klinik
doğrulama içermez. Adaptör eğitim modüllerini (`veri_indirme`, `model_egitim`,
`degerlendirme`, `rapor`) import etmez. Genomik demo vakaları S3'ün kalan işidir; SHAP açıklaması
artık çıkarım raporunun `explanation` alanında üretiliyor.
