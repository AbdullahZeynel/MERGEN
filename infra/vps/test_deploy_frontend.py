"""Run: python3 -m unittest discover -s infra/vps -p 'test_*.py'"""
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from deploy_frontend import install, rollback


class DeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mergen-deploy-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "site"

    def bundle(self, name, extra=None):
        archive = self.base / f"{name}.tar.gz"
        with tarfile.open(archive, 'w:gz') as tar:
            for path, data in [("./index.html", name.encode()), ("./assets/app.js", b"void 0;"), *(extra or [])]:
                entry = tarfile.TarInfo(path)
                entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data))
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_install_upgrade_rollback_preserves_both_releases(self):
        a, digest_a = self.bundle('first')
        b, digest_b = self.bundle('second')
        install(a, digest_a, self.root)
        install(b, digest_b, self.root)
        self.assertEqual((self.root / 'current/index.html').read_text(), 'second')
        rollback(self.root)
        self.assertEqual((self.root / 'current/index.html').read_text(), 'first')
        self.assertEqual((self.root / 'previous/index.html').read_text(), 'second')
        self.assertEqual((self.root / 'shared/assets/app.js').read_bytes(), b'void 0;')

    def test_checksum_failure_does_not_change_current(self):
        a, digest = self.bundle('first')
        install(a, digest, self.root)
        with self.assertRaises(ValueError):
            install(a, '0' * 64, self.root)
        self.assertEqual((self.root / 'current/index.html').read_text(), 'first')

    def test_traversal_and_secrets_are_rejected_before_activation(self):
        for unsafe in ['../escape', '/absolute', './.env']:
            with self.subTest(unsafe=unsafe):
                archive, digest = self.bundle('invalid', [(unsafe, b'bad')])
                with self.assertRaises(ValueError):
                    install(archive, digest, self.root)
                self.assertFalse((self.root / 'current').exists())

    def test_symlinks_are_rejected(self):
        archive = self.base / 'symlink.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            link = tarfile.TarInfo('linked')
            link.type = tarfile.SYMTYPE
            link.linkname = '/etc'
            tar.addfile(link)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            install(archive, digest, self.root)

    def test_conflicting_asset_cannot_replace_active_release(self):
        a, digest_a = self.bundle('first')
        install(a, digest_a, self.root)
        (self.root / 'shared/assets/app.js').write_bytes(b'existing different asset')
        b, digest_b = self.bundle('second')
        with self.assertRaises(ValueError):
            install(b, digest_b, self.root)
        self.assertEqual((self.root / 'current/index.html').read_text(), 'first')


if __name__ == '__main__':
    unittest.main()
