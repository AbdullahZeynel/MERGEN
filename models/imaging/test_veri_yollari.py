"""
Veri seti yol çözümü testleri
==============================

`evaluate_uwcse` ve `ensemble_inference`, TCIA indirmesindeki kanal adlarını
(`_bias`, `T1gad_bias`, aynı adlı klasör içinde dosya) doğru çözmeli ve eksik
kanallı vakayı değerlendirmeye almamalı. Testler torch/monai gerektirmez;
yalnız `prepare_example_dataset` içindeki adlandırma tablosunu kullanır.

    python3 -m unittest discover -s models/imaging -p 'test_*.py'
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

BURASI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "prepare_example_dataset", BURASI / "prepare_example_dataset.py")
pe = importlib.util.module_from_spec(_spec)
sys.modules["prepare_example_dataset"] = pe
_spec.loader.exec_module(pe)


def kur(kok: Path, vaka: str, adlar: list[str], icice: bool = False) -> Path:
    klasor = kok / f"{vaka}_nifti"
    klasor.mkdir(parents=True, exist_ok=True)
    for ad in adlar:
        if icice:
            (klasor / ad).mkdir(exist_ok=True)
            (klasor / ad / ad).write_bytes(b"x")
        else:
            (klasor / ad).write_bytes(b"x")
    return klasor


def tam_mi(klasor: Path, vaka: str) -> bool:
    found = pe.index_case(str(klasor), vaka)
    return bool(all(pe.pick(found, k) for k in pe.MODALITIES.values())
                and pe.pick(found, pe.LABEL_KEYS))


class KanalCozumu(unittest.TestCase):
    VAKA = "UCSF-PDGM-0026"

    def test_bias_ekli_duz_dosyalar(self):
        with tempfile.TemporaryDirectory() as ad:
            k = kur(Path(ad), self.VAKA, [
                f"{self.VAKA}_FLAIR_bias.nii", f"{self.VAKA}_T1_bias.nii",
                f"{self.VAKA}_T1c_bias.nii", f"{self.VAKA}_T2_bias.nii",
                f"{self.VAKA}_tumor_segmentation.nii"])
            self.assertTrue(tam_mi(k, self.VAKA))

    def test_ayni_adli_klasor_icindeki_dosya(self):
        with tempfile.TemporaryDirectory() as ad:
            k = kur(Path(ad), self.VAKA, [
                f"{self.VAKA}_FLAIR_bias.nii", f"{self.VAKA}_T1_bias.nii",
                f"{self.VAKA}_T1c_bias.nii", f"{self.VAKA}_T2_bias.nii",
                f"{self.VAKA}_tumor_segmentation.nii"], icice=True)
            self.assertTrue(tam_mi(k, self.VAKA))

    def test_t1gad_takma_adi_t1c_yerine_gecer(self):
        with tempfile.TemporaryDirectory() as ad:
            k = kur(Path(ad), self.VAKA, [
                f"{self.VAKA}_FLAIR_bias.nii", f"{self.VAKA}_T1_bias.nii",
                f"{self.VAKA}_T1gad_bias.nii", f"{self.VAKA}_T2_bias.nii",
                f"{self.VAKA}_tumor_segmentation.nii"])
            found = pe.index_case(str(k), self.VAKA)
            self.assertIsNotNone(pe.pick(found, pe.MODALITIES["T1c"]))
            self.assertTrue(tam_mi(k, self.VAKA))

    def test_gz_uzantisi_taninir(self):
        with tempfile.TemporaryDirectory() as ad:
            k = kur(Path(ad), self.VAKA, [
                f"{self.VAKA}_FLAIR_bias.nii.gz", f"{self.VAKA}_T1_bias.nii.gz",
                f"{self.VAKA}_T1c_bias.nii.gz", f"{self.VAKA}_T2_bias.nii.gz",
                f"{self.VAKA}_tumor_segmentation.nii.gz"])
            self.assertTrue(tam_mi(k, self.VAKA))

    def test_eksik_kanal_vakayi_disarida_birakir(self):
        for eksik in ("T1", "T2", "T1c", "FLAIR"):
            with self.subTest(eksik=eksik), tempfile.TemporaryDirectory() as ad:
                adlar = [f"{self.VAKA}_{m}_bias.nii"
                         for m in ("FLAIR", "T1", "T1c", "T2") if m != eksik]
                adlar.append(f"{self.VAKA}_tumor_segmentation.nii")
                k = kur(Path(ad), self.VAKA, adlar)
                self.assertFalse(tam_mi(k, self.VAKA))

    def test_etiket_eksikse_disarida_kalir(self):
        with tempfile.TemporaryDirectory() as ad:
            k = kur(Path(ad), self.VAKA, [
                f"{self.VAKA}_{m}_bias.nii" for m in ("FLAIR", "T1", "T1c", "T2")])
            self.assertFalse(tam_mi(k, self.VAKA))

    def test_baska_vakanin_dosyasi_sayilmaz(self):
        with tempfile.TemporaryDirectory() as ad:
            k = kur(Path(ad), self.VAKA, [
                f"{self.VAKA}_FLAIR_bias.nii", "UCSF-PDGM-9999_T1_bias.nii",
                f"{self.VAKA}_T1c_bias.nii", f"{self.VAKA}_T2_bias.nii",
                f"{self.VAKA}_tumor_segmentation.nii"])
            self.assertFalse(tam_mi(k, self.VAKA))


if __name__ == "__main__":
    unittest.main()
