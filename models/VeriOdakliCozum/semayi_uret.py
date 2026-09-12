"""
Özellik Şeması ve CGGA Frekans Tablosu Üretici
===============================================

Eğitilmiş modelin özellik sözleşmesini dosyaya döker; çıkarım adaptörü
(``cikarim.py``) yalnızca bu sözleşmeye bakar. Betik **eğitim yapmaz**,
model dosyalarını değiştirmez; yalnızca okur ve türetilmiş metadata yazar.

Kullanım (repo kökünden):

    python -m VeriOdakliCozum.semayi_uret --cgga --sema

Çıktılar:
    modeller/cgga_gen_frekans.v1.json   CGGA gen→frekans tablosu (Git dışı)
    semalar/ozellik_semasi.v1.json      Özellik sırası + sağlama toplamları

``--sema`` eğitim matrisinin kolon sırasını yetkili kaynak alır
(``model_egitim.ozellikleri_ayir`` iz kolonlarını düşürür, sıra korunur).
xgboost kuruluysa modelin kendi özellik adları da karşılaştırılır ve
uyuşmazlıkta betik hata ile durur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

from . import config


# model_egitim.IZ_KOLONLARI ile aynı küme. Kopya bilinçli: bu betik xgboost/
# sklearn kurulu olmayan bir makinede de şema üretebilsin diye eğitim modülü
# import edilmez. Eğitim modülü erişilebilirse küme birebir doğrulanır ve
# uyuşmazlıkta betik durur.
IZ_KOLONLARI = {"etiket", "gen", "protein_degisim", "kohort",
                "mc3_sift_skor", "mc3_polyphen_skor"}


def _iz_kolonlarini_dogrula() -> bool:
    """Eğitim modülüyle iz kolonu kümesini karşılaştırır."""
    try:
        from .moduller.model_egitim import IZ_KOLONLARI as egitim_kumesi
    except Exception as exc:                      # eğitim bağımlılıkları yok
        LOG.warning("model_egitim import edilemedi (%s) — iz kolonları "
                    "doğrulanmadı.", type(exc).__name__)
        return False
    if set(egitim_kumesi) != IZ_KOLONLARI:
        raise ValueError(
            "İz kolonu kümesi eğitim modülüyle uyuşmuyor.\n"
            f"  eğitim : {sorted(egitim_kumesi)}\n  şema   : {sorted(IZ_KOLONLARI)}"
        )
    return True

LOG = logging.getLogger("SEMA")

SEMA_SURUMU = 1
SEMA_DIZINI = config.PROJE_KOKU / "semalar"
SEMA_YOLU = SEMA_DIZINI / f"ozellik_semasi.v{SEMA_SURUMU}.json"
CGGA_TABLO_YOLU = config.MODEL_DIZINI / f"cgga_gen_frekans.v{SEMA_SURUMU}.json"
MATRIS_YOLU = config.VERI_DIZINI / "ozellik_matrisi.csv"
KARAR_ESIGI = 0.5          # model_egitim.son_modeli_egit ile aynı eşik


def sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


# ---------------------------------------------------------------------------
def cgga_tablosu_yaz(hedef: Path = CGGA_TABLO_YOLU) -> dict:
    """CGGA WESeq_286 dosyasından gen→missense frekans tablosu üretir."""
    import pandas as pd

    kaynak = config.CGGA_MUTASYON_DOSYASI
    if not kaynak.exists():
        raise FileNotFoundError(
            f"CGGA mutasyon dosyası yok: {kaynak}. Tablo üretilemez; "
            "eksik dosya yerine sıfır frekans uydurulmaz."
        )

    df = pd.read_csv(kaynak, sep="\t", low_memory=False, index_col=0)
    df.index.name = "gen"
    orneklem = int(df.shape[1])
    maske = df.apply(
        lambda s: s.astype(str).str.contains("missense", case=False, na=False)
        | s.astype(str).str.contains("multiple_variant", case=False, na=False)
    )
    frekans = (maske.sum(axis=1) / orneklem)

    tablo = {
        "schemaVersion": SEMA_SURUMU,
        "feature": "cgga_missense_frekans",
        "source": {
            "file": kaynak.name,
            "sha256": sha256(kaynak),
            "sampleCount": orneklem,
            "geneCount": int(len(frekans)),
        },
        "note": (
            "Gen bazlı, hasta bazlı değil: CGGA kohortunda ilgili gende missense "
            "veya multiple_variant taşıyan örnek oranı. Tabloda olmayan gen için "
            "değer 0.0'dır; eğitimde de aynı doldurma uygulandı."
        ),
        "frequencies": {
            str(gen): round(float(deger), 12)
            for gen, deger in frekans.items() if deger > 0
        },
    }
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(tablo, ensure_ascii=False, indent=1, sort_keys=True))
    LOG.info("CGGA tablosu yazıldı: %s (%d sıfır olmayan gen / %d gen, %d örnek)",
             hedef, len(tablo["frequencies"]), len(frekans), orneklem)
    return tablo


# ---------------------------------------------------------------------------
def _model_ozellik_adlari() -> list[str] | None:
    """Eğitilmiş modelin kendi bildirdiği özellik adları; xgboost yoksa None."""
    try:
        import xgboost as xgb
    except ImportError:
        LOG.warning("xgboost kurulu değil — modelin kendi özellik adları doğrulanmadı.")
        return None

    model_yolu = config.MODEL_DIZINI / "mergen_xgb.json"
    if not model_yolu.exists():
        LOG.warning("%s yok — modelin kendi özellik adları doğrulanmadı.", model_yolu)
        return None

    model = xgb.XGBClassifier()
    model.load_model(str(model_yolu))
    adlar = getattr(model, "feature_names_in_", None)
    if adlar is None:
        adlar = model.get_booster().feature_names
    return list(adlar) if adlar is not None else None


def sema_yaz(hedef: Path = SEMA_YOLU) -> dict:
    """Eğitim matrisinden özellik sözleşmesini türetir ve dosyaya yazar."""
    import pandas as pd

    if not MATRIS_YOLU.exists():
        raise FileNotFoundError(
            f"Eğitim özellik matrisi yok: {MATRIS_YOLU}. Şema uydurulmaz."
        )

    iz_dogrulandi = _iz_kolonlarini_dogrula()
    matris = pd.read_csv(MATRIS_YOLU)
    ozellikler = [k for k in matris.columns if k not in IZ_KOLONLARI]

    model_adlari = _model_ozellik_adlari()
    if model_adlari is not None and model_adlari != ozellikler:
        raise ValueError(
            "Model özellik adları eğitim matrisiyle uyuşmuyor.\n"
            f"  model  : {model_adlari}\n  matris : {ozellikler}"
        )

    sabitler = [k for k in ozellikler if matris[k].nunique(dropna=False) == 1]
    varliklar = {}
    for ad in ("mergen_xgb.json", "mergen_xgb.joblib", CGGA_TABLO_YOLU.name):
        yol = config.MODEL_DIZINI / ad
        if yol.exists():
            varliklar[ad] = {"sha256": sha256(yol), "bytes": yol.stat().st_size}

    sema = {
        "schemaVersion": SEMA_SURUMU,
        "modelId": "mergen-glioma-variant-xgb",
        "modelVersion": f"v{SEMA_SURUMU}",
        "module": "genomics",
        "disease": "glioma-variant-pathogenicity",
        "decisionThreshold": KARAR_ESIGI,
        "featureOrder": ozellikler,
        "featureNamesVerifiedFromModel": model_adlari is not None,
        "traceColumnsVerifiedFromTrainingModule": iz_dogrulandi,
        "constantInTraining": {k: float(matris[k].iloc[0]) for k in sabitler},
        "trainingMatrix": {
            "file": MATRIS_YOLU.name,
            "sha256": sha256(MATRIS_YOLU),
            "rows": int(len(matris)),
            "genes": int(matris["gen"].nunique()),
            "positives": int((matris["etiket"] == 1).sum()),
            "negatives": int((matris["etiket"] == 0).sum()),
        },
        "assets": varliklar,
        "esmModel": config.ESM_MODEL_ADI,
        "notes": [
            "Özellik sırası eğitim matrisinin kolon sırasıdır; iz kolonları "
            f"({sorted(IZ_KOLONLARI)}) modele girmez.",
            "constantInTraining içindeki özellikler eğitimde tek değer taşıdı; "
            "model onlardan sinyal öğrenmedi. Çıkarımda aynı sabit kullanılır.",
            "esm_pathojenite = -esm_llr; iki kolon tek bilgi taşır.",
        ],
    }
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sema, ensure_ascii=False, indent=2) + "\n")
    LOG.info("Şema yazıldı: %s (%d özellik, sabit: %s)",
             hedef, len(ozellikler), sabitler or "yok")
    return sema


# ---------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description="Özellik şeması / CGGA tablosu üretici")
    p.add_argument("--cgga", action="store_true", help="CGGA gen frekans tablosunu üret")
    p.add_argument("--sema", action="store_true", help="Özellik şemasını üret")
    arg = p.parse_args()
    if not (arg.cgga or arg.sema):
        p.error("--cgga ve/veya --sema verilmeli")

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")
    if arg.cgga:
        cgga_tablosu_yaz()
    if arg.sema:
        sema_yaz()


if __name__ == "__main__":
    main()
