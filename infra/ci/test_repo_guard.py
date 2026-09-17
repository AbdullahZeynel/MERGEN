"""repo_guard kural testleri: neyi yakalamalı, neyi yakalamamalı.

Dosyadaki örnek sırlar bilinçlidir; guard kendi test verisini bulmasın diye
satır sonlarında `repo-guard: allow` yorumu vardır. Yorum yalnız kaynak satırı
etkiler, testin çalışma anında taradığı metni değil.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repo_guard  # noqa: E402


def kurallar(metin: str, yol: str = "x.py") -> set[str]:
    return {b.rule for b in repo_guard.scan_text(yol, metin)}


class YakalanmasiGerekenler(unittest.TestCase):
    def test_gercek_ip(self):
        self.assertIn("public-ip", kurallar("HOST = '203.0.114.9'"))  # repo-guard: allow

    def test_tailscale_makine_adresi(self):
        self.assertIn("public-ip", kurallar("worker 100.101.102.103"))  # repo-guard: allow

    def test_magic_dns(self):
        self.assertIn("tailscale-host", kurallar("https://gpu.tail1234.ts.net/api"))  # repo-guard: allow

    def test_dolu_token(self):
        self.assertIn("secret-value", kurallar('CONTROL_TOKEN = "s3cret-value-32-characters-long"'))  # repo-guard: allow

    def test_ozel_anahtar(self):
        self.assertIn("private-key", kurallar("-----BEGIN OPENSSH PRIVATE KEY-----"))  # repo-guard: allow

    def test_ssh_acik_anahtar(self):
        self.assertIn("ssh-key", kurallar("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabcdefghij a@b"))  # repo-guard: allow

    def test_saglayici_anahtarlari(self):
        ornekler = {
            "aws-access-key": "AKIA" + "Q" * 16,
            "github-token": "ghp_" + "b" * 36,
            "slack-token": "xoxb-" + "1" * 12,
            "huggingface-token": "hf_" + "c" * 30,
            "google-api-key": "AIza" + "d" * 35,
            "json-web-token": "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.dBjftJeZ4CVP-mB92K",  # repo-guard: allow
        }
        for kural, deger in ornekler.items():
            with self.subTest(kural=kural):
                self.assertIn(kural, kurallar(f"X = {deger}"))

    def test_bulgu_degeri_yazdirmaz(self):
        gizli = "s3cret-value-32-characters-long"
        rapor = " ".join(str(b) for b in repo_guard.scan_text("x.py", f'TOKEN = "{gizli}"'))
        self.assertNotIn(gizli, rapor)


class YakalanmamasiGerekenler(unittest.TestCase):
    def test_yerel_adresler(self):
        self.assertEqual(kurallar("uvicorn --host 127.0.0.1 # 0.0.0.0 ve 192.168.1.5"), set())

    def test_tailscale_ag_literali(self):
        self.assertEqual(kurallar('ipaddress.ip_network("100.64.0.0/10")'), set())

    def test_belge_ip_araligi(self):
        self.assertEqual(kurallar("örnek: 192.0.2.10 ve 203.0.113.7"), set())

    def test_surum_sabiti_adres_degil(self):
        self.assertEqual(kurallar("cuda-toolkit==13.0.3.0\nnvidia-cudnn-cu13==9.24.0.43"), set())

    def test_tek_esittir_hala_adres(self):
        # Only a version pin is exempt; an assignment is still an address.
        self.assertIn("public-ip", kurallar("HOST=203.0.114.9"))  # repo-guard: allow
        self.assertIn("public-ip", kurallar("worker 13.0.3.0"))  # repo-guard: allow

    def test_bos_ornek_degerler(self):
        self.assertEqual(kurallar('TOKEN=""\nAPI_KEY="<VPS_TOKEN>"\nPASSWORD="changeme"'), set())

    def test_kod_ifadesi_sir_degil(self):
        self.assertEqual(kurallar('token = os.environ.get("MERGEN_CONTROL_TOKEN", "")'), set())

    def test_tokenizer_yanlis_pozitif_degil(self):
        self.assertEqual(kurallar('self._tokenizer = AutoTokenizer.from_pretrained("facebook/esm2")'), set())

    def test_surum_ve_hash_benzeri_metin(self):
        self.assertEqual(kurallar('fastapi==0.141.1 # 1.30.0\n"integrity": "sha512-AAAA"'), set())

    def test_allow_yorumu_satiri_atlar(self):
        self.assertEqual(kurallar('TOKEN = "s3cret-value-32-characters-long"  # repo-guard: allow'), set())


class OrnekEnvDosyasi(unittest.TestCase):
    YOL = "infra/vps/services.env.example"

    def test_gercek_env_dosyasi_olarak_taninir(self):
        for yol in (".env.example", "services.env.example", "infra/vps/frontend.env.example",
                    "a/.env.local.example"):
            with self.subTest(yol=yol):
                self.assertTrue(repo_guard.is_env_example(yol))
        self.assertFalse(repo_guard.is_env_example("backend/api.py"))

    def test_bos_ve_yer_tutucu_degerler_serbest(self):
        metin = (
            "# yorum\n"
            "MERGEN_LIVE_ACCESS_HASH=\n"
            "MERGEN_CONTROL_TOKEN=\n"
            "MERGEN_RUNTIME_ROOT=/srv/mergen/runtime\n"
            "MERGEN_MAX_ACTIVE_SESSIONS=10\n"
            "MERGEN_COOKIE_SECURE=true\n"
            "MERGEN_MCP_URL=http://127.0.0.1:9010/mcp\n"
            "MERGEN_DOMAIN=<VPS_HOST>\n"
        )
        self.assertEqual(kurallar(metin, self.YOL), set())

    def test_dolu_sir_ornek_dosyada_reddedilir(self):
        self.assertIn("env-example-secret",
                      kurallar("MERGEN_CONTROL_TOKEN=abcdefghijklmnopqrstuvwx", self.YOL))
        self.assertIn("env-example-secret",
                      kurallar("MERGEN_LIVE_ACCESS_HASH=9f86d081884c7d65", self.YOL))

    def test_gercek_gorunen_deger_reddedilir(self):
        self.assertIn("env-example-value", kurallar("MERGEN_DOMAIN=mergen.gerceksite.dev", self.YOL))

    def test_bicimsiz_satir_ve_bos_dosya(self):
        self.assertIn("env-example-format", kurallar("bu bir atama degil", self.YOL))
        self.assertIn("env-example-empty", kurallar("# yalnız yorum\n", self.YOL))


class DosyaAdiKurallari(unittest.TestCase):
    def _kural(self, ad: str, icerik: bytes = b"x") -> set[str]:
        with tempfile.TemporaryDirectory() as klasor:
            kok = Path(klasor)
            hedef = kok / ad
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(icerik)
            return {b.rule for b in repo_guard.scan_file(hedef, kok)}

    def test_env_dosyasi_reddedilir(self):
        for ad in (".env", ".env.production", "backend/.env", "prod.env",
                   "deploy.pem", "server.key", ".netrc", "id_ed25519",
                   "credentials.json", "service-account-prod.json",
                   "terraform.tfstate", ".claude/settings.local.json"):
            with self.subTest(ad=ad):
                self.assertIn("secret-file", self._kural(ad))

    def test_ornek_dosyalar_serbest(self):
        for ad in ("infra/vps/services.env.example", ".env.example", ".env.local.example"):
            with self.subTest(ad=ad):
                self.assertNotIn("secret-file", self._kural(ad, b"KEY=\n"))

    def test_buyuk_dosya_ve_agirlik_uzantisi(self):
        self.assertIn("bulk-file", self._kural("model.pt", b"0" * 16))
        self.assertIn("large-file", self._kural("veri.csv", b"0" * (repo_guard.MAX_BYTES + 1)))

    def test_ikili_dosya_coku_atlar(self):
        self.assertEqual(self._kural("resim.png", b"\x89PNG\r\n\x1a\n\xff\xfe"), set())


class GitignoreKorumasi(unittest.TestCase):
    def test_eksik_desen_bildirilir(self):
        with tempfile.TemporaryDirectory() as klasor:
            kok = Path(klasor)
            (kok / ".gitignore").write_text(".env\n*.pem\n")
            kurallar_ = {b.rule for b in repo_guard.scan_gitignore(kok)}
            self.assertIn("gitignore-weakened", kurallar_)

    def test_tam_gitignore_temiz(self):
        with tempfile.TemporaryDirectory() as klasor:
            kok = Path(klasor)
            (kok / ".gitignore").write_text("\n".join(repo_guard.REQUIRED_IGNORES) + "\n")
            self.assertEqual(repo_guard.scan_gitignore(kok), [])

    def test_gitignore_yoksa_bulgu(self):
        with tempfile.TemporaryDirectory() as klasor:
            self.assertIn("gitignore-missing",
                          {b.rule for b in repo_guard.scan_gitignore(Path(klasor))})


if __name__ == "__main__":
    unittest.main()
