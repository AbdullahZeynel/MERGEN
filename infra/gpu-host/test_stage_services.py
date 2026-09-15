"""stage-services.sh and verify-services.sh on a fake host (see fake_host.py).

Nothing here touches the real /opt, /etc, /var, an account, systemd or the
network. Root, systemd, pip and the accounts are fake commands; the scripts'
own logic, files, modes, links and renames are real.

    python -m unittest discover -s infra/gpu-host -p 'test_*.py'
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fake_host import HERE, REPO, FakeHost

# Must never reach any output. Assembled at run time: no literal in this file
# looks like a credential or a real address.
SECRET = "".join(("S", "3", "cr3t-", "q" * 40))
ADDRESS = "sentinel-control" + ".example.com"
WORKER = "sentinel-" + "worker"


class StagingCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-stage-")
        self.addCleanup(tmp.cleanup)
        self.host = FakeHost(Path(tmp.name))

    def apply(self, version: str = "r1") -> subprocess.CompletedProcess:
        return self.host.stage("--apply", version=version)

    def release(self, version: str = "r1") -> Path:
        return self.host.path(f"/opt/mergen/releases/{version}")

    def current(self) -> str | None:
        link = self.host.path("/opt/mergen/current")
        return os.readlink(link) if link.is_symlink() else None

    def assert_code(self, result: subprocess.CompletedProcess, code: int) -> None:
        self.assertEqual(result.returncode, code, result.stdout[-4000:] + result.stderr[-2000:])

    def calls(self, *prefixes: str) -> list[str]:
        return [call for call in self.host.calls() if call.startswith(prefixes)]

    def changed_source(self) -> None:
        with open(self.host.source / "mergen_executor/config.py", "a", encoding="utf-8") as source:
            source.write("# a later commit\n")


class PlanMode(StagingCase):
    def test_plan_mode_changes_nothing(self):
        before = self.host.snapshot()
        result = self.host.stage()
        self.assert_code(result, 0)
        self.assertIn("Nothing was changed", result.stdout)
        self.assertEqual(self.host.snapshot(), before)
        self.assertEqual(self.calls("chown", "venv-python", "systemd-analyze"), [])
        self.assertFalse([call for call in self.calls("python3") if "-m venv" in call])

    def test_apply_is_refused_without_root(self):
        if os.geteuid() == 0:
            self.skipTest("runs as root; the guard cannot be exercised")
        before = self.host.snapshot()
        result = self.host.stage("--apply", fake_root=False)
        self.assert_code(result, 1)
        self.assertIn("as root", result.stderr)
        self.assertEqual(self.host.snapshot(), before)

    def test_a_version_is_required_and_cannot_escape(self):
        for version in ("", "../r1", ".hidden", "r 1", "a/b"):
            with self.subTest(version=version):
                self.assert_code(self.host.stage(version=version), 2)


class Apply(StagingCase):
    def test_apply_builds_one_release_and_points_current_at_it(self):
        result = self.apply()
        self.assert_code(result, 0)
        self.assertEqual(self.current(), "releases/r1")
        release = self.release()
        for name in ("src/backend/archive_io.py", "src/mergen_spool/gate.py", "src/mergen_dispatcher/__main__.py",
                     "src/mergen_executor/__main__.py", "units/mergen-dispatcher.service",
                     "units/mergen-executor.service", "dispatcher/bin/python", "executor/bin/python",
                     "MANIFEST.sha256", "RELEASE", "dispatcher.freeze", "executor.freeze"):
            self.assertTrue((release / name).exists(), name)
        self.assertEqual(list(release.glob("src/**/test_*.py")), [])
        self.assertIn("gate_version=1", (release / "RELEASE").read_text())
        for service in ("dispatcher", "executor"):
            env = self.host.path(f"/etc/mergen/{service}.env")
            self.assertEqual(env.stat().st_mode & 0o777, 0o640)
            self.assertEqual(self.host.owner_of(env), ("root", f"mergen-{service}"))
            unit = self.host.path(f"/etc/systemd/system/mergen-{service}.service")
            self.assertEqual(unit.read_bytes(), (release / "units" / unit.name).read_bytes())
        self.assertIn("Nothing was enabled or started", result.stdout)
        self.assertEqual([call for call in self.calls("systemctl") if " is-active " not in call], [])

    def test_a_second_run_changes_nothing(self):
        self.assert_code(self.apply(), 0)
        before, calls = self.host.snapshot(), len(self.host.calls())
        result = self.apply()
        self.assert_code(result, 0)
        self.assertIn("Nothing to change", result.stdout)
        self.assertEqual(self.host.snapshot(), before)
        later = self.host.calls()[calls:]
        self.assertFalse([call for call in later if call.startswith("chown") or " pip install " in call])

    def test_existing_env_files_are_left_untouched(self):
        paths = [self.host.write_env("dispatcher", "MERGEN_WORKER_TOKEN=kept\n"),
                 self.host.write_env("executor", "MERGEN_RUNTIME_ROOT=/var/lib/mergen/runtime\n")]
        before = [(path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode) for path in paths]
        self.assert_code(self.apply(), 0)
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode) for path in paths],
                         before)
        self.assertFalse([call for call in self.calls("chown") if ".env" in call])

    def test_a_new_version_switches_current_and_keeps_the_previous_release(self):
        self.assert_code(self.apply("r1"), 0)
        self.changed_source()
        result = self.apply("r2")
        self.assert_code(result, 0)
        self.assertEqual(self.current(), "releases/r2")
        self.assertTrue((self.release("r1") / "RELEASE").exists(), "the previous release was removed")
        self.assertIn("previous: r1", result.stdout)

    def test_a_gate_version_change_is_reported(self):
        self.assert_code(self.apply("r1"), 0)
        release_file = self.release("r1") / "RELEASE"
        release_file.write_text(release_file.read_text().replace("gate_version=1", "gate_version=0"))
        self.changed_source()
        result = self.apply("r2")
        self.assert_code(result, 0)
        self.assertIn("Spool gate version changes 0 -> 1: restart both services together", result.stdout)


class Failures(StagingCase):
    def test_a_failed_venv_install_leaves_the_current_release(self):
        self.assert_code(self.apply("r1"), 0)
        self.changed_source()
        self.host.set(pip_fail="executor")
        result = self.apply("r2")
        self.assert_code(result, 1)
        self.assertEqual(self.current(), "releases/r1")
        self.assertEqual(sorted(path.name for path in self.release("r1").parent.iterdir()), ["r1"])
        self.assertIn("is unchanged", result.stderr)

    def test_a_half_built_release_never_becomes_current(self):
        for failure in ({"pip_fail": "dispatcher"}, {"analyze_fail": True}):
            with self.subTest(failure=failure):
                self.host.set(**{"pip_fail": "", "analyze_fail": False, **failure})
                self.assert_code(self.apply(), 1)
                self.assertIsNone(self.current())
                self.assertFalse(self.release().exists())

    def test_an_existing_release_is_never_overwritten(self):
        self.assert_code(self.apply("r1"), 0)
        manifest = (self.release() / "MANIFEST.sha256").read_bytes()
        self.changed_source()
        result = self.apply("r1")
        self.assert_code(result, 1)
        self.assertIn("choose another --version", result.stdout)
        self.assertEqual((self.release() / "MANIFEST.sha256").read_bytes(), manifest)

    def test_a_different_installed_unit_is_never_overwritten(self):
        unit = self.host.path("/etc/systemd/system/mergen-executor.service")
        unit.write_text("[Service]\nExecStart=/bin/true\n")
        before = self.host.snapshot()
        result = self.apply()
        self.assert_code(result, 1)
        self.assertIn("move it aside by hand", result.stdout)
        self.assertEqual(self.host.snapshot(), before)

    def test_a_running_service_blocks_staging(self):
        self.host.set(active=["mergen-dispatcher.service"])
        before = self.host.snapshot()
        result = self.host.stage("--apply")
        self.assert_code(result, 1)
        self.assertIn("is running; stop it first", result.stdout)
        self.assertEqual(self.host.snapshot(), before)


class Separation(StagingCase):
    def test_each_venv_gets_only_its_own_requirements(self):
        self.assert_code(self.apply(), 0)
        installs = [call.split() for call in self.calls("venv-python") if " pip install " in call]
        self.assertEqual(sorted((Path(call[1]).name, Path(call[-1]).parent.name) for call in installs),
                         [("dispatcher", "mergen_dispatcher"), ("executor", "mergen_executor")])
        self.assertIn("httpx", (self.release() / "dispatcher.freeze").read_text())
        self.assertNotIn("httpx", (self.release() / "executor.freeze").read_text())

    def test_the_requirements_keep_the_model_stack_and_http_out(self):
        def names(service):
            lines = (REPO / f"mergen_{service}/requirements.txt").read_text().splitlines()
            return {line.split("==")[0].strip().lower() for line in lines if line.strip() and not line.startswith("#")}
        model = {"torch", "monai", "nnunetv2", "tensorflow", "onnxruntime"}
        self.assertFalse((names("dispatcher") | names("executor")) & model)
        self.assertNotIn("httpx", names("executor"))
        self.assertIn("httpx", names("dispatcher"))

    def test_a_model_package_in_a_service_venv_is_refused(self):
        with open(self.host.source / "mergen_executor/requirements.txt", "a", encoding="utf-8") as source:
            source.write("torch==2.8.0\n")
        result = self.host.stage()
        self.assert_code(result, 1)
        self.assertIn("names a model package: torch", result.stdout)


class Units(StagingCase):
    def test_unit_paths_match_the_release_layout(self):
        self.assert_code(self.apply(), 0)
        for service in ("dispatcher", "executor"):
            with self.subTest(service=service):
                text = (HERE / "systemd" / f"mergen-{service}.service.example").read_text()
                self.assertIn(f"\nExecStart=/opt/mergen/current/{service}/bin/python -P -m mergen_{service}\n", text)
                self.assertIn("\nEnvironment=PYTHONPATH=/opt/mergen/current/src\n", text)
                self.assertIn(f"\nEnvironmentFile=/etc/mergen/{service}.env\n", text)
                # The same names resolve inside the staged release.
                self.assertTrue((self.release() / service / "bin" / "python").exists())
                self.assertTrue((self.release() / "src" / f"mergen_{service}" / "__main__.py").exists())
                self.assertTrue(self.host.path(f"/etc/systemd/system/mergen-{service}.service").is_file())
        verified = [call for call in self.calls("systemd-analyze")]
        self.assertTrue(verified and all(call.startswith("systemd-analyze verify") for call in verified))


class Secrets(StagingCase):
    def test_the_executor_cannot_read_the_dispatcher_token(self):
        self.assert_code(self.apply(), 0)
        self.assertIn("mergen-executor cannot read dispatcher.env", self.host.verify("after").stdout)
        env = self.host.path("/etc/mergen/dispatcher.env")
        env.chmod(0o644)
        result = self.host.verify("after")
        self.assert_code(result, 1)
        self.assertIn("mergen-executor can read dispatcher.env", result.stdout)
        self.assertIn("the contract is root:mergen-dispatcher 640", result.stdout)

    def test_a_release_a_service_account_could_change_fails_verification(self):
        self.assert_code(self.apply(), 0)
        self.host.own(self.release() / "src", "mergen-executor", "mergen-executor")
        result = self.host.verify("after")
        self.assert_code(result, 1)
        self.assertIn("Part of the release is not owned by root:root", result.stdout)

    def test_the_executor_in_the_dispatcher_group_is_refused(self):
        groups = self.host.load()["groups"]
        groups["mergen-dispatcher"] = [991, ["mergen-executor"]]
        self.host.set(groups=groups)
        result = self.host.stage("--apply")
        self.assert_code(result, 1)
        self.assertIn("could read the worker token", result.stdout)
        self.assertIsNone(self.current())

    def executor_env_verdict(self, text: str) -> subprocess.CompletedProcess:
        self.host.write_env("executor", text)
        return self.host.verify("before")

    def assert_refused(self, key: str) -> None:
        value = "sentinel-" + key.lower().replace("_", "-") + "-" + "v" * 12
        result = self.executor_env_verdict(f"MERGEN_RUNTIME_ROOT=/var/lib/mergen/runtime\n{key}={value}\n")
        self.assert_code(result, 1)
        self.assertIn(f"executor.env must not set: {key}\n", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_an_executor_env_naming_the_vps_is_refused(self):
        # The rule is a prefix, not today's three names; each key is named once.
        result = self.executor_env_verdict("MERGEN_CONTROL_URL=\nMERGEN_WORKER_TOKEN=\nMERGEN_WORKER_ID=\n"
                                           "MERGEN_WORKER_TOKEN=\n")
        self.assert_code(result, 1)
        self.assertIn("executor.env must not set: MERGEN_CONTROL_URL MERGEN_WORKER_ID MERGEN_WORKER_TOKEN\n",
                      result.stdout)

    def test_a_control_token_is_refused_in_the_executor_env(self):
        self.assert_refused("MERGEN_CONTROL_TOKEN")

    def test_a_control_host_is_refused_in_the_executor_env(self):
        self.assert_refused("MERGEN_CONTROL_HOST")

    def test_an_unknown_control_setting_is_refused_in_the_executor_env(self):
        self.assert_refused("MERGEN_CONTROL_FALLBACK_ORIGIN")

    def test_an_unknown_worker_setting_is_refused_in_the_executor_env(self):
        self.assert_refused("MERGEN_WORKER_SECRET_FILE")

    def test_a_vps_setting_is_refused_in_the_executor_env(self):
        self.assert_refused("MERGEN_VPS_ADDRESS")

    def test_a_refused_key_never_shows_its_value(self):
        # Every spelling a mistake could take, and staging stops before any change.
        text = f"MERGEN_CONTROL_TOKEN={SECRET}\nexport MERGEN_VPS_HOST={ADDRESS}\nmergen_worker_id={WORKER}\n"
        outputs = [self.executor_env_verdict(text), self.host.stage(), self.host.stage("--apply")]
        self.assertIn("executor.env must not set: MERGEN_CONTROL_TOKEN MERGEN_VPS_HOST mergen_worker_id\n",
                      outputs[0].stdout)
        for result in outputs:
            self.assert_code(result, 1)
            for value in (SECRET, ADDRESS, WORKER):
                self.assertNotIn(value, result.stdout + result.stderr)
        self.assertIsNone(self.current())

    def test_the_normal_executor_settings_are_accepted(self):
        example = (self.host.source / "infra/gpu-host/executor.env.example").read_text()
        result = self.executor_env_verdict(example + "MERGEN_SPOOL_OWNER=mergen-dispatcher\n")
        self.assert_code(result, 0)
        self.assertIn("executor.env sets no MERGEN_CONTROL_*, MERGEN_WORKER_* or MERGEN_VPS_* key", result.stdout)

    def test_a_control_setting_in_the_executor_unit_is_refused(self):
        self.assert_code(self.apply(), 0)
        unit = self.host.path("/etc/systemd/system/mergen-executor.service")
        unit.write_text(unit.read_text().replace(
            "Environment=PYTHONDONTWRITEBYTECODE=1",
            f'Environment=PYTHONDONTWRITEBYTECODE=1 "MERGEN_CONTROL_TOKEN={SECRET}"'))
        result = self.host.verify("after")
        self.assert_code(result, 1)
        self.assertIn("isolation problem: sets-MERGEN_CONTROL_TOKEN", result.stdout)
        self.assertNotIn(SECRET, result.stdout + result.stderr)

    def test_no_output_carries_a_secret_or_an_address(self):
        self.host.write_env("dispatcher", f"MERGEN_CONTROL_URL=https://{ADDRESS}\nMERGEN_WORKER_TOKEN={SECRET}\n"
                                          f"MERGEN_WORKER_ID={WORKER}\n")
        self.host.set(config={"dispatcher": "invalid:MERGEN_CONTROL_URL"})
        outputs = [self.host.stage(), self.apply(), self.host.verify("before"), self.host.verify("after")]
        self.assertIn("is not accepted: MERGEN_CONTROL_URL", outputs[-1].stdout)
        for result in outputs:
            for value in (SECRET, ADDRESS, WORKER):
                self.assertNotIn(value, result.stdout + result.stderr)


@unittest.skipUnless(importlib.util.find_spec("pydantic") and importlib.util.find_spec("httpx"),
                     "the real probe needs the service dependencies")
class RealProbe(unittest.TestCase):
    def probe(self, service: str, env_text: str | None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            args = [sys.executable, "-P", str(HERE / "lib" / "service_probe.py"), "--service", service]
            if env_text is not None:
                (Path(tmp) / "service.env").write_text(env_text, encoding="utf-8")
                args += ["--env-file", str(Path(tmp) / "service.env")]
            environ = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
            return subprocess.run(args, capture_output=True, text=True, env=environ, check=True).stdout

    def test_the_probe_reports_the_release_and_names_only(self):
        executor = self.probe("executor", None)
        for line in ("imports=ok", "gate_version=1", "adapter=none", "model_packages=none"):
            self.assertIn(line, executor.splitlines())
        dispatcher = self.probe("dispatcher", f"MERGEN_CONTROL_URL=https://{ADDRESS}/path\n"
                                              f"MERGEN_WORKER_TOKEN={SECRET}\nMERGEN_WORKER_ID={WORKER}\n")
        self.assertIn("config=invalid:MERGEN_CONTROL_URL", dispatcher.splitlines())
        for value in (SECRET, ADDRESS, WORKER):
            self.assertNotIn(value, dispatcher)


if __name__ == "__main__":
    unittest.main()
