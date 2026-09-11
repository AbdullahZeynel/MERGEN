"""
MERGEN raporu için profesyonel akış şemaları.

İki şekil üretir:
    1) sistem_mimarisi.png — başlık şeritli, renk kodlu, madde listeli
       sistem mimarisi (görüntü kolu mavi, veri kolu kırmızı, füzyon altın,
       sonuç yeşil).
    2) cikti_akisi.png — tek hastada adım adım çıktı üretim akışı, aynı
       görsel dille.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mp
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

CIKTI = Path(__file__).resolve().parent / "sonuclar"
CIKTI.mkdir(parents=True, exist_ok=True)

# Renk paleti (başlık şeridi / gövde)
RENK = {
    "altin":  ("#b8860b", "#f7ecc9"),
    "mavi":   ("#2f6ea5", "#d6e6f4"),
    "kirmizi":("#b5403d", "#f4dcdb"),
    "yesil":  ("#5a8a3c", "#dcebc8"),
}


def panel(ax, x, y, w, h, baslik, satirlar, anahtar,
          baslik_fs=12, govde_fs=10):
    """Başlık şeritli + madde listeli kutu çizer. (x, y) sol-alt köşedir."""
    bas_renk, gov_renk = RENK[anahtar]
    serit = 0.62

    # Gövde (tüm kutu, açık renk, yuvarlak köşe)
    ax.add_patch(mp.FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        facecolor=gov_renk, edgecolor=bas_renk, linewidth=1.8, zorder=2))

    # Başlık şeridi (üstte, koyu renk) — alt kenar gövdenin içine biner
    ax.add_patch(mp.FancyBboxPatch(
        (x, y + h - serit), w, serit,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        facecolor=bas_renk, edgecolor=bas_renk, linewidth=1.8, zorder=3))
    # Şeridin altını gövdeyle kaynaştırmak için ince düz örtü
    ax.add_patch(plt.Rectangle(
        (x + 0.04, y + h - serit - 0.02), w - 0.08, 0.12,
        facecolor=bas_renk, edgecolor="none", zorder=3))

    # Başlık metni
    ax.text(x + w / 2, y + h - serit / 2, baslik,
            ha="center", va="center", fontsize=baslik_fs,
            fontweight="bold", color="white", zorder=5)

    # Gövde içeriği (madde listesi, sola hizalı)
    ty = y + h - serit - 0.27
    for satir in satirlar:
        ax.text(x + 0.28, ty, satir, ha="left", va="top",
                fontsize=govde_fs, color="#1f2937", zorder=5,
                linespacing=1.2)
        ty -= 0.38 * (1 + satir.count("\n"))


def ok(ax, x1, y1, x2, y2, renk="#374151", kalin=2.0):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=20,
        linewidth=kalin, color=renk, zorder=1,
        shrinkA=2, shrinkB=2))


# ===========================================================================
# ŞEKİL 1 — Sistem Mimarisi
# ===========================================================================
fig, ax = plt.subplots(figsize=(16, 11))
ax.set_xlim(0, 20)
ax.set_ylim(0, 14)
ax.axis("off")

# Başlık (sol üst, ikinci görüntüdeki gibi)
ax.text(0.4, 13.5, "MERGEN Hibrit Karar Destek Sistemi — Mimari",
        ha="left", va="top", fontsize=21, fontweight="bold", color="#1d3a63")
ax.text(0.4, 12.8, "Görüntü ve veri modüllerinin geç birleştirilmesi (late fusion)",
        ha="left", va="top", fontsize=13, color="#5b6470", style="italic")

# Hasta (üst orta, altın)
panel(ax, 7.6, 10.9, 4.8, 1.15, "Hasta (glioma şüphesi)",
      [], "altin", baslik_fs=13)

# --- SOL KOL (Görüntü, mavi) ---
panel(ax, 0.6, 8.7, 6.2, 1.7, "Manyetik Rezonans Görüntüleme",
      ["• Çok modlu çekim:", "   FLAIR, T1, T1c, T2"], "mavi")

panel(ax, 0.6, 5.9, 6.2, 2.3, "Görüntü Modülü — UWCSE",
      ["Modeller: nnU-Net (CNN),",
       "      Swin UNETR (Transformer)",
       "Teknikler: CSW · UNC · Post-processing"], "mavi")

panel(ax, 0.6, 3.3, 6.2, 2.1, "Segmentasyon Çıktıları",
      ["• Tümör bölgeleri: TC, WT, ET",
       "• Tümör hacmi",
       "• Segmentasyon güveni"], "mavi")

# --- SAĞ KOL (Veri, kırmızı) ---
panel(ax, 13.2, 8.7, 6.2, 1.7, "Tümör Doku Örneği (WES)",
      ["• Whole-Exome Sequencing",
       "• Somatik missense varyantlar"], "kirmizi")

panel(ax, 13.2, 5.9, 6.2, 2.3, "Veri Modülü — MERGEN",
      ["Modeller: XGBoost + ESM-2", "      + AAindex",
       "Analiz: SHAP açıklanabilirlik"], "kirmizi")

panel(ax, 13.2, 3.3, 6.2, 2.1, "Veri Analiz Çıktıları",
      ["• Varyant patojenite olasılıkları",
       "• TMB ve sürücü mutasyon profili",
       "• SHAP biyolojik gerekçeler"], "kirmizi")

# --- FÜZYON (altın, geniş) ---
panel(ax, 4.0, 1.2, 12.0, 1.85, "Füzyon Katmanı (Geç Füzyon / Karar Katmanı)",
      ["Özellik füzyonu: tümör hacmi · segmentasyon güveni · TMB · "
       "sürücü gen · patojenite",
       "Yöntem: ağırlıklı toplam veya logistik regresyon"], "altin",
      baslik_fs=12.5)

# --- SONUÇ (yeşil) ---
panel(ax, 6.4, 0.0, 7.2, 0.95, "Birleşik Klinik Karar Raporu",
      [], "yesil", baslik_fs=12.5)

# --- OKLAR ---
ok(ax, 8.6, 10.9, 4.0, 10.4)      # Hasta -> MR
ok(ax, 11.4, 10.9, 16.0, 10.4)    # Hasta -> WES
ok(ax, 3.7, 8.7, 3.7, 8.2)        # MR -> Görüntü Modülü
ok(ax, 3.7, 5.9, 3.7, 5.4)        # Görüntü Modülü -> Segmentasyon
ok(ax, 16.3, 8.7, 16.3, 8.2)      # WES -> Veri Modülü
ok(ax, 16.3, 5.9, 16.3, 5.4)      # Veri Modülü -> Veri Analiz
ok(ax, 3.7, 3.3, 7.0, 3.05)       # Segmentasyon -> Füzyon (çapraz)
ok(ax, 16.3, 3.3, 13.0, 3.05)     # Veri Analiz -> Füzyon (çapraz)
ok(ax, 10.0, 1.2, 10.0, 0.95)     # Füzyon -> Sonuç

fig.tight_layout()
yol = CIKTI / "sistem_mimarisi.png"
fig.savefig(yol, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Yazıldı: {yol}")


# ===========================================================================
# ŞEKİL 2 — Çıktı Akışı (aynı görsel dil)
# ===========================================================================
fig, ax = plt.subplots(figsize=(16, 12))
ax.set_xlim(0, 20)
ax.set_ylim(0, 15)
ax.axis("off")

ax.text(0.4, 14.5, "Tek Hasta İçin Çıktı Üretim Akışı",
        ha="left", va="top", fontsize=21, fontweight="bold", color="#1d3a63")
ax.text(0.4, 13.8,
        "Veri girişinden hekim raporuna kadar ardışık işlem adımları",
        ha="left", va="top", fontsize=13, color="#5b6470", style="italic")

# Ortak girdi
panel(ax, 7.6, 12.2, 4.8, 1.0, "Hasta Verisi (MR + WES)", [], "altin",
      baslik_fs=12.5)

# Sol sütun (görüntü, mavi) — 5 adım
gx, gw = 0.6, 8.6
panel(ax, gx, 10.4, gw, 1.25, "Adım G1 — Ön İşleme",
      ["• Kafatası çıkarma · N4 bias düzeltme · kayıt (registration)"], "mavi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, gx, 8.85, gw, 1.25, "Adım G2 — nnU-Net Çıkarımı",
      ["• 3B U-Net, BraTS 2021 eğitimli olasılık haritası"], "mavi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, gx, 7.30, gw, 1.25, "Adım G3 — Swin UNETR Çıkarımı",
      ["• Transformer kodlayıcı, olasılık haritası"], "mavi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, gx, 5.75, gw, 1.25, "Adım G4 — UWCSE Birleştirme",
      ["• CSW + voksel belirsizliği ile ağırlıklı topluluk"], "mavi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, gx, 4.20, gw, 1.25, "Adım G5 — Son İşleme ve Hacim",
      ["• Bağlı bileşen temizliği · bölgesel hacim hesabı"], "mavi",
      baslik_fs=11, govde_fs=9.5)

# Sağ sütun (veri, kırmızı) — 5 adım
dx = 10.8
panel(ax, dx, 10.4, gw, 1.25, "Adım V1 — MAF Okuma",
      ["• Somatik MAF okuma · missense süzgeci"], "kirmizi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, dx, 8.85, gw, 1.25, "Adım V2 — Dizilim Eşleme",
      ["• HGVSp parse · UniProt referans dizilim eşleme"], "kirmizi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, dx, 7.30, gw, 1.25, "Adım V3 — Özellik Çıkarımı",
      ["• ESM-2 LLR + AAindex deltaları + CGGA frekansı"], "kirmizi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, dx, 5.75, gw, 1.25, "Adım V4 — XGBoost Tahmini",
      ["• 15 boyutlu vektör ile patojenite olasılığı"], "kirmizi",
      baslik_fs=11, govde_fs=9.5)
panel(ax, dx, 4.20, gw, 1.25, "Adım V5 — SHAP Gerekçesi",
      ["• Her varyant için biyolojik gerekçe çıkarımı"], "kirmizi",
      baslik_fs=11, govde_fs=9.5)

# Füzyon
panel(ax, 4.0, 2.0, 12.0, 1.6, "Adım F1 — Füzyon Katmanı",
      ["Görüntü çıktıları (hacim, güven) ile veri çıktıları "
       "(patojenite, TMB, sürücü gen) birleşimi",
       "Ortak karar vektörü ve birleşik olasılık"], "altin",
      baslik_fs=12)

# Sonuç
panel(ax, 5.6, 0.4, 8.8, 1.05, "Adım F2 — Hekim Raporu (PDF / Web)",
      ["Segmentasyon · varyant tablosu · gerekçeler · güven aralıkları"],
      "yesil", baslik_fs=11.5, govde_fs=9.5)

# Oklar
ok(ax, 9.0, 12.2, 4.9, 11.65)     # Hasta -> G1
ok(ax, 11.0, 12.2, 15.1, 11.65)   # Hasta -> V1
for y1, y2 in [(10.4, 10.1), (8.85, 8.55), (7.30, 7.0), (5.75, 5.45)]:
    ok(ax, 4.9, y1, 4.9, y2)       # sol sütun dikey
    ok(ax, 15.1, y1, 15.1, y2)     # sağ sütun dikey
ok(ax, 4.9, 4.2, 7.5, 3.6)        # G5 -> Füzyon
ok(ax, 15.1, 4.2, 12.5, 3.6)      # V5 -> Füzyon
ok(ax, 10.0, 2.0, 10.0, 1.45)     # Füzyon -> Rapor

fig.tight_layout()
yol = CIKTI / "cikti_akisi.png"
fig.savefig(yol, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Yazıldı: {yol}")
