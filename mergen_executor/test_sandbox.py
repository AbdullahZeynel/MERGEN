from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mergen_executor.sandbox import DEVICE_NODES, confine_writes, supported

REPO = Path(__file__).resolve().parent.parent
UNIT = REPO / "infra/gpu-host/systemd/mergen-executor.service.example"

# Applies the confinement and reports what the kernel then allows. Every answer
# is an errno or "ok", so a rule that is too wide shows up as an extra "ok".
PROBE = """
import json, os, sys
from mergen_executor.sandbox import confine_writes
output, outside, devices, extra = sys.argv[1:5]
confine_writes(output, tuple(item for item in devices.split(",") if item))


def probe(action):
    try:
        action()
    except OSError as error:
        return error.errno
    return "ok"


print(json.dumps({
    "output-write": probe(lambda: open(os.path.join(output, "result"), "w").close()),
    "outside-write": probe(lambda: open(outside, "w").close()),
    "null-rdwr": probe(lambda: os.close(os.open("/dev/null", os.O_RDWR))),
    "null-read": probe(lambda: os.close(os.open("/dev/null", os.O_RDONLY))),
    "zero-rdwr": probe(lambda: os.close(os.open("/dev/zero", os.O_RDWR))),
    "dev-create": probe(lambda: os.close(os.open("/dev/mergen-probe",
                                                 os.O_CREAT | os.O_WRONLY, 0o600))),
    "dev-unlink": probe(lambda: os.unlink("/dev/null")),
    "extra-rdwr": probe(lambda: os.close(os.open(extra, os.O_RDWR))),
}))
"""

DENIED = 13  # EACCES


class DeviceBoundary(unittest.TestCase):
    """The GPU exception is one named node, not an opening of /dev.

    /dev/null stands in for an NVIDIA node so the boundary is measured against
    the real kernel on a machine with no GPU.
    """

    def setUp(self):
        if not supported():
            self.skipTest("Linux Landlock is unavailable")
        temporary = tempfile.TemporaryDirectory(prefix="mergen-sandbox-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.output = self.base / "output"
        self.output.mkdir()
        self.outside = self.base / "outside"

    def confine(self, devices, extra="/dev/null") -> dict:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPO)
        result = subprocess.run(
            [sys.executable, "-c", PROBE, str(self.output), str(self.outside),
             ",".join(str(device) for device in devices), str(extra)],
            capture_output=True, text=True, env=environment, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_a_named_device_is_writable_and_the_rest_of_dev_is_not(self):
        report = self.confine(("/dev/null",))
        self.assertEqual(report["null-rdwr"], "ok")
        self.assertEqual(report["output-write"], "ok")
        # Naming one node must not open its directory: no neighbour, no new
        # entry in /dev and no removal of the node itself.
        self.assertEqual(report["zero-rdwr"], DENIED)
        self.assertEqual(report["dev-create"], DENIED)
        self.assertEqual(report["dev-unlink"], DENIED)
        # And the write confinement itself is still in force.
        self.assertEqual(report["outside-write"], DENIED)

    def test_without_its_rule_the_same_device_is_closed_but_readable(self):
        report = self.confine(())
        self.assertEqual(report["null-rdwr"], DENIED)
        self.assertEqual(report["null-read"], "ok")
        self.assertEqual(report["output-write"], "ok")

    def test_only_a_real_character_device_is_granted(self):
        regular = self.base / "not-a-device"
        regular.write_bytes(b"")
        link = self.base / "link-to-null"
        link.symlink_to("/dev/null")
        report = self.confine((regular, link), extra=regular)
        # A path that is not a character device gets no rule, and a symlink is
        # refused rather than followed to the node it names.
        self.assertEqual(report["extra-rdwr"], DENIED)
        self.assertEqual(report["null-rdwr"], DENIED)
        self.assertEqual(report["output-write"], "ok")

    def test_a_missing_node_costs_nothing_and_grants_nothing(self):
        report = self.confine(("/dev/nvidia-does-not-exist", "/dev/null"))
        self.assertEqual(report["null-rdwr"], "ok")
        self.assertEqual(report["zero-rdwr"], DENIED)

    def test_the_device_list_matches_the_unit_and_stays_compute_only(self):
        allowed = set(re.findall(r"^DeviceAllow=(\S+) rw$", UNIT.read_text(encoding="utf-8"),
                                 flags=re.MULTILINE))
        self.assertEqual(set(DEVICE_NODES), allowed)
        for unwanted in ("/dev/dri", "/dev/nvidia-modeset"):
            self.assertNotIn(unwanted, DEVICE_NODES)

    def test_the_runner_is_confined_with_that_list_by_default(self):
        # The tests above name their own devices, so the production default is
        # asserted here: without it the model silently finds no GPU.
        default = inspect.signature(confine_writes).parameters["devices"].default
        self.assertEqual(default, DEVICE_NODES)


if __name__ == "__main__":
    unittest.main()
