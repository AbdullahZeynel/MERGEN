"""
Genomik Demo Vakalarını Üretir
===============================

`fixtures/varyantlar.json` içindeki kamuya açık varyantları çıkarım
adaptöründen geçirir ve demo paketinin genomik koleksiyonunu yazar:

    <çıktı>/genomics/glioma-variant-pathogenicity/
      manifest.json
      cases/<case-id>/{input.json, result.json, explanation.json}

Sonuçlar uydurulmaz; her biri gerçek ESM-2 + XGBoost çıktısıdır. Model
ağırlığı yerelden yüklenir, ağa çıkılmaz (bkz. `esm_yerel`). Eğitim
tetiklenmez.

    python -m VeriOdakliCozum.demo_uret --cikti .local/demo-v3-genomik
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import config
from .cikarim import (CikarimHatasi, VaryantGirdisi, cgga_tablosu_yukle,
                      dizilim_oku, model_yukle, sema_yukle, varyanti_skorla)
from .esm_yerel import varlik_kaydi

LOG = logging.getLogger("DEMO")

MODUL = "genomics"
HASTALIK = "glioma-variant-pathogenicity"
FIXTURE_DIZINI = config.PROJE_KOKU / "fixtures"
VARYANT_KATALOGU = FIXTURE_DIZINI / "varyantlar.json"


def girdi_belgesi(kayit: dict, dizilim: str) -> dict:
    """docs/contracts/genomics-input.v1.example.json biçiminde girdi."""
    return {
        "schemaVersion": 1,
        "module": MODUL,
        "disease": HASTALIK,
        "files": [],
        "variant": {
            "gene": kayit["gene"],
            "proteinChange": kayit["proteinChange"],
            "proteinSequence": dizilim,
            "uniprotAccession": kayit["kaynak"]["erisim"],
        },
    }


def vaka_yaz(hedef: Path, kayit: dict, sonuc, dizilim: str) -> dict:
    """Bir vakanın üç dosyasını yazar ve manifest kaydını döndürür."""
    hedef.mkdir(parents=True, exist_ok=True)
    rapor = sonuc.sozluk(mod="demo")
    aciklama = rapor.pop("explanation")

    (hedef / "input.json").write_text(
        json.dumps(girdi_belgesi(kayit, dizilim), ensure_ascii=False, indent=2) + "\n")
    (hedef / "result.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=2) + "\n")
    (hedef / "explanation.json").write_text(
        json.dumps(aciklama, ensure_ascii=False, indent=2) + "\n")

    return {
        "schemaVersion": 3,
        "module": MODUL,
        "disease": HASTALIK,
        "caseId": kayit["caseId"],
        "id": kayit["caseId"],
        "source": kayit["kaynak"]["veritabani"],
        "mode": "demo",
        "status": "demo_ready",
        "modelId": rapor["modelId"],
        "modelVersion": rapor["modelVersion"],
        "inputKind": "variant",
        "hasPrediction": True,
        "hasGroundTruth": False,
        "gene": kayit["gene"],
        "proteinChange": kayit["proteinChange"],
        "reports": ["result", "explanation", "input"],
    }


def uret(cikti: Path, yalniz: list[str] | None = None) -> int:
    katalog = json.loads(VARYANT_KATALOGU.read_text(encoding="utf-8"))
    sema = sema_yukle()
    cgga = cgga_tablosu_yukle()
    model = model_yukle(sema)                     # tek sefer yüklenir
    from .esm_skorlayici import ESM2Skorlayici
    skorlayici = ESM2Skorlayici()                 # ağırlık bir kez belleğe alınır
    esm_bilgi = varlik_kaydi()
    LOG.info("ESM-2 revision=%s (çevrimdışı=%s)", esm_bilgi["revision"], esm_bilgi["offline"])

    kok = cikti / MODUL / HASTALIK
    if kok.exists():
        raise CikarimHatasi(f"{kok} zaten var; üzerine yazılmaz, yeni bir --cikti verin.")

    kayitlar = []
    for kayit in katalog["variants"]:
        if yalniz and kayit["caseId"] not in yalniz:
            continue
        dizilim = dizilim_oku(FIXTURE_DIZINI / kayit["kaynak"]["dosya"])
        girdi = VaryantGirdisi(kayit["gene"], kayit["proteinChange"], dizilim,
                               kayit["kaynak"]["erisim"])
        sonuc = varyanti_skorla(girdi, sema=sema, cgga_tablo=cgga, model=model,
                                esm_skorlayici=skorlayici)
        kayitlar.append(vaka_yaz(kok / "cases" / kayit["caseId"], kayit, sonuc, dizilim))
        LOG.info("%-12s olasılık=%.6f sınıf=%s esm_llr=%.6f",
                 kayit["caseId"], sonuc.olasilik,
                 "pathogenic" if sonuc.sinif else "benign",
                 sonuc.ozellikler["esm_llr"])

    if not kayitlar:
        raise CikarimHatasi("Hiç vaka üretilmedi.")

    manifest = {
        "schemaVersion": 3,
        "module": MODUL,
        "disease": HASTALIK,
        "modelId": sema["modelId"],
        "modelVersion": sema["modelVersion"],
        "esm": {"modelId": esm_bilgi["modelId"], "revision": esm_bilgi["revision"]},
        "decisionThreshold": sema["decisionThreshold"],
        "note": ("Kamuya açık referans varyantlar; hasta verisi yoktur. Sonuçlar "
                 "araştırma prototipi çıktısıdır, klinik karar için kullanılamaz."),
        "cases": kayitlar,
    }
    (kok / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    LOG.info("Manifest yazıldı: %s (%d vaka)", kok / "manifest.json", len(kayitlar))
    katalogu_guncelle(cikti)
    return len(kayitlar)


def katalogu_guncelle(cikti: Path) -> None:
    """Kök `catalog.json`'a genomik koleksiyonu ekler; görüntü girdisine dokunmaz.

    `prepare_demo.py` görüntü koleksiyonunu kendi ortamında üretir. İki üretici
    aynı paket kökünü paylaşır; bu işlev yalnız kendi satırını yazar ve tekrar
    çalıştırıldığında girdiyi çoğaltmaz.
    """
    yol = cikti / "catalog.json"
    katalog = json.loads(yol.read_text(encoding="utf-8")) if yol.is_file() else {}
    if katalog.get("schemaVersion") not in (None, 3):
        raise CikarimHatasi(f"{yol}: beklenen schemaVersion 3, bulunan "
                            f"{katalog.get('schemaVersion')}")
    girdiler = [g for g in katalog.get("collections", [])
                if not (g.get("module") == MODUL and g.get("disease") == HASTALIK)]
    girdiler.append({"module": MODUL, "disease": HASTALIK,
                     "manifest": f"{MODUL}/{HASTALIK}/manifest.json"})
    girdiler.sort(key=lambda g: (g.get("module", ""), g.get("disease", "")))
    yol.write_text(json.dumps({"schemaVersion": 3, "collections": girdiler},
                              ensure_ascii=False, indent=2) + "\n")
    LOG.info("Katalog güncellendi: %s (%d koleksiyon)", yol, len(girdiler))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Genomik demo koleksiyonu üretici")
    p.add_argument("--cikti", type=Path, required=True, help="demo paketi kökü")
    p.add_argument("--yalniz", nargs="*", help="yalnız bu vaka kimlikleri")
    arg = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")
    try:
        uret(arg.cikti, arg.yalniz)
    except CikarimHatasi as exc:
        LOG.error("Üretim durdu: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
