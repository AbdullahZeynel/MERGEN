"""repo_guard kural testleri: neyi yakalamalı, neyi yakalamamalı."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repo_guard  # noqa: E402


def kurallar(metin: str) -> set[str]:
    return {b.rule for b in repo_guard.scan_text("x.py", metin)}


class YakalanmasiGerekenler(unittest.TestCase):
    def test_gercek_ip(self):
        self.assertIn("public-ip", kurallar("HOST = '203.0.114.9'"))

    def test_tailscale_makine_adresi(self):
        self.assertIn("public-ip", kurallar("worker 100.101.102.103"))

    def test_magic_dns(self):
        self.assertIn("tailscale-host", kurallar("https://mergen-gpu.tail1234.ts.net/api"))

    def test_dolu_token(self):
        self.assertIn("secret-value", kurallar('MERGEN_CONTROL_TOKEN = "s3cret-value-32-characters-long"'))

    def test_ozel_anahtar(self):
        self.assertIn("private-key", kurallar("-----BEGIN OPENSSH PRIVATE KEY-----"))

    def test_ssh_acik_anahtar(self):
        self.assertIn("ssh-key", kurallar("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabcdefghij deploy@host"))

    def test_bulgu_degeri_yazdirmaz(self):
        gizli = "s3cret-value-32-characters-long"
        rapor = " ".join(str(b) for b in repo_guard.scan_text("x.py", f'TOKEN = "{gizli}"'))
        self.assertNotIn(gizli, rapor)


class YakalanmamasiGerekenler(unittest.TestCase):
    def test_yerel_adresler(self):
        self.assertEqual(kurallar("uvicorn --host 127.0.0.1 --port 9000 # 0.0.0.0 ve 192.168.1.5"), set())

    def test_tailscale_ag_literali(self):
        self.assertEqual(kurallar('ipaddress.ip_network("100.64.0.0/10")'), set())

    def test_belge_ip_araligi(self):
        self.assertEqual(kurallar("örnek: 192.0.2.10 ve 203.0.113.7"), set())

    def test_bos_ornek_degerler(self):
        self.assertEqual(kurallar('MERGEN_CONTROL_TOKEN=""\nAPI_KEY="<VPS_TOKEN>"\nPASSWORD="changeme"'), set())

    def test_kod_ifadesi_sir_degil(self):
        self.assertEqual(kurallar('token = os.environ.get("MERGEN_CONTROL_TOKEN", "")'), set())

    def test_tokenizer_yanlis_pozitif_degil(self):
        self.assertEqual(kurallar('self._tokenizer = AutoTokenizer.from_pretrained("facebook/esm2")'), set())

    def test_surum_numarasi(self):
        self.assertEqual(kurallar("fastapi==0.141.1 # 1.30.0"), set())

    def test_allow_yorumu_satiri_atlar(self):
        self.assertEqual(kurallar('TOKEN = "s3cret-value-32-characters-long"  # repo-guard: allow'), set())


class DosyaKurallari(unittest.TestCase):
    def test_buyuk_dosya_ve_agirlik_uzantisi(self):
        with tempfile.TemporaryDirectory() as ad:
            kok = Path(ad)
            agirlik = kok / "model.pt"
            agirlik.write_bytes(b"0" * 16)
            kurallar_ = {b.rule for b in repo_guard.scan_file(agirlik, kok)}
            self.assertIn("bulk-file", kurallar_)

            buyuk = kok / "veri.csv"
            buyuk.write_bytes(b"0" * (repo_guard.MAX_BYTES + 1))
            self.assertIn("large-file", {b.rule for b in repo_guard.scan_file(buyuk, kok)})

    def test_ikili_dosya_coku_atlar(self):
        with tempfile.TemporaryDirectory() as ad:
            kok = Path(ad)
            ikili = kok / "resim.png"
            ikili.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
            self.assertEqual(repo_guard.scan_file(ikili, kok), [])


if __name__ == "__main__":
    unittest.main()
