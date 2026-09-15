"""Start-up checks, configuration and exit codes.
Run: python -m unittest discover -s mergen_executor -t ."""
import io
import os
import pwd
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from mergen_executor.__main__ import main
from mergen_executor.config import ConfigError, ExecutorConfig
from mergen_executor.layout import LayoutError, verify_jobs_directory, verify_spool, verify_state
from mergen_executor.test_support import ExecutorCase

USER = pwd.getpwuid(os.geteuid()).pw_name


def with_ids(info: os.stat_result, uid: int | None = None, gid: int | None = None) -> os.stat_result:
    values = list(info[:10])
    values[4] = info.st_uid if uid is None else uid
    values[5] = info.st_gid if gid is None else gid
    return os.stat_result(values)


class SpoolLayout(ExecutorCase):
    def test_the_prepared_layout_is_accepted(self):
        verify_state(self.state)
        verify_spool(self.root, os.geteuid())

    def test_a_runtime_root_outside_the_contract_is_refused(self):
        for mode in (0o2775, 0o2777, 0o0770, 0o2750):
            with self.subTest(mode=f"{mode:04o}"):
                os.chmod(self.root, mode)
                try:
                    with self.assertRaisesRegex(LayoutError, f"runtime root has mode {mode:04o}"):
                        verify_spool(self.root, os.geteuid())
                finally:
                    os.chmod(self.root, 0o2770)

    def test_the_spool_owner_and_the_group_membership_are_checked(self):
        with self.assertRaisesRegex(LayoutError, "runtime root is not owned by MERGEN_SPOOL_OWNER"):
            verify_spool(self.root, os.geteuid() + 1)
        stranger = max({os.getegid(), *os.getgroups()}) + 1000
        real = os.lstat

        def lstat(path, *args, **kwargs):
            info = real(path, *args, **kwargs)
            return with_ids(info, gid=stranger) if os.fspath(path) == str(self.root) else info

        with patch("os.lstat", side_effect=lstat), \
                self.assertRaisesRegex(LayoutError, "not a member of the runtime root's group"):
            verify_spool(self.root, os.geteuid())

    def test_jobs_outside_the_contract_are_refused_and_a_missing_one_waits(self):
        jobs = self.root / "jobs"
        os.chmod(jobs, 0o2770)  # the group could add or rename jobs
        with self.assertRaisesRegex(LayoutError, "jobs/ has mode 2770"):
            verify_spool(self.root, os.geteuid())
        os.chmod(jobs, 0o2750)
        with self.assertRaisesRegex(LayoutError, "jobs/ is not owned by MERGEN_SPOOL_OWNER"):
            verify_jobs_directory(self.root, os.geteuid() + 1)
        jobs.rmdir()
        self.assertFalse(verify_jobs_directory(self.root, os.geteuid()))
        jobs.symlink_to(self.base)
        with self.assertRaisesRegex(LayoutError, "jobs/ is not a real directory"):
            verify_jobs_directory(self.root, os.geteuid())

    def test_a_shared_linked_or_missing_state_directory_is_refused(self):
        os.chmod(self.state, 0o750)
        with self.assertRaisesRegex(LayoutError, "open to other accounts"):
            verify_state(self.state)
        os.chmod(self.state, 0o700)
        link = self.base / "state-link"
        link.symlink_to(self.state)
        with self.assertRaisesRegex(LayoutError, "state directory is not a real directory"):
            verify_state(link)
        with self.assertRaisesRegex(LayoutError, "does not exist"):
            verify_state(self.base / "missing")


class Configuration(unittest.TestCase):
    def env(self, **overrides):
        values = {"MERGEN_SPOOL_OWNER": USER, **overrides}
        return {key: value for key, value in values.items() if value is not None}

    def test_defaults_follow_the_host_contract(self):
        config = ExecutorConfig.from_env(self.env())
        self.assertEqual(config.runtime_root, Path("/var/lib/mergen/runtime"))
        self.assertEqual(config.state_root, Path("/var/lib/mergen/executor"))
        self.assertEqual(config.pause_file, Path("/var/lib/mergen/executor/pause"))
        self.assertEqual(config.gpu_lock_path, Path("/var/lib/mergen/executor/gpu.lock"))
        self.assertEqual(config.spool_owner_uid, os.geteuid())
        self.assertLess(config.ready_refresh_seconds, 90)
        self.assertEqual(config.model_root, Path("/srv/mergen-models"))
        self.assertIsNone(config.imaging_venv)

    def test_model_root_and_venv_are_configurable(self):
        config = ExecutorConfig.from_env(self.env(
            MERGEN_MODEL_ROOT="/srv/mergen-models/imaging/v1",
            MERGEN_IMAGING_VENV="/srv/mergen-models/venv/imaging"))
        self.assertEqual(config.model_root, Path("/srv/mergen-models/imaging/v1"))
        self.assertEqual(config.imaging_venv, Path("/srv/mergen-models/venv/imaging"))

    def test_invalid_values_name_the_variable(self):
        cases = {"MERGEN_RUNTIME_ROOT": "relative/runtime",
                 "MERGEN_EXECUTOR_STATE": "/var/lib/../executor",
                 "MERGEN_SPOOL_OWNER": "no-such-account-" + "q" * 8,
                 "MERGEN_PAUSE_FILE": "/var/tmp/pause",
                 "MERGEN_GPU_LOCK_PATH": "/var/lib/mergen/executor/sub/gpu.lock",
                 "MERGEN_GPU_WAIT_SECONDS": "120",
                 "MERGEN_EXECUTOR_POLL_SECONDS": "soon",
                 "MERGEN_MAX_INPUT_BYTES": "0"}
        cases.update({"MERGEN_MODEL_ROOT": "relative/model",
                      "MERGEN_IMAGING_VENV": "relative/venv",
                      "MERGEN_ADAPTER_TIMEOUT_SECONDS": "5",
                      "MERGEN_ADAPTER_TERM_GRACE_SECONDS": "0"})
        for name, value in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ConfigError, name):
                ExecutorConfig.from_env(self.env(**{name: value}))

    def test_there_is_no_network_or_credential_setting(self):
        for field in ExecutorConfig.__dataclass_fields__:
            for word in ("url", "token", "host", "worker", "vps", "control"):
                with self.subTest(field=field, word=word):
                    self.assertNotIn(word, field)


class ExitCodes(ExecutorCase):
    def run_main(self, environ):
        stderr = io.StringIO()
        with redirect_stderr(stderr), patch("mergen_executor.__main__.configure_logging"):
            code = main(environ)
        return code, stderr.getvalue()

    def test_a_configuration_error_exits_2_and_names_the_variable(self):
        code, output = self.run_main({"MERGEN_SPOOL_OWNER": USER, "MERGEN_RUNTIME_ROOT": "relative"})
        self.assertEqual(code, 2)
        self.assertIn("MERGEN_RUNTIME_ROOT", output)

    def test_an_unsafe_spool_exits_2_before_anything_is_written(self):
        os.chmod(self.root / "jobs", 0o2757)
        environ = {"MERGEN_SPOOL_OWNER": USER, "MERGEN_RUNTIME_ROOT": str(self.root),
                   "MERGEN_EXECUTOR_STATE": str(self.state)}
        with self.assertLogs("mergen.executor", level="ERROR") as logs:
            code, _ = self.run_main(environ)
        self.assertEqual(code, 2)
        self.assertIn("jobs/ has mode 2757", "\n".join(logs.output))
        self.assertFalse((self.root / "executor.json").exists())


if __name__ == "__main__":
    unittest.main()
