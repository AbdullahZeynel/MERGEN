# HD95 — Sınır Doğruluğu (UCSF-PDGM kilitli test, n=172)

Dice bir örtüşme ölçüsüdür ve sınır hatalarına görece duyarsızdır; HD95 tam da sınırı ölçer.
BraTS ve klinik literatür ikisini birlikte raporlar. **Düşük olan iyidir.**

| Model | Bölge | HD95 ort (mm) | Medyan | p75 | Tanımlı vaka | Tanımsız |
|---|---|---:|---:|---:|---:|---:|
| nnU-Net BraTS21 | TC | 3.60 | 1.41 | 3.86 | 117 | 55 |
| nnU-Net BraTS21 | WT | 3.90 | 2.00 | 3.04 | 172 | 0 |
| nnU-Net BraTS21 | ET | 2.60 | 1.41 | 2.24 | 120 | 52 |
| Swin UNETR BraTS21 | TC | 2.78 | 1.00 | 2.54 | 144 | 28 |
| Swin UNETR BraTS21 | WT | 5.86 | 2.91 | 6.34 | 170 | 2 |
| Swin UNETR BraTS21 | ET | 1.93 | 1.00 | 1.41 | 156 | 16 |
| **UWCSE (ÜRÜN)** | TC | 2.44 | 1.00 | 2.12 | 151 | 21 |
| **UWCSE (ÜRÜN)** | WT | 3.45 | 2.00 | 3.93 | 171 | 1 |
| **UWCSE (ÜRÜN)** | ET | 1.77 | 1.00 | 1.41 | 160 | 12 |

**Ürün her üç bölgede de iki tek modeli de geçiyor.** TC 2,44 mm (nnU-Net 3,60 · Swin 2,78),
WT 3,45 mm (3,90 · 5,86), ET 1,77 mm (2,60 · 1,93).

**Tanımsız vakalar önemli.** Referans ile tahminden yalnız biri boşsa HD95 tanımsızdır ve
ortalamaya girmez. nnU-Net'te TC için 55, ET için 52 vaka tanımsız; üründe 21 ve 12. Bu fark
doğrudan yanlış-çekirdek sorununun ölçüsüdür: nnU-Net olmayan bölgeleri işaretlediği için
o vakalarda mesafe hesaplanamıyor. Tabloyu okurken tanımsız sayısını da vermek gerekir.

Boş küme kuralı: ikisi de boşsa 0, yalnız biri boşsa tanımsız.

Kaynak: `hd95.json` · üretim betiği: `compute_hd95.py` (yeniden çıkarım yok, uwcse_v1 önbelleği)
