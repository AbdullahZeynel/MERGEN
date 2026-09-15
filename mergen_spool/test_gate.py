"""The finalization gate. Run: python -m unittest discover -s mergen_spool -t ."""
import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mergen_spool import contract
from mergen_spool.gate import GateBusy, GateMissing, create_gate, finalization_gate


class Gate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-gate-test-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "job"
        self.dir.mkdir()
        self.fd = self.open_directory()

    def open_directory(self) -> int:
        fd = os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        return fd

    def test_the_gate_is_created_once_and_names_its_version(self):
        create_gate(self.dir)
        self.assertEqual((self.dir / "gate").read_bytes(), b"mergen-spool-gate 1\n")
        self.assertEqual(stat.S_IMODE(os.stat(self.dir / "gate").st_mode) & 0o007, 0)
        with self.assertRaises(FileExistsError):
            create_gate(self.dir)

    def test_a_second_holder_is_excluded_until_the_gate_is_released(self):
        create_gate(self.dir)
        other = self.open_directory()
        with finalization_gate(self.fd, timeout=1):
            with self.assertRaises(GateBusy), finalization_gate(other, timeout=0.05):
                pass
        with finalization_gate(other, timeout=0.05):
            pass

    def test_a_waiting_holder_enters_as_soon_as_the_gate_is_released(self):
        create_gate(self.dir)
        order, entered, release = [], threading.Event(), threading.Event()

        def first():
            with finalization_gate(self.fd, timeout=1):
                order.append("first")
                entered.set()
                release.wait(5)

        holder = threading.Thread(target=first)
        holder.start()
        self.addCleanup(holder.join, 5)
        self.assertTrue(entered.wait(5))
        threading.Timer(0.05, release.set).start()
        started = time.monotonic()
        with finalization_gate(self.open_directory(), timeout=2):
            order.append("second")
        self.assertEqual(order, ["first", "second"])
        self.assertGreaterEqual(time.monotonic() - started, 0.04)

    def test_a_missing_linked_or_foreign_version_gate_is_refused(self):
        with self.assertRaises(GateMissing), finalization_gate(self.fd, timeout=0.01):
            pass
        (self.dir / "elsewhere").write_bytes(contract.GATE_CONTENT)
        (self.dir / "gate").symlink_to(self.dir / "elsewhere")
        with self.assertRaises(GateMissing), finalization_gate(self.fd, timeout=0.01):
            pass
        (self.dir / "gate").unlink()
        (self.dir / "gate").write_bytes(b"mergen-spool-gate 2\n")
        with self.assertRaises(GateMissing), finalization_gate(self.fd, timeout=0.01):
            pass


if __name__ == "__main__":
    unittest.main()
