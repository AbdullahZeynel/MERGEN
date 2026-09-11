"""MERGEN + UWCSE fusion mimari diyagramı üretir (rapor için)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp
from pathlib import Path

fig, ax = plt.subplots(figsize=(14, 9))
ax.set_xlim(0, 14)
ax.set_ylim(0, 10)
ax.axis("off")


def kutu(x, y, w, h, metin, renk, kenar="black", fontsize=10, bold=False):
    ax.add_patch(mp.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                                     facecolor=renk, edgecolor=kenar, linewidth=1.5))
    ax.text(x + w/2, y + h/2, metin, ha="center", va="center",
            fontsize=fontsize, fontweight="bold" if bold else "normal", wrap=True)


def ok(x1, y1, x2, y2, etiket="", renk="black"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", lw=1.8, color=renk))
    if etiket:
        ax.text((x1+x2)/2, (y1+y2)/2 + 0.15, etiket, ha="center",
                fontsize=8, color=renk, style="italic")


# Başlık
ax.text(7, 9.6, "MERGEN + UWCSE — Hibrit Karar Destek Sistemi",
        ha="center", fontsize=16, fontweight="bold")
ax.text(7, 9.2, "Görüntü Modeli ⊕ Veri Modeli ⇒ Birleşik Klinik Karar",
        ha="center", fontsize=11, style="italic", color="#555")

# Hasta girişi
kutu(5.5, 7.8, 3, 0.9, "HASTA\n(Glioma Şüphesi)", "#fef3c7", fontsize=11, bold=True)

# İki kol — sol: MR, sağ: WES
kutu(0.5, 6.3, 5, 1.0, "Çok-modlu MRI\n(FLAIR, T1, T1c, T2)", "#dbeafe", fontsize=10)
kutu(8.5, 6.3, 5, 1.0, "Tümör Doku Biyopsisi\n→ Whole-Exome Sequencing (WES)",
     "#fce7f3", fontsize=10)

ok(7, 7.8, 3, 7.3)
ok(7, 7.8, 11, 7.3)

# Görüntü modeli
kutu(0.2, 4.5, 5.6, 1.4,
     "UWCSE Ensemble (Görüntü Modeli)\n"
     "nnU-Net (CNN) + Swin UNETR (Transformer)\n"
     "+ CSW + UNC + PP katmanları",
     "#bfdbfe", kenar="#1e40af", fontsize=9, bold=True)

ok(3, 6.3, 3, 5.9)

# Görüntü çıktıları
kutu(0.0, 2.9, 1.95, 1.2, "TC bölgesi\nDice 0.947", "#e0f2fe", fontsize=8)
kutu(2.05, 2.9, 1.95, 1.2, "WT bölgesi\nDice 0.942", "#e0f2fe", fontsize=8)
kutu(4.10, 2.9, 1.7, 1.2, "ET bölgesi\nDice 0.919", "#e0f2fe", fontsize=8)

ok(3, 4.5, 1, 4.1)
ok(3, 4.5, 3, 4.1)
ok(3, 4.5, 4.95, 4.1)

# Veri modeli
kutu(8.2, 4.5, 5.6, 1.4,
     "MERGEN (Veri Modeli)\n"
     "XGBoost + ESM-2 + AAindex\n"
     "AUC 0.967, F1 0.940",
     "#fbcfe8", kenar="#9d174d", fontsize=9, bold=True)

ok(11, 6.3, 11, 5.9)

# Veri çıktıları
kutu(8.0, 2.9, 1.85, 1.2, "Varyant\npatojenite\nskorları", "#fdf2f8", fontsize=8)
kutu(9.95, 2.9, 1.95, 1.2, "SHAP\nbiyolojik\naçıklama", "#fdf2f8", fontsize=8)
kutu(12.00, 2.9, 1.8, 1.2, "TMB & sürücü\ngen anotasyonu", "#fdf2f8", fontsize=8)

ok(11, 4.5, 8.9, 4.1)
ok(11, 4.5, 10.9, 4.1)
ok(11, 4.5, 12.9, 4.1)

# Füzyon katmanı
kutu(3, 1.0, 8, 1.4,
     "FÜZYON KATMANI (Geç-Birleştirme)\n"
     "Tümör hacmi · TMB · Sürücü mutasyon profili · Segmentasyon güveni\n"
     "→ Multi-modal logistik regresyon / ağırlıklı ortalama",
     "#fef9c3", kenar="#854d0e", fontsize=9, bold=True)

ok(2.0, 2.9, 5, 2.4)
ok(4.5, 2.9, 6, 2.4)
ok(5.0, 2.9, 6.5, 2.4)
ok(9, 2.9, 7.5, 2.4)
ok(11, 2.9, 8.5, 2.4)
ok(12.9, 2.9, 9, 2.4)

# Klinik karar
kutu(4.5, -0.4, 5, 1.0,
     "Birleşik Klinik Karar Raporu\n"
     "(Klinisyen + Karar Destek)",
     "#d1fae5", kenar="#065f46", fontsize=10, bold=True)

ok(7, 1.0, 7, 0.6)

# Not
ax.text(7, -0.9,
        "Not: Aynı hastada hem görüntü hem WES verisi içeren açık veri seti hâlâ yoktur. "
        "Füzyon prototip aşamasındadır; klinik deneylerde gözlenmesi hedeflenmektedir.",
        ha="center", fontsize=8, style="italic", color="#555")

fig.tight_layout()
yol = Path(__file__).resolve().parent / "sonuclar" / "fusion_mimari.png"
yol.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(yol, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Fusion diyagramı kaydedildi: {yol}")
