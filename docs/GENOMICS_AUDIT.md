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
| 1 | XGBoost dosyasının açılması, özellik adları/sırası, kütüphane sürümü | **Bekliyor** — bu makinede xgboost kurulu değil. Sıra eğitim matrisinden türetildi; `semayi_uret --sema` xgboost varsa modelin kendi adlarıyla karşılaştırır ve uyuşmazlıkta durur. Şemada `featureNamesVerifiedFromModel: false`. |
| 2 | ESM-2 ağırlıklarının çevrimdışı yüklenmesi ve checksum'u | **Bekliyor** — GPU VM kurulmadı (S4). |
| 3 | ESM kolonlarının gerçekten ESM açıkken üretildiği kanıtı | **Geçti** — `esm_llr` 1151 satırda 459 benzersiz sürekli değer taşıyor (min −13.5809, maks 3.3797, ortalama −2.5833). `--esm-yok` yolu bu kolonu sabit 0.0 yapar; matris o yoldan gelmemiş. |
| 4 | Bir varyant için gerekli minimum giriş | **Tanımlandı** — aşağıdaki "Minimum girdi" bölümü. |
| 5 | Sentetik `X` dizisi ve sentetik COSMIC yollarının canlıda yasaklanması | **Uygulandı** — `cikarim.py` reddediyor, `test_cikarim.py` bunu test ediyor. |
| 6 | Sabit fixture, beklenen olasılık ve SHAP değerleri | **Kısmi** — özellik vektörü fixture'ı kilitlendi (`test_fixture_vektoru_sabit`). Olasılık ve SHAP toleransı gerçek ortam gerektiriyor; madde 1–2 ile birlikte bekliyor. |

Madde 1, 2 ve 6 kapanmadan arayüzde genom modeli "çalışıyor" gösterilmez.

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

## Kapsam dışı

Bu denetim yeniden eğitim, eşik değiştirme, ön işleme değişikliği veya klinik
doğrulama içermez. Adaptör eğitim modüllerini (`veri_indirme`, `model_egitim`,
`degerlendirme`, `rapor`) import etmez. SHAP açıklaması ve genomik demo
vakaları S3'ün kalan işidir.
