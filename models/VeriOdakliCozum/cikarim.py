"""
Tek Varyant Patojenite Çıkarımı (canlı adaptör)
================================================

Eğitilmiş XGBoost modelini **yalnızca okuyup** tek bir missense varyant için
olasılık üretir. Eğitim, veri indirme ve değerlendirme yollarına dokunmaz:
bu modül ``veri_indirme``, ``model_egitim``, ``degerlendirme`` ve ``rapor``
modüllerini import etmez.

Özellik sırası ve karar eşiği ``semalar/ozellik_semasi.v1.json`` dosyasından
okunur; şema ile modelin kendi özellik adları uyuşmazsa çıkarım reddedilir.

Sessiz doldurma yoktur. Aşağıdaki durumların hepsi açık hatadır:

* protein değişimi standart missense biçiminde değil,
* protein dizilimi verilmemiş veya standart olmayan harf (``X`` dâhil) içeriyor
  — eğitim hattındaki sentetik ``X`` kontekst yolu canlıda yasaktır,
* bildirilen pozisyondaki amino asit dizilimdeki harfle uyuşmuyor,
* ESM-2 yüklenemiyor veya skoru üretilemiyor — ESM özelliği sıfırlanarak
  tahmin yapılmaz,
* CGGA frekans tablosu yok,
* şemadaki özellik sırası modelle uyuşmuyor.

Kullanım:

    python -m VeriOdakliCozum.cikarim --girdi input.json --cikti sonuc/
    python -m VeriOdakliCozum.cikarim --gen IDH1 --degisim p.R132H --dizilim-dosyasi idh1.txt

CLI, ``docs/contracts/genomics-input.v1.example.json`` biçimindeki girdiyi
okur ve ``report.json`` yazar.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config
from .moduller.aa_ozellikler import aaindex_delta_hesapla
from .moduller.on_isleme import hgvsp_ayristir

LOG = logging.getLogger(__name__)

SEMA_YOLU = config.PROJE_KOKU / "semalar" / "ozellik_semasi.v1.json"
MODEL_YOLU = config.MODEL_DIZINI / "mergen_xgb.json"
CGGA_TABLO_YOLU = config.MODEL_DIZINI / "cgga_gen_frekans.v1.json"


class CikarimHatasi(RuntimeError):
    """Girdi, varlık veya şema sözleşmesi ihlali. Sessiz varsayılan yerine hata."""


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VaryantGirdisi:
    gen: str
    protein_degisim: str
    protein_dizilim: str | None = None
    uniprot_erisim: str | None = None


@dataclass
class CikarimSonucu:
    gen: str
    protein_degisim: str
    olasilik: float
    sinif: int
    esik: float
    ozellikler: dict[str, float]
    model: dict[str, Any]
    notlar: list[str] = field(default_factory=list)

    def sozluk(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "module": "genomics",
            "disease": "glioma-variant-pathogenicity",
            "mode": "live",
            "modelId": self.model["modelId"],
            "modelVersion": self.model["modelVersion"],
            "hasPrediction": True,
            "hasGroundTruth": False,
            "variant": {"gene": self.gen, "proteinChange": self.protein_degisim},
            "prediction": {
                "pathogenicityProbability": round(self.olasilik, 6),
                "class": "pathogenic" if self.sinif == 1 else "benign",
                "decisionThreshold": self.esik,
            },
            "features": {k: round(v, 9) for k, v in self.ozellikler.items()},
            "featureOrder": list(self.ozellikler),
            "notes": self.notlar,
        }


# ---------------------------------------------------------------------------
def sema_yukle(yol: Path = SEMA_YOLU) -> dict[str, Any]:
    if not yol.exists():
        raise CikarimHatasi(
            f"Özellik şeması yok: {yol}. "
            "`python -m VeriOdakliCozum.semayi_uret --cgga --sema` ile üretin."
        )
    sema = json.loads(yol.read_text())
    if sema.get("schemaVersion") != 1:
        raise CikarimHatasi(f"Desteklenmeyen şema sürümü: {sema.get('schemaVersion')}")
    for alan in ("featureOrder", "decisionThreshold", "modelId", "modelVersion"):
        if alan not in sema:
            raise CikarimHatasi(f"Şemada '{alan}' alanı yok: {yol}")
    return sema


def cgga_tablosu_yukle(yol: Path = CGGA_TABLO_YOLU) -> dict[str, Any]:
    if not yol.exists():
        raise CikarimHatasi(
            f"CGGA frekans tablosu yok: {yol}. Eksik tablo yerine sıfır frekans "
            "kullanılmaz; `semayi_uret --cgga` ile üretin."
        )
    tablo = json.loads(yol.read_text())
    if tablo.get("feature") != "cgga_missense_frekans":
        raise CikarimHatasi(f"Beklenmeyen CGGA tablosu içeriği: {yol}")
    return tablo


# ---------------------------------------------------------------------------
def dizilimi_dogrula(dizilim: str | None, gen: str) -> str:
    """Protein dizilimini canlı kullanım için doğrular."""
    if not dizilim:
        raise CikarimHatasi(
            f"{gen}: protein dizilimi verilmedi. Canlı çıkarım sentetik "
            "kontekst üretmez; kanonik dizilim girdide taşınmalıdır."
        )
    temiz = dizilim.strip().upper()
    izinsiz = sorted(set(temiz) - set(config.STANDART_AA))
    if izinsiz:
        raise CikarimHatasi(
            f"{gen}: protein diziliminde standart olmayan harf var: {izinsiz}. "
            "'X' dolgusu eğitim hattındaki sentetik kontekst yoludur ve canlıda "
            "yasaktır."
        )
    if len(temiz) < 2:
        raise CikarimHatasi(f"{gen}: protein dizilimi çok kısa ({len(temiz)}).")
    return temiz


def varyanti_ayristir(girdi: VaryantGirdisi) -> tuple[str, int, str]:
    ayrisim = hgvsp_ayristir(girdi.protein_degisim)
    if ayrisim is None:
        raise CikarimHatasi(
            f"{girdi.gen}: '{girdi.protein_degisim}' standart missense biçiminde "
            "değil (beklenen 'p.R132H' veya 'p.Arg132His'). Nonsense/frameshift/"
            "indel varyantları bu model için kapsam dışıdır."
        )
    return ayrisim


# ---------------------------------------------------------------------------
def _esm_skorlayici_al(esm_skorlayici=None):
    if esm_skorlayici is not None:
        return esm_skorlayici
    try:
        from .moduller.ozellik_cikarimi import ESM2Skorlayici
    except ImportError as exc:
        raise CikarimHatasi(
            f"ESM-2 bağımlılıkları yüklenemedi ({exc}). ESM özelliği sıfırlanarak "
            "tahmin üretilmez."
        ) from exc
    return ESM2Skorlayici()


def ozellikleri_uret(
    girdi: VaryantGirdisi,
    sema: dict[str, Any],
    cgga_tablo: dict[str, Any],
    esm_skorlayici=None,
) -> tuple[dict[str, float], list[str]]:
    """Tek varyant için şemadaki sırada özellik sözlüğü üretir."""
    notlar: list[str] = []
    wt, pozisyon, mut = varyanti_ayristir(girdi)
    dizilim = dizilimi_dogrula(girdi.protein_dizilim, girdi.gen)

    if not 1 <= pozisyon <= len(dizilim):
        raise CikarimHatasi(
            f"{girdi.gen}: pozisyon {pozisyon} dizilim uzunluğunun ({len(dizilim)}) "
            "dışında."
        )
    if dizilim[pozisyon - 1] != wt:
        raise CikarimHatasi(
            f"{girdi.gen} {girdi.protein_degisim}: bildirilen vahşi tip '{wt}' ile "
            f"dizilimdeki '{dizilim[pozisyon - 1]}' uyuşmuyor. İzoform veya "
            "numaralandırma farkı olabilir; tahmin üretilmedi."
        )

    ozellik = dict(aaindex_delta_hesapla(wt, mut))

    # --- ESM-2 zorunlu ---
    skorlayici = _esm_skorlayici_al(esm_skorlayici)
    try:
        llr = float(skorlayici.llr_hesapla(dizilim, pozisyon, wt, mut))
    except Exception as exc:                       # yükleme/çalışma hatası
        raise CikarimHatasi(f"ESM-2 skoru üretilemedi: {exc}") from exc
    if llr == 0.0:
        raise CikarimHatasi(
            "ESM-2 tam 0.0 döndürdü. Eğitim hattında bu değer 'skor üretilemedi' "
            "durumunun sessiz karşılığıdır; canlıda nötr özellik yerine hata verilir."
        )
    ozellik["esm_llr"] = llr
    ozellik["esm_pathojenite"] = -llr

    # --- Eğitimde sabit kalan özellikler ---
    sabitler = sema.get("constantInTraining", {})
    for ad, deger in sabitler.items():
        ozellik[ad] = float(deger)
        notlar.append(
            f"{ad} eğitimde sabit {deger} idi; model bu özellikten sinyal "
            "öğrenmedi ve çıkarımda aynı sabit kullanıldı."
        )

    # --- CGGA gen frekansı ---
    frekanslar = cgga_tablo.get("frequencies", {})
    if girdi.gen in frekanslar:
        ozellik["cgga_missense_frekans"] = float(frekanslar[girdi.gen])
    else:
        ozellik["cgga_missense_frekans"] = 0.0
        notlar.append(
            f"{girdi.gen} CGGA kohortunda missense taşıyan örnek bulundurmuyor; "
            "frekans 0.0 (eğitimde de aynı doldurma uygulandı)."
        )

    ozellik["nispi_pozisyon"] = pozisyon / len(dizilim)

    sira = list(sema["featureOrder"])
    eksik = [k for k in sira if k not in ozellik]
    fazla = [k for k in ozellik if k not in sira]
    if eksik or fazla:
        raise CikarimHatasi(
            f"Özellik kümesi şemayla uyuşmuyor. Eksik={eksik} Fazla={fazla}"
        )
    return {k: float(ozellik[k]) for k in sira}, notlar


# ---------------------------------------------------------------------------
def model_yukle(sema: dict[str, Any], yol: Path = MODEL_YOLU):
    """Eğitilmiş modeli okur ve özellik adlarını şemayla karşılaştırır."""
    if not yol.exists():
        raise CikarimHatasi(f"Model dosyası yok: {yol}")
    try:
        import xgboost as xgb
    except ImportError as exc:
        raise CikarimHatasi(f"xgboost kurulu değil: {exc}") from exc

    model = xgb.XGBClassifier()
    model.load_model(str(yol))
    adlar = getattr(model, "feature_names_in_", None)
    if adlar is None:
        adlar = model.get_booster().feature_names
    if adlar is not None and list(adlar) != list(sema["featureOrder"]):
        raise CikarimHatasi(
            "Model özellik adları şemayla uyuşmuyor.\n"
            f"  model : {list(adlar)}\n  şema  : {list(sema['featureOrder'])}"
        )
    if adlar is None:
        LOG.warning("Model özellik adı bildirmiyor; sıra yalnızca şemadan alındı.")
    return model


def varyanti_skorla(
    girdi: VaryantGirdisi,
    sema: dict[str, Any] | None = None,
    cgga_tablo: dict[str, Any] | None = None,
    model=None,
    esm_skorlayici=None,
) -> CikarimSonucu:
    """Tek varyant için patojenite olasılığı üretir. Eğitim tetiklemez."""
    sema = sema or sema_yukle()
    cgga_tablo = cgga_tablo or cgga_tablosu_yukle()
    ozellik, notlar = ozellikleri_uret(girdi, sema, cgga_tablo, esm_skorlayici)

    model = model or model_yukle(sema)
    import numpy as np

    vektor = np.asarray([[ozellik[k] for k in sema["featureOrder"]]], dtype=float)
    olasilik = float(model.predict_proba(vektor)[0, 1])
    esik = float(sema["decisionThreshold"])

    return CikarimSonucu(
        gen=girdi.gen,
        protein_degisim=girdi.protein_degisim,
        olasilik=olasilik,
        sinif=int(olasilik >= esik),
        esik=esik,
        ozellikler=ozellik,
        model={
            "modelId": sema["modelId"],
            "modelVersion": sema["modelVersion"],
            "esmModel": sema.get("esmModel"),
            "featureNamesVerifiedFromModel": sema.get(
                "featureNamesVerifiedFromModel", False),
        },
        notlar=notlar,
    )


# ---------------------------------------------------------------------------
def girdi_dosyasindan(yol: Path) -> VaryantGirdisi:
    """``genomics-input.v1`` biçimindeki input.json dosyasını okur."""
    veri = json.loads(yol.read_text())
    if veri.get("schemaVersion") != 1 or veri.get("module") != "genomics":
        raise CikarimHatasi(
            f"{yol}: genomics/schemaVersion 1 girdisi beklendi "
            f"(module={veri.get('module')!r})."
        )
    if veri.get("disease") != "glioma-variant-pathogenicity":
        raise CikarimHatasi(f"{yol}: desteklenmeyen hastalık profili "
                            f"{veri.get('disease')!r}.")
    if veri.get("files"):
        raise CikarimHatasi(f"{yol}: genomik girdi dosya taşımaz.")
    varyant = veri.get("variant") or {}
    return VaryantGirdisi(
        gen=varyant.get("gene", ""),
        protein_degisim=varyant.get("proteinChange", ""),
        protein_dizilim=varyant.get("proteinSequence"),
        uniprot_erisim=varyant.get("uniprotAccession"),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tek varyant patojenite çıkarımı")
    p.add_argument("--girdi", type=Path, help="genomics-input.v1 biçiminde input.json")
    p.add_argument("--gen", help="Gen sembolü (--girdi yerine)")
    p.add_argument("--degisim", help="Protein değişimi, örn. p.R132H")
    p.add_argument("--dizilim-dosyasi", type=Path,
                   help="Kanonik protein dizilimini içeren düz metin dosyası")
    p.add_argument("--cikti", type=Path, help="report.json yazılacak dizin")
    arg = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")

    if arg.girdi:
        girdi = girdi_dosyasindan(arg.girdi)
    elif arg.gen and arg.degisim and arg.dizilim_dosyasi:
        girdi = VaryantGirdisi(
            gen=arg.gen,
            protein_degisim=arg.degisim,
            protein_dizilim=arg.dizilim_dosyasi.read_text().split(">")[-1]
                              .replace("\n", "").strip(),
        )
    else:
        p.error("--girdi ya da --gen + --degisim + --dizilim-dosyasi gerekli")

    try:
        sonuc = varyanti_skorla(girdi)
    except CikarimHatasi as exc:
        LOG.error("Çıkarım reddedildi: %s", exc)
        return 2

    rapor = sonuc.sozluk()
    metin = json.dumps(rapor, ensure_ascii=False, indent=2)
    if arg.cikti:
        arg.cikti.mkdir(parents=True, exist_ok=True)
        (arg.cikti / "report.json").write_text(metin + "\n")
        LOG.info("Yazıldı: %s", arg.cikti / "report.json")
    else:
        print(metin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
