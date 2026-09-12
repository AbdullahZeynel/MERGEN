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

import json
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
        from .moduller.on_isleme import hgvsp_ayristir

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
