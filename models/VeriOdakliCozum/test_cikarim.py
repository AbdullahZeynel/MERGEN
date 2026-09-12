"""
Çıkarım adaptörü testleri
==========================

İki katman:

* Varlık gerektirmeyen testler — şema (Git'te) dışında dosya istemez, ESM-2
  yerine sahte skorlayıcı kullanır. Girdi doğrulama, özellik sırası ve sabit
  fixture burada kilitlenir.
* ``ozellik_matrisi.csv`` varsa çalışan yeniden üretim testi — adaptörün
  ürettiği AAindex/CGGA/pozisyon değerlerinin eğitim matrisiyle birebir aynı
  olduğunu doğrular. Matris Git dışıdır; yoksa test atlanır.

Çalıştırma (repo kökünden):

    python -m unittest VeriOdakliCozum.test_cikarim -v
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import config
from .cikarim import (CikarimHatasi, VaryantGirdisi, ozellikleri_uret,
                      sema_yukle, varyanti_ayristir)

MATRIS_YOLU = config.VERI_DIZINI / "ozellik_matrisi.csv"

# Test tablosu: gerçek CGGA tablosu Git dışı olduğu için testler kendi
# tablosunu enjekte eder. Değerler gerçek tablodan alınmıştır (IDH1, TP53).
CGGA_TEST_TABLOSU = {
    "schemaVersion": 1,
    "feature": "cgga_missense_frekans",
    "frequencies": {"IDH1": 0.465034965035, "TP53": 0.374125874126},
}

# Sabit fixture: 20 amino asitlik sentetik test dizilimi (biyolojik iddia
# taşımaz, yalnızca belirlenimciliği kilitler). ESM sahte skorlayıcıdan gelir.
FIXTURE_DIZILIM = "ACDEFGHIKLMNPQRSTVWY"
FIXTURE_LLR = -1.25


class SahteESM:
    """llr_hesapla sözleşmesini taklit eder; model yüklemez."""

    def __init__(self, llr: float = FIXTURE_LLR):
        self.llr = llr
        self.cagrilar: list[tuple] = []

    def llr_hesapla(self, dizilim, poz, wt, mut):
        self.cagrilar.append((dizilim, poz, wt, mut))
        return self.llr


class SemaTesti(unittest.TestCase):
    def test_sema_15_ozellik_ve_sira(self):
        sema = sema_yukle()
        self.assertEqual(sema["schemaVersion"], 1)
        self.assertEqual(len(sema["featureOrder"]), 15)
        self.assertEqual(sema["featureOrder"][0], "delta_hidrofobiklik")
        self.assertEqual(sema["featureOrder"][-1], "nispi_pozisyon")
        self.assertEqual(sema["decisionThreshold"], 0.5)
        self.assertIn("cosmic_frekans_log", sema["constantInTraining"])

    def test_eksik_sema_dosyasi_hata(self):
        with self.assertRaises(CikarimHatasi):
            sema_yukle(Path("/olmayan/sema.json"))


class GirdiDogrulamaTesti(unittest.TestCase):
    def setUp(self):
        self.sema = sema_yukle()

    def _uret(self, **kwargs):
        temel = dict(gen="IDH1", protein_degisim="p.R132H",
                     protein_dizilim=FIXTURE_DIZILIM)
        temel.update(kwargs)
        return ozellikleri_uret(VaryantGirdisi(**temel), self.sema,
                                CGGA_TEST_TABLOSU, SahteESM())

    def test_missense_olmayan_degisim_reddedilir(self):
        for degisim in ("p.R132*", "p.Arg132Ter", "c.395G>A", "R132H", "p.R132del"):
            with self.subTest(degisim=degisim), self.assertRaises(CikarimHatasi):
                varyanti_ayristir(VaryantGirdisi("IDH1", degisim, FIXTURE_DIZILIM))

    def test_uc_harfli_biçim_kabul_edilir(self):
        self.assertEqual(
            varyanti_ayristir(VaryantGirdisi("IDH1", "p.Arg132His", FIXTURE_DIZILIM)),
            ("R", 132, "H"),
        )

    def test_dizilim_yoksa_hata(self):
        with self.assertRaises(CikarimHatasi) as ctx:
            self._uret(protein_dizilim=None)
        self.assertIn("sentetik", str(ctx.exception))

    def test_x_dolgusu_reddedilir(self):
        with self.assertRaises(CikarimHatasi) as ctx:
            self._uret(protein_degisim="p.A1C", protein_dizilim="AXXXXCDEF")
        self.assertIn("'X'", str(ctx.exception))

    def test_pozisyon_dizilim_disinda_hata(self):
        with self.assertRaises(CikarimHatasi) as ctx:
            self._uret(protein_degisim="p.R500H")
        self.assertIn("dışında", str(ctx.exception))

    def test_vahsi_tip_uyusmazligi_hata(self):
        # 1. pozisyon 'A'; 'R' bildirmek uyuşmazlıktır
        with self.assertRaises(CikarimHatasi) as ctx:
            self._uret(protein_degisim="p.R1H")
        self.assertIn("uyuşmuyor", str(ctx.exception))

    def test_esm_sifir_donerse_hata(self):
        with self.assertRaises(CikarimHatasi) as ctx:
            ozellikleri_uret(
                VaryantGirdisi("IDH1", "p.A1C", FIXTURE_DIZILIM),
                self.sema, CGGA_TEST_TABLOSU, SahteESM(llr=0.0),
            )
        self.assertIn("0.0", str(ctx.exception))

    def test_cgga_tablosu_sozlesmesi(self):
        with self.assertRaises(CikarimHatasi):
            from .cikarim import cgga_tablosu_yukle
            cgga_tablosu_yukle(Path("/olmayan/cgga.json"))


class OzellikVektoruTesti(unittest.TestCase):
    def setUp(self):
        self.sema = sema_yukle()

    def test_fixture_vektoru_sabit(self):
        esm = SahteESM()
        ozellik, notlar = ozellikleri_uret(
            VaryantGirdisi("IDH1", "p.A1C", FIXTURE_DIZILIM),
            self.sema, CGGA_TEST_TABLOSU, esm,
        )
        self.assertEqual(list(ozellik), self.sema["featureOrder"])
        beklenen = {
            "delta_hidrofobiklik": 0.7,
            "delta_hacim": 19.9,
            "delta_polarite": -2.6,
            "delta_izoelektrik": -0.93,
            "delta_yuk": 0.0,
            "delta_esneklik": -0.011,
            "delta_yuzey_erisim": -5.7,
            "delta_heliks_tercihi": -0.72,
            "delta_beta_tercihi": 0.36,
            "grantham_yakl": 6.92882,   # 2.6*1.833 + 19.9*0.1018 + 0.7*0.196
            "esm_llr": FIXTURE_LLR,
            "esm_pathojenite": -FIXTURE_LLR,
            "cosmic_frekans_log": 0.0,
            "cgga_missense_frekans": 0.465034965035,
            "nispi_pozisyon": 1 / 20,
        }
        for ad, deger in beklenen.items():
            self.assertAlmostEqual(ozellik[ad], deger, places=6, msg=ad)
        # ESM'e gönderilen argümanlar dizilimi ve 1-tabanlı pozisyonu korur
        self.assertEqual(esm.cagrilar, [(FIXTURE_DIZILIM, 1, "A", "C")])
        self.assertTrue(any("cosmic_frekans_log" in n for n in notlar))

    def test_cgga_disi_gen_sifir_ve_not(self):
        ozellik, notlar = ozellikleri_uret(
            VaryantGirdisi("ZZZ9", "p.A1C", FIXTURE_DIZILIM),
            self.sema, CGGA_TEST_TABLOSU, SahteESM(),
        )
        self.assertEqual(ozellik["cgga_missense_frekans"], 0.0)
        self.assertTrue(any("CGGA" in n for n in notlar))


@unittest.skipUnless(MATRIS_YOLU.exists(),
                     f"eğitim matrisi yok (Git dışı): {MATRIS_YOLU}")
class EgitimMatrisiYenidenUretimTesti(unittest.TestCase):
    """Adaptörün özellik tanımı eğitimde kullanılanla aynı mı?"""

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        cls.matris = pd.read_csv(MATRIS_YOLU)
        cls.sema = sema_yukle()

    def test_aaindex_kolonlari_birebir(self):
        from .moduller.aa_ozellikler import aaindex_delta_hesapla
        from .moduller.varyant_notasyonu import hgvsp_ayristir

        kolonlar = [k for k in self.sema["featureOrder"] if k.startswith("delta_")]
        kolonlar.append("grantham_yakl")
        maks_fark = 0.0
        for _, satir in self.matris.iterrows():
            ayrisim = hgvsp_ayristir(satir["protein_degisim"])
            self.assertIsNotNone(ayrisim, satir["protein_degisim"])
            wt, _, mut = ayrisim
            yeni = aaindex_delta_hesapla(wt, mut)
            for k in kolonlar:
                maks_fark = max(maks_fark, abs(yeni[k] - float(satir[k])))
        self.assertLess(maks_fark, 1e-9, f"maks fark {maks_fark}")

    def test_esm_kolonlari_ayna(self):
        toplam = (self.matris["esm_llr"] + self.matris["esm_pathojenite"]).abs().max()
        self.assertLess(float(toplam), 1e-12)

    def test_cosmic_kolonu_sabit(self):
        self.assertEqual(int(self.matris["cosmic_frekans_log"].nunique()), 1)
        self.assertEqual(float(self.matris["cosmic_frekans_log"].iloc[0]), 0.0)

    def test_cgga_tablosu_matrisle_uyusur(self):
        from .cikarim import cgga_tablosu_yukle
        from .cikarim import CGGA_TABLO_YOLU
        if not CGGA_TABLO_YOLU.exists():
            self.skipTest(f"CGGA tablosu yok: {CGGA_TABLO_YOLU}")
        frek = cgga_tablosu_yukle()["frequencies"]
        for gen, grup in self.matris.groupby("gen"):
            beklenen = float(grup["cgga_missense_frekans"].iloc[0])
            self.assertAlmostEqual(float(frek.get(str(gen), 0.0)), beklenen,
                                   places=12, msg=str(gen))


if __name__ == "__main__":
    unittest.main()


# ===========================================================================
# Gerçek çalışma zamanı testleri
# ===========================================================================
# Bu bölüm gerçek XGBoost modelini ve gerçek ESM-2 ağırlığını ister. Varlıklar
# Git dışıdır; yoksa testler gerekçesiyle atlanır (CI'da beklenen durum budur).

FIXTURE_YOLU = config.PROJE_KOKU / "fixtures" / "idh1_r132h.json"
FIXTURE_FASTA = config.PROJE_KOKU / "fixtures" / "IDH1_O75874.fasta"
EGITIM_MODULLERI = ("veri_indirme", "model_egitim", "degerlendirme", "rapor",
                    "gorseller", "shap_analiz", "on_isleme", "ozellik_cikarimi",
                    "pandas", "requests")


def _fixture() -> dict:
    return json.loads(FIXTURE_YOLU.read_text(encoding="utf-8"))


def _esm_hazir() -> bool:
    from .esm_yerel import ESMYokHatasi, kaynagi_coz
    try:
        return kaynagi_coz().yol is not None
    except ESMYokHatasi:
        return False


def _model_hazir() -> bool:
    from .cikarim import CGGA_TABLO_YOLU, MODEL_YOLU
    if not (MODEL_YOLU.is_file() and CGGA_TABLO_YOLU.is_file()):
        return False
    try:
        import xgboost  # noqa: F401
    except ImportError:
        return False
    return True


def _agsiz():
    """Ağ soketlerini kapatan bağlam yöneticisi: indirme denenirse patlar."""
    import socket
    from contextlib import contextmanager
    from unittest.mock import patch

    def _yasak(*args, **kwargs):
        raise AssertionError("çıkarım sırasında ağ bağlantısı denendi")

    @contextmanager
    def kapali():
        with patch.object(socket, "socket", _yasak), \
             patch.object(socket, "create_connection", _yasak):
            yield
    return kapali()


class CevrimdisiESMKaynagi(unittest.TestCase):
    """Varlık gerektirmez: çözümleyicinin yokluk davranışı."""

    def test_cache_yoksa_acik_hata(self):
        from unittest.mock import patch
        from . import esm_yerel
        with tempfile.TemporaryDirectory() as bos:
            with patch.object(esm_yerel, "_cache_adaylari", lambda: [Path(bos)]), \
                 patch.object(esm_yerel.config, "ESM_YEREL_YOL", None), \
                 patch.object(esm_yerel.config, "ESM_INDIRME_IZNI", False):
                with self.assertRaises(esm_yerel.ESMYokHatasi) as ctx:
                    esm_yerel.kaynagi_coz()
        self.assertIn("MERGEN_ESM_INDIRME_IZNI", str(ctx.exception))

    def test_yerel_yol_gecersizse_hata(self):
        from unittest.mock import patch
        from . import esm_yerel
        with tempfile.TemporaryDirectory() as bos:
            with patch.object(esm_yerel.config, "ESM_YEREL_YOL", bos):
                with self.assertRaises(esm_yerel.ESMYokHatasi) as ctx:
                    esm_yerel.kaynagi_coz()
        self.assertIn("config.json", str(ctx.exception))

    def test_indirme_varsayilan_olarak_kapali(self):
        self.assertFalse(config.ESM_INDIRME_IZNI,
                         "canlı çıkarım varsayılanı indirmeye izin vermemeli")


class EgitimAyrimi(unittest.TestCase):
    """Canlı çıkarım eğitim modüllerini ve ağ kütüphanesini yüklememeli."""

    def test_cikarim_importu_egitim_modulu_cekmiyor(self):
        betik = (
            "import sys, json;"
            "sys.path.insert(0, %r);"
            "import VeriOdakliCozum.cikarim;"
            "print(json.dumps(sorted(m for m in sys.modules "
            "if m.startswith('VeriOdakliCozum') or m in ('pandas','requests'))))"
            % str(config.PROJE_KOKU.parent)
        )
        cikti = subprocess.run([sys.executable, "-c", betik], check=True,
                               capture_output=True, text=True).stdout
        yuklu = json.loads(cikti)
        for ad in EGITIM_MODULLERI:
            with self.subTest(modul=ad):
                self.assertFalse([m for m in yuklu if m.endswith(ad) or m == ad],
                                 f"{ad} çıkarım yolunda yüklenmemeli: {yuklu}")


@unittest.skipUnless(_model_hazir(), "model/CGGA tablosu veya xgboost yok (Git dışı varlık)")
class ModelSemaUyumu(unittest.TestCase):
    def test_model_kendi_ozellik_adlarini_bildiriyor(self):
        from .cikarim import model_yukle
        sema = sema_yukle()
        model = model_yukle(sema)
        adlar = getattr(model, "feature_names_in_", None)
        if adlar is None:
            adlar = model.get_booster().feature_names
        self.assertIsNotNone(adlar, "model özellik adı taşımıyor")
        self.assertEqual(list(adlar), list(sema["featureOrder"]))

    def test_sira_degisirse_cikarim_reddedilir(self):
        from .cikarim import CikarimHatasi, model_yukle
        bozuk = dict(sema_yukle())
        sira = list(bozuk["featureOrder"])
        sira[0], sira[1] = sira[1], sira[0]
        bozuk["featureOrder"] = sira
        with self.assertRaises(CikarimHatasi) as ctx:
            model_yukle(bozuk)
        self.assertIn("uyuşmuyor", str(ctx.exception))

    def test_sema_semasi_dogrulanmis_olarak_isaretli(self):
        sema = sema_yukle()
        self.assertTrue(sema["featureNamesVerifiedFromModel"])
        self.assertTrue(sema["traceColumnsVerifiedFromTrainingModule"])


@unittest.skipUnless(_model_hazir() and _esm_hazir(),
                     "model veya yerel ESM-2 ağırlığı yok (Git dışı varlık)")
class GercekFixture(unittest.TestCase):
    """IDH1 p.R132H: gerçek ESM-2 + gerçek XGBoost, ağ kapalı."""

    @classmethod
    def setUpClass(cls):
        from .cikarim import VaryantGirdisi, dizilim_oku, varyanti_skorla
        cls.f = _fixture()
        dizi = dizilim_oku(FIXTURE_FASTA)
        girdi = VaryantGirdisi(cls.f["girdi"]["gen"],
                               cls.f["girdi"]["proteinDegisim"], dizi)
        with _agsiz():                     # indirme denenirse test patlar
            cls.sonuc = varyanti_skorla(girdi)

    def test_fixture_dizilimi_kaynakla_uyusuyor(self):
        from .cikarim import dizilim_oku
        dizi = dizilim_oku(FIXTURE_FASTA)
        kaynak = self.f["kaynak"]
        self.assertEqual(len(dizi), kaynak["uzunluk"])
        self.assertEqual(dizi[131], kaynak["pozisyon132"])
        self.assertEqual(hashlib.sha256(dizi.encode()).hexdigest(),
                         kaynak["diziSha256"])

    def test_esm_llr_sabit(self):
        b = self.f["beklenen"]
        self.assertAlmostEqual(self.sonuc.ozellikler["esm_llr"], b["esmLlr"],
                               delta=b["esmLlrTolerans"])
        self.assertNotEqual(self.sonuc.ozellikler["esm_llr"], 0.0)

    def test_olasilik_ve_sinif_sabit(self):
        b = self.f["beklenen"]
        self.assertAlmostEqual(self.sonuc.olasilik, b["olasilik"],
                               delta=b["olasilikTolerans"])
        self.assertEqual(self.sonuc.esik, b["kararEsigi"])
        self.assertEqual("pathogenic" if self.sonuc.sinif else "benign", b["sinif"])

    def test_shap_toplamsalligi(self):
        b = self.f["beklenen"]
        a = self.sonuc.aciklama
        self.assertIsNotNone(a)
        self.assertEqual(a["space"], b["shapUzayi"])
        toplam = a["baseValue"] + sum(a["contributions"].values())
        self.assertAlmostEqual(toplam, a["rawMargin"],
                               delta=b["shapToplamsallikTolerans"])
        self.assertEqual(list(a["contributions"]), list(sema_yukle()["featureOrder"]))
        self.assertEqual(a["contributions"]["cosmic_frekans_log"], 0.0)

    def test_rapor_alanlari_makinece_okunabilir(self):
        rapor = self.sonuc.sozluk()
        self.assertEqual(rapor["module"], "genomics")
        self.assertIs(rapor["hasGroundTruth"], False)
        for alan in ("baseValue", "rawMargin", "contributions", "space", "method"):
            self.assertIn(alan, rapor["explanation"])
        json.dumps(rapor)              # serileştirilebilir olmalı
