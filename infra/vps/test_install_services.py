"""Installer upgrade safety. Run: python3 -m unittest discover -s infra/vps -p 'test_*.py'

The real installer needs root and changes the host, so it is checked in two
halves: the env checker it calls runs against temporary files, and the script
text is checked for its non-overwrite and ordering guarantees. Fixture values
are fake, and no assertion echoes file content.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHECKER = HERE / "check_services_env.py"
ENV_PATH = "/etc/mergen/services.env"
# Proves redaction only; it is not a credential.
CANARY = "canary-" + "q" * 40


def run_checker(text: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="mergen-env-test-") as tmp:
        env_file = Path(tmp) / "services.env"
        env_file.write_text(text, encoding="utf-8")
        result = subprocess.run([sys.executable, str(CHECKER), str(env_file)],
                                capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class ServicesEnvCheck(unittest.TestCase):
    def test_shipped_example_passes(self):
        code, _ = run_checker((HERE / "services.env.example").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)

    def test_demo_only_env_from_an_old_install_fails_with_names_only(self):
        code, output = run_checker(
            f"MERGEN_DEMO_ROOT=/srv/mergen/demo-{CANARY}\n"
            f"MERGEN_CONTROL_TOKEN={CANARY}\n")
        self.assertEqual(code, 1)
        self.assertIn("MERGEN_RUNTIME_ROOT", output)
        self.assertIn("MERGEN_DATABASE_PATH", output)
        self.assertFalse(CANARY in output, "the checker printed a value from the file")

    def test_blank_and_commented_settings_count_as_missing(self):
        code, output = run_checker(
            "MERGEN_RUNTIME_ROOT=\n"
            "# MERGEN_DATABASE_PATH=/srv/mergen/runtime/control.sqlite3\n")
        self.assertEqual(code, 1)
        self.assertEqual(output.count("is missing or empty"), 2)

    def test_relative_and_traversing_paths_fail(self):
        code, output = run_checker(
            "MERGEN_RUNTIME_ROOT=.local/runtime\n"
            "MERGEN_DATABASE_PATH=/srv/mergen/runtime/../control.sqlite3\n")
        self.assertEqual(code, 1)
        self.assertEqual(output.count("must be an absolute path"), 2)

    def test_database_outside_the_runtime_root_fails(self):
        code, output = run_checker(
            "MERGEN_RUNTIME_ROOT=/srv/mergen/runtime\n"
            "MERGEN_DATABASE_PATH=/var/tmp/control.sqlite3\n")
        self.assertEqual(code, 1)
        self.assertIn("inside MERGEN_RUNTIME_ROOT", output)

    def test_quotes_are_accepted_and_a_later_blank_assignment_wins(self):
        good = ('MERGEN_RUNTIME_ROOT="/srv/mergen/runtime"\n'
                "MERGEN_DATABASE_PATH='/srv/mergen/runtime/control.sqlite3'\n")
        self.assertEqual(run_checker(good)[0], 0)
        self.assertEqual(run_checker(good + "MERGEN_RUNTIME_ROOT=\n")[0], 1)

    def test_unreadable_file_fails_without_content(self):
        result = subprocess.run([sys.executable, str(CHECKER), "/nonexistent/services.env"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be read", result.stderr)


class InstallerScript(unittest.TestCase):
    def setUp(self):
        self.lines = (HERE / "install-services.sh").read_text(encoding="utf-8").splitlines()
        self.code = [line for line in self.lines if not line.lstrip().startswith("#")]

    def index_of(self, needle: str) -> int:
        matches = [number for number, line in enumerate(self.code) if needle in line]
        self.assertEqual(len(matches), 1, f"expected exactly one line containing {needle!r}")
        return matches[0]

    def test_existing_env_is_never_overwritten(self):
        redirect = re.compile(r">>?\s*['\"]?" + re.escape(ENV_PATH))
        writes = [number for number, line in enumerate(self.code)
                  if ENV_PATH in line and "check_services_env.py" not in line
                  and (re.search(r"\b(install|cp|mv|tee|sed)\b", line) or redirect.search(line))]
        self.assertEqual(len(writes), 1, "services.env must be written in exactly one place")
        guard = self.code[writes[0] - 1].strip()
        self.assertEqual(guard, f"if [[ ! -e {ENV_PATH} ]]; then")

    def test_env_check_runs_after_install_and_fails_the_run(self):
        reload = self.index_of("systemctl daemon-reload")
        check = self.index_of("check_services_env.py")
        done = self.index_of("echo 'Installed.")
        self.assertLess(reload, check)
        self.assertLess(check, done)
        self.assertTrue(self.code[check].strip().startswith("if ! "))
        self.assertIn("exit 1", "\n".join(self.code[check:done]))

    def test_installer_never_prints_or_sources_the_env(self):
        for line in self.code:
            if ENV_PATH not in line:
                continue
            with self.subTest(line=line.strip()[:50]):
                self.assertIsNone(re.search(r"\b(cat|less|head|tail|grep|source)\b|^\s*\.\s", line))

    def test_installer_starts_no_service(self):
        text = "\n".join(self.code)
        self.assertIsNone(re.search(r"systemctl\s+(enable|start|restart)\b", text))


def unit_exec(name: str) -> list[str]:
    for line in (HERE / name).read_text(encoding="utf-8").splitlines():
        if line.startswith("ExecStart="):
            return line.removeprefix("ExecStart=").split()
    raise AssertionError(f"{name} has no ExecStart")


class ServiceUnits(unittest.TestCase):
    """Run each backend unit's real command line against a copy of the
    installed layout, where WorkingDirectory holds the `backend/` package."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-unit-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.services = self.root / "services"
        (self.services / "backend").mkdir(parents=True)
        for source in (REPO / "backend").glob("*.py"):
            if not source.name.startswith("test_"):
                shutil.copy2(source, self.services / "backend" / source.name)

    def run_unit(self, name: str, extra_env: dict[str, str]):
        argv = unit_exec(name)
        self.assertEqual(argv[0], "/srv/mergen/services/.venv/bin/python")
        env = {"PATH": os.environ.get("PATH", ""), **extra_env}
        return subprocess.run([sys.executable, *argv[1:]], cwd=self.services, env=env,
                              capture_output=True, text=True, timeout=60)

    def test_backend_units_use_the_module_form(self):
        for name in ("mergen-api.service", "mergen-control.service", "mergen-cleanup.service"):
            argv = unit_exec(name)
            with self.subTest(unit=name):
                self.assertEqual(argv[1], "-m")
                self.assertTrue(argv[2] == "uvicorn" or argv[2].startswith("backend."))
                self.assertIn("WorkingDirectory=/srv/mergen/services",
                              (HERE / name).read_text(encoding="utf-8"))

    def test_cleanup_unit_command_imports_and_runs(self):
        result = self.run_unit("mergen-cleanup.service",
                               {"MERGEN_RUNTIME_ROOT": str(self.root / "runtime")})
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertIn("expiredSessions", result.stdout)

    def test_cleanup_unit_refuses_to_guess_under_systemd(self):
        result = self.run_unit("mergen-cleanup.service", {"INVOCATION_ID": "0" * 32})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MERGEN_RUNTIME_ROOT", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.services / ".local").exists(), "fell back to the checkout default")

    @unittest.skipUnless(importlib.util.find_spec("uvicorn"), "uvicorn is not installed")
    def test_control_unit_command_imports_before_validating(self):
        result = self.run_unit("mergen-control.service", {})
        self.assertEqual(result.returncode, 1)
        self.assertIn("MERGEN_CONTROL_HOST", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
