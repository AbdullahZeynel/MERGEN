"""capture-baseline.sh on a fake host (see fake_host.py): it changes nothing,
writes only into a new private directory, never overwrites a baseline, and
records metadata without any secret, identity or spool content.

    python -m unittest discover -s infra/gpu-host -p 'test_*.py'
"""
import os
import re
import socket
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from fake_host import GPU_UUID, HERE, IDENTITY, PCI_BUS_ID, FakeHost
from test_gpu_host import MUTATING_PATTERNS

# Must never reach a baseline. Assembled at run time: nothing here looks like
# a credential or a real identity.
SECRET = "".join(("B", "4se", "line-", "z" * 36))
PATIENT = "sub-" + "sentinel-patient" + "_T1w.nii.gz"
HISTORY = "Commandline: apt-get install " + "sentinel-history-entry"


class BaselineCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-baseline-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.host = FakeHost(self.base)
        self.output = self.base / "baseline"

    def capture(self, output: Path | None = None) -> subprocess.CompletedProcess:
        command = ["bash", str(HERE / "capture-baseline.sh"), "--output", str(output or self.output),
                   "--root", str(self.host.root)]
        return subprocess.run(command, capture_output=True, text=True, env=self.host.environ())

    def assert_code(self, result: subprocess.CompletedProcess, code: int) -> None:
        self.assertEqual(result.returncode, code, result.stdout[-3000:] + result.stderr[-2000:])

    def record(self) -> str:
        return (self.output / "baseline.txt").read_text(encoding="utf-8")

    def write(self, absolute: str, text: str, mode: int = 0o644) -> Path:
        path = self.host.path(absolute)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        return path

    def lay_out_a_used_host(self) -> None:
        """What a host looks like after G0-G3, with secrets and job data in it."""
        self.host.write_env("dispatcher", f"MERGEN_WORKER_TOKEN={SECRET}\n")
        self.host.write_env("executor", f"MERGEN_RUNTIME_ROOT=/var/lib/mergen/runtime\n# {SECRET}\n")
        self.write("/usr/lib/sysusers.d/mergen.conf", (HERE / "sysusers.d" / "mergen.conf").read_text())
        self.write("/etc/systemd/system/mergen-executor.service", "[Service]\nExecStart=/bin/true\n")
        self.write("/etc/systemd/system/mergen-executor.service.d/override.conf",
                   f"[Service]\nEnvironment=MERGEN_CONTROL_TOKEN={SECRET}\n")
        self.write(f"/var/lib/mergen/runtime/jobs/{'a' * 32}/{PATIENT}", "voxels")
        self.write("/srv/mergen-models/imaging/sentinel-weights.pt", "weights")
        self.write("/opt/mergen/releases/r0/RELEASE", "version=r0\n")
        self.host.path("/opt/mergen/current").symlink_to("releases/r0")
        self.write("/var/log/apt/history.log", HISTORY + "\n")
        groups = self.host.load()["groups"]
        groups["mergen-svc"] = [990, ["mergen-dispatcher", "mergen-executor", "someone-else"]]
        self.host.set(groups=groups)


class ReadOnly(BaselineCase):
    def test_the_host_is_unchanged_and_the_output_is_private(self):
        self.lay_out_a_used_host()
        before = self.host.snapshot()
        result = self.capture()
        self.assert_code(result, 0)
        self.assertEqual(self.host.snapshot(), before)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(sorted(path.name for path in self.output.iterdir()), ["baseline.txt", "packages.txt"])
        for path in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
        self.assertEqual([call for call in self.host.calls() if call.startswith("chown")], [])
        self.assertEqual([call for call in self.host.calls()
                          if call.startswith("systemctl") and call.split()[1] not in ("is-enabled", "is-active")], [])

    def test_the_tool_holds_no_mutating_command_but_its_own_mkdir(self):
        code = []
        for line in (HERE / "capture-baseline.sh").read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            code.append(re.sub(r"""(['"])(?:\\.|(?!\1).)*\1""", "''", line))
        text = "\n".join(code)
        for pattern in MUTATING_PATTERNS:
            with self.subTest(pattern=pattern):
                if pattern == r"\bmkdir\b":
                    self.assertEqual(re.findall(r"\bmkdir\b.*", text), ["mkdir -m 700 -- '' || refuse ''"])
                else:
                    self.assertIsNone(re.search(pattern, text))


class OutputDirectory(BaselineCase):
    def test_a_second_capture_never_overwrites_the_first(self):
        self.assert_code(self.capture(), 0)
        first = {path.name: path.read_bytes() for path in self.output.iterdir()}
        result = self.capture()
        self.assert_code(result, 1)
        self.assertIn("a baseline is never overwritten", result.stderr)
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, first)

    def test_an_existing_directory_must_be_empty_and_private(self):
        empty = self.base / "empty-private"
        empty.mkdir(mode=0o700)
        empty.chmod(0o700)
        self.assert_code(self.capture(empty), 0)
        open_dir = self.base / "empty-open"
        open_dir.mkdir()
        open_dir.chmod(0o755)
        result = self.capture(open_dir)
        self.assert_code(result, 1)
        self.assertIn("open to other accounts", result.stderr)
        self.assertEqual(list(open_dir.iterdir()), [])
        link = self.base / "link"
        link.symlink_to(empty)
        self.assert_code(self.capture(link), 1)

    def test_the_output_must_be_an_absolute_path(self):
        self.assert_code(self.capture(Path("relative/baseline")), 2)


class Content(BaselineCase):
    def setUp(self):
        super().setUp()
        self.lay_out_a_used_host()
        self.result = self.capture()
        self.assert_code(self.result, 0)
        self.text = self.record() + (self.output / "packages.txt").read_text() + self.result.stdout + self.result.stderr

    def test_env_files_are_recorded_by_metadata_only(self):
        for service in ("dispatcher", "executor"):
            line = next(line for line in self.record().splitlines()
                        if line.startswith(f"/etc/mergen/{service}.env:"))
            self.assertEqual(line, f"/etc/mergen/{service}.env: file mode=640 owner=root:mergen-{service}")
        self.assertNotIn(SECRET, self.text)

    def test_no_identity_reaches_the_baseline(self):
        # The kernel release is recorded on purpose and may share a word with the
        # hostname; everything else must not carry it.
        text = "\n".join(line for line in self.text.splitlines() if not line.startswith("kernel="))
        for value in (GPU_UUID, PCI_BUS_ID, *IDENTITY.values(), socket.gethostname(), "someone-else"):
            self.assertNotIn(value, text)
        self.assertEqual([call for call in self.host.calls() if call.split()[0] in IDENTITY], [])
        gpu_calls = [call for call in self.host.calls() if call.startswith("nvidia-smi")]
        self.assertEqual(gpu_calls, ["nvidia-smi --query-gpu=index,name,driver_version,memory.total "
                                     "--format=csv,noheader"])
        self.assertIn("gpu 0: name=NVIDIA Test GPU driver=999.99.99 memory_total=16384 MiB", self.record())
        self.assertIn("group mergen-svc: present gid=990 mergen_members=mergen-dispatcher,mergen-executor "
                      "other_members=1", self.record())

    def test_spool_models_releases_and_apt_history_are_not_archived(self):
        for value in (PATIENT, "sentinel-weights", HISTORY, "voxels"):
            self.assertNotIn(value, self.text)
        record = self.record()
        self.assertIn("/var/lib/mergen/runtime: directory mode=2770 owner=mergen-dispatcher:mergen-svc entries=1",
                      record)
        self.assertIn("/srv/mergen-models: directory mode=750 owner=mergen:mergen-svc entries=1", record)
        self.assertIn("/opt/mergen/current: symlink to releases/r0", record)
        self.assertIn("releases=r0", record)
        self.assertIn("apt_history=present rotated=0", record)
        self.assertIn("package_manager=dpkg packages=2 (packages.txt)", record)

    def test_pre_existing_targets_are_recorded_as_metadata(self):
        record = self.record()
        self.assertIn("account mergen: present uid=1500 gid=1500", record)
        self.assertIn("account mergen-dispatcher: present uid=991 gid=991", record)
        self.assertRegex(record, r"(?m)^/usr/lib/sysusers\.d/mergen\.conf: file mode=644 owner=root:root "
                                 r"sha256=[0-9a-f]{64}$")
        self.assertIn("/etc/sudoers.d/mergen-maintenance: absent", record)
        dropin = "/etc/systemd/system/mergen-executor.service.d/override.conf: file mode=644 owner=root:root"
        self.assertIn(dropin + "\n", record)
        self.assertIn("unit mergen-executor.service: enabled=not-found active=inactive", record)


if __name__ == "__main__":
    unittest.main()
