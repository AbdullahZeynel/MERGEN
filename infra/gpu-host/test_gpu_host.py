"""Contract tests for the GPU host bootstrap layer.

Nothing here touches the real /etc, /var, user database or GPU. The only
script executed is install-base.sh in its default plan mode, and it runs with
a stubbed PATH so that any attempt to mutate the host is recorded and fails
the test instead of changing anything.

    python -m unittest discover -s infra/gpu-host -p 'test_*.py'
"""

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL_SCRIPTS = sorted(HERE.glob("*.sh")) + sorted(HERE.glob("lib/*.sh"))
READ_ONLY_SCRIPTS = ("audit-host.sh", "check-snapshot-layout.sh", "verify-gpu-runtime.sh")

# Commands that would change the host. Matched as invocations, not as words:
# a read-only script may legitimately name `apt-get` while probing which
# package manager exists, and may say "not kill it" in a warning string.
MUTATING_PATTERNS = (
    r"\buseradd\b", r"\bgroupadd\b", r"\busermod\b", r"\bpasswd\s+--",
    r"\bsystemd-sysusers\b", r"\bsystemd-tmpfiles\b",
    r"\bsystemctl\s+(start|stop|enable|disable|restart|mask)\b",
    r"\bapt(-get)?\s+(install|remove|upgrade|purge)\b",
    r"\bpacman\s+-[SR]", r"\bdnf\s+(install|remove)\b", r"\bzypper\s+(install|remove)\b",
    r"\bpip\s+install\b", r"\bpip3\s+install\b",
    r"\bcurl\s+", r"\bwget\s+",
    r"(^|[;&|]|\$\()\s*rm\s+", r"\brmdir\b", r"\bmkdir\b",
    r"\binstall\s+-[a-zA-Z]", r"\bchown\b", r"\bchmod\b",
    r"\btailscale\s+up\b",
    r"(^|[;&|]|\$\()\s*(kill|pkill)\s+",
    r"\bbtrfs\s+subvolume\s+(snapshot|delete|create)\b",
    r"\blvcreate\b", r"\blvremove\b", r"\bmkfs\b", r"\bdd\s+if=",
)

# Identity that must never reach stdout or a log line.
LEAKY_TOKENS = (
    "tailscale ip",
    "--query-gpu=uuid",
    "--query-gpu=serial",
    "query-compute-apps",
    "nvidia-smi -q",
    "hostname -f",
    "$(hostname",
    "ps -ef",
    "ps aux",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ShellHygiene(unittest.TestCase):
    def test_every_shell_file_parses(self):
        self.assertTrue(SHELL_SCRIPTS, "no shell scripts found")
        for script in SHELL_SCRIPTS:
            with self.subTest(script=script.name):
                result = subprocess.run(["bash", "-n", str(script)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_strict_mode_is_inherited_everywhere(self):
        # common.sh sets it once; the executables source common.sh as their
        # first statement, so strict mode is in force before anything runs.
        self.assertIn("set -euo pipefail", read(HERE / "lib" / "common.sh"))
        for script in HERE.glob("*.sh"):
            with self.subTest(script=script.name):
                text = read(script)
                self.assertIn("lib/common.sh", text,
                              f"{script.name} does not source the strict-mode library")

    def test_executables_declare_a_bash_shebang(self):
        for script in HERE.glob("*.sh"):
            with self.subTest(script=script.name):
                self.assertTrue(read(script).startswith("#!/usr/bin/env bash"))


class ReadOnlyScripts(unittest.TestCase):
    def test_read_only_scripts_contain_no_mutating_command(self):
        for name in READ_ONLY_SCRIPTS:
            # Drop comments and the text of quoted messages: prose may name a
            # command the script must never run.
            code_lines = []
            for line in read(HERE / name).splitlines():
                if line.lstrip().startswith("#"):
                    continue
                code_lines.append(re.sub(r"""(['"])(?:\\.|(?!\1).)*\1""", "''", line))
            code = "\n".join(code_lines)
            for pattern in MUTATING_PATTERNS:
                with self.subTest(script=name, pattern=pattern):
                    match = re.search(pattern, code)
                    self.assertIsNone(
                        match,
                        f"{name} contains a host-mutating command: {match.group(0) if match else ''}")

    def test_no_script_prints_identifying_detail(self):
        for script in SHELL_SCRIPTS:
            text = read(script)
            for token in LEAKY_TOKENS:
                with self.subTest(script=script.name, token=token):
                    self.assertNotIn(token, text,
                                     f"{script.name} could leak host identity: {token}")

    def test_verify_script_rejects_a_traversal_venv_path(self):
        result = subprocess.run(
            ["bash", str(HERE / "verify-gpu-runtime.sh"), "/opt/../etc/mergen"],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertTrue("FAIL" in combined or "nvidia-smi" in combined)

    def test_verify_script_requires_exactly_one_argument(self):
        result = subprocess.run(["bash", str(HERE / "verify-gpu-runtime.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


class SafePathHelper(unittest.TestCase):
    """safe_system_path must reject traversal and symlinked targets."""

    def _check(self, path: str) -> int:
        script = f'source "{HERE}/lib/common.sh"; safe_system_path "{path}"'
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True).returncode

    def test_absolute_plain_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._check(tmp), 0)

    def test_relative_path_is_rejected(self):
        self.assertNotEqual(self._check("relative/path"), 0)

    def test_traversal_segment_is_rejected(self):
        self.assertNotEqual(self._check("/opt/mergen/../../etc"), 0)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real"
            target.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(target)
            self.assertNotEqual(self._check(str(link)), 0)

    def test_symlinked_parent_of_a_missing_target_is_rejected(self):
        # Regression: checking only the final component passed this, because
        # the leaf does not exist and so is not itself a symlink.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "real").mkdir()
            (Path(tmp) / "link").symlink_to(Path(tmp) / "real")
            self.assertNotEqual(self._check(f"{tmp}/link/not-created"), 0)

    def test_missing_target_under_a_plain_parent_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._check(f"{tmp}/not-created"), 0)

    def test_root_and_repeated_slashes_are_accepted(self):
        self.assertEqual(self._check("/"), 0)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._check(f"{tmp}//sub//leaf"), 0)


class InstallPlanIsInert(unittest.TestCase):
    """Plan mode must describe actions without performing any of them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.marker = Path(self.tmp) / "called"
        self.stub_dir = Path(self.tmp) / "bin"
        self.stub_dir.mkdir()
        # Any mutating tool the script might reach for records the call and
        # exits non-zero, so a stray invocation is loud rather than silent.
        for tool in ("useradd", "passwd", "systemd-sysusers", "systemd-tmpfiles",
                     "install", "chown", "chmod", "groupadd", "usermod"):
            stub = self.stub_dir / tool
            stub.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "$0 $*" >> "{self.marker}"\n'
                "exit 97\n",
                encoding="utf-8")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _run_plan(self):
        env = dict(os.environ)
        env["PATH"] = f"{self.stub_dir}:{env.get('PATH', '')}"
        return subprocess.run(["bash", str(HERE / "install-base.sh")],
                              capture_output=True, text=True, env=env, cwd=self.tmp)

    def test_plan_mode_invokes_no_mutating_tool(self):
        self._run_plan()
        self.assertFalse(self.marker.exists(),
                         f"plan mode called a mutating tool: "
                         f"{self.marker.read_text() if self.marker.exists() else ''}")

    def test_plan_mode_creates_no_file_in_its_working_directory(self):
        before = set(Path(self.tmp).rglob("*"))
        self._run_plan()
        after = set(Path(self.tmp).rglob("*"))
        self.assertEqual(before, after, "plan mode created or removed files")

    def test_plan_mode_either_plans_or_refuses_explicitly(self):
        result = self._run_plan()
        combined = result.stdout + result.stderr
        if result.returncode == 0:
            self.assertIn("Nothing was changed", combined)
            self.assertIn("PLAN", combined)
        else:
            # The only acceptable non-zero exit is a stated precondition failure.
            self.assertTrue(
                "Unsupported or unrecognised distribution" in combined
                or "systemd is not the running init" in combined
                or "Required tool missing" in combined,
                combined)

    def test_apply_without_root_is_refused(self):
        if os.geteuid() == 0:
            self.skipTest("test runs as root; the non-root guard cannot be exercised")
        env = dict(os.environ)
        env["PATH"] = f"{self.stub_dir}:{env.get('PATH', '')}"
        result = subprocess.run(["bash", str(HERE / "install-base.sh"), "--apply"],
                                capture_output=True, text=True, env=env, cwd=self.tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn("as root", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_unknown_argument_is_refused(self):
        result = subprocess.run(["bash", str(HERE / "install-base.sh"), "--yolo"],
                                capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(result.returncode, 2)


class DeclarativeConfiguration(unittest.TestCase):
    def test_service_accounts_cannot_log_in(self):
        text = read(HERE / "sysusers.d" / "mergen.conf")
        for account in ("mergen-dispatcher", "mergen-executor"):
            line = next(l for l in text.splitlines()
                        if l.startswith("u ") and account in l)
            self.assertIn("nologin", line, f"{account} must not have a login shell")

    def test_maintenance_account_is_not_declared_as_a_system_user(self):
        for line in read(HERE / "sysusers.d" / "mergen.conf").splitlines():
            if line.startswith("u "):
                self.assertNotIn(" mergen ", f" {line} ",
                                 "the human maintenance account must not be a sysusers entry")

    def test_sensitive_directories_give_nothing_to_others(self):
        # /opt/mergen and /var/lib/mergen are traversal paths for public code;
        # everything that can hold job data, models or state must be closed.
        closed = {
            "/srv/mergen-models",
            "/var/lib/mergen/dispatcher",
            "/var/lib/mergen/executor",
            "/var/lib/mergen/runtime",
        }
        seen = set()
        for line in read(HERE / "tmpfiles.d" / "mergen.conf").splitlines():
            if not line.startswith("d "):
                continue
            parts = line.split()
            path, mode = parts[1], parts[2]
            if path in closed:
                seen.add(path)
                self.assertEqual(int(mode, 8) & 0o007, 0,
                                 f"{path} is readable by other users (mode {mode})")
        self.assertEqual(seen, closed, "a protected directory is missing from tmpfiles")

    def test_runtime_spool_is_setgid_to_the_shared_service_group(self):
        # The hand-off contract: dispatcher owns the spool, both services share
        # a group through setgid, and other users get nothing.
        line = next(l for l in read(HERE / "tmpfiles.d" / "mergen.conf").splitlines()
                    if l.startswith("d /var/lib/mergen/runtime"))
        parts = line.split()
        mode = int(parts[2], 8)
        self.assertEqual(parts[3], "mergen-dispatcher")
        self.assertEqual(parts[4], "mergen-svc")
        self.assertTrue(mode & 0o2000, "the spool must be setgid")
        self.assertEqual(mode & 0o070, 0o070, "the shared group needs rwx")
        self.assertEqual(mode & 0o007, 0, "other users must get nothing")

    def test_both_services_belong_to_the_shared_group(self):
        text = read(HERE / "sysusers.d" / "mergen.conf")
        for account in ("mergen-dispatcher", "mergen-executor"):
            with self.subTest(account=account):
                self.assertIn(f"m {account}", text.replace("   ", " ").replace("  ", " "))
        for name in ("mergen-dispatcher", "mergen-executor"):
            unit = read(HERE / "systemd" / f"{name}.service.example")
            self.assertIn("SupplementaryGroups=mergen-svc", unit)

    def test_units_use_a_umask_that_allows_the_hand_off(self):
        for name in ("mergen-dispatcher", "mergen-executor"):
            unit = read(HERE / "systemd" / f"{name}.service.example")
            with self.subTest(unit=name):
                self.assertIn("UMask=0007", unit)
                self.assertNotIn("UMask=0077", unit)

    def test_spool_mode_arithmetic_actually_produces_a_shared_file(self):
        """Exercise the real setgid + umask behaviour, not just the numbers.

        This cannot prove cross-account access without three real users, so it
        proves the half that is mechanical: a file created under a setgid
        directory with UMask=0007 is group-readable, group-writable, and
        closed to others, and inherits the directory's group.
        """
        with tempfile.TemporaryDirectory() as tmp:
            spool = Path(tmp) / "runtime"
            spool.mkdir()
            os.chmod(spool, 0o2770)
            self.assertTrue(os.stat(spool).st_mode & stat.S_ISGID,
                            "the filesystem did not keep the setgid bit")
            script = (f'umask 0007; mkdir "{spool}/job-1"; : > "{spool}/job-1/input.bin"')
            subprocess.run(["bash", "-c", script], check=True)
            job = spool / "job-1"
            job_file = job / "input.bin"
            self.assertEqual(os.stat(job).st_mode & 0o777, 0o770)
            self.assertEqual(os.stat(job_file).st_mode & 0o777, 0o660)
            self.assertEqual(os.stat(job).st_gid, os.stat(spool).st_gid,
                             "setgid did not propagate the group to the job directory")
            self.assertEqual(os.stat(job_file).st_gid, os.stat(spool).st_gid)
            for path in (job, job_file):
                self.assertEqual(os.stat(path).st_mode & 0o007, 0,
                                 "other users must not reach spool content")

    def test_snapshot_check_accepts_the_runtime_mode_and_rejects_others_access(self):
        snapshot = read(HERE / "check-snapshot-layout.sh")
        self.assertIn('mode_too_wide "$mode" "$MERGEN_RUNTIME_MODE"', snapshot)
        command = (
            f'source "{HERE}/lib/common.sh"; '
            '! mode_too_wide "$MERGEN_RUNTIME_MODE" "$MERGEN_RUNTIME_MODE"; '
            'mode_too_wide 2777 "$MERGEN_RUNTIME_MODE"'
        )
        result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_executor_cannot_read_the_dispatcher_secret(self):
        # Contract level: the installer seeds dispatcher.env to the dispatcher
        # group at 0640, and the executor unit never references that file.
        installer = read(HERE / "install-base.sh")
        self.assertIn('seed_env "$here/dispatcher.env.example" '
                      '"$MERGEN_CONFIG_ROOT/dispatcher.env" "$MERGEN_DISPATCHER_USER"',
                      installer)
        self.assertIn('install -m 640 -o root -g "$group"', installer)
        executor_unit = read(HERE / "systemd" / "mergen-executor.service.example")
        self.assertNotIn("dispatcher.env", executor_unit)
        self.assertNotIn("MERGEN_WORKER_TOKEN", read(HERE / "executor.env.example"))

    def test_tmpfiles_never_deletes(self):
        for line in read(HERE / "tmpfiles.d" / "mergen.conf").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            self.assertTrue(stripped.startswith("d "),
                            f"only directory lines are allowed: {stripped}")

    def _sudoers_rules(self):
        text = read(HERE / "sudoers.d" / "mergen-maintenance.example")
        return [line for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")]

    def test_sudoers_example_is_narrow(self):
        rules = "\n".join(self._sudoers_rules())
        self.assertNotIn("ALL=(ALL) ALL", rules)
        self.assertNotIn("ALL=(ALL:ALL)", rules)
        self.assertNotRegex(rules, r"(?m)^\s*mergen\s+ALL=\(ALL\)\s+ALL\s*$")
        for account in ("mergen-dispatcher", "mergen-executor"):
            for line in self._sudoers_rules():
                if line.strip().startswith(account):
                    self.fail(f"{account} must never appear as a sudoers subject")

    def test_sudoers_commands_carry_no_wildcard(self):
        # A trailing `*` lets the caller append any option; with a pager option
        # that is a root shell.
        for line in self._sudoers_rules():
            with self.subTest(line=line.strip()[:60]):
                self.assertNotIn("*", line)

    def test_pager_capable_commands_are_pinned_to_no_pager(self):
        for line in self._sudoers_rules():
            for command in ("journalctl", "systemctl --no-pager status", "systemctl status"):
                if command == "journalctl" and "journalctl" in line:
                    self.assertIn("--no-pager", line,
                                  "journalctl without --no-pager can escape to a shell")
            if "status" in line and "systemctl" in line:
                self.assertIn("--no-pager", line,
                              "systemctl status without --no-pager can escape to a shell")

    def test_nopasswd_is_scoped_to_the_named_aliases_only(self):
        # The maintenance password is locked, so a password-requiring rule
        # could never run. NOPASSWD is therefore allowed, but only for the
        # fixed alias list -- never for ALL.
        rule = [line for line in self._sudoers_rules()
                if line.split() and line.split()[0] == "mergen"]
        self.assertEqual(len(rule), 1, "exactly one subject rule expected")
        text = rule[0]
        self.assertIn("NOPASSWD:", text)
        granted = text.split("NOPASSWD:", 1)[1]
        self.assertEqual(
            sorted(item.strip() for item in granted.split(",")),
            ["MERGEN_DIAG", "MERGEN_LOGS", "MERGEN_STATUS", "MERGEN_UNITS"])
        self.assertNotIn("ALL", granted)

    def test_every_granted_alias_is_defined(self):
        text = "\n".join(self._sudoers_rules())
        for alias in ("MERGEN_UNITS", "MERGEN_STATUS", "MERGEN_LOGS", "MERGEN_DIAG"):
            with self.subTest(alias=alias):
                self.assertIn(f"Cmnd_Alias {alias} =", text)

    def test_sudoers_grants_no_package_or_account_management(self):
        rules = "\n".join(self._sudoers_rules()).lower()
        for forbidden in ("apt", "pacman", "dnf", "useradd", "usermod", "visudo",
                          "bash", "sh ", "vi ", "vim", "nano", "reboot", "shutdown"):
            with self.subTest(command=forbidden):
                self.assertNotIn(forbidden, rules)


class InstallerScope(unittest.TestCase):
    def setUp(self):
        self.installer = read(HERE / "install-base.sh")

    def test_sysusers_is_applied_to_our_file_only(self):
        # A bare `systemd-sysusers` also applies every other pending definition
        # on the host, which is not this installer's decision to make.
        self.assertIn("systemd-sysusers /usr/lib/sysusers.d/mergen.conf", self.installer)
        self.assertNotRegex(self.installer, r"(?m)^\s*systemd-sysusers\s*$")

    def test_missing_maintenance_account_is_a_precondition_failure(self):
        self.assertIn("--no-maintenance-account was given but", self.installer)

    def test_existing_maintenance_account_is_validated(self):
        for expectation in ("has no usable home directory",
                            "has a nologin shell; it cannot be used for maintenance"):
            with self.subTest(check=expectation):
                self.assertIn(expectation, self.installer)

    def test_tmpfiles_owners_are_verified_before_apply(self):
        self.assertIn("tmpfiles names an unknown owner", self.installer)
        self.assertIn("tmpfiles names an unknown group", self.installer)

    def test_symlinked_config_target_is_refused(self):
        self.assertIn("Refusing to write through a symlink", self.installer)

    def test_app_root_has_no_private_group_assumption(self):
        line = next(l for l in read(HERE / "tmpfiles.d" / "mergen.conf").splitlines()
                    if l.startswith("d /opt/mergen"))
        parts = line.split()
        self.assertEqual((parts[3], parts[4]), ("root", "root"))


class EnvExamples(unittest.TestCase):
    SECRET_KEYS = ("MERGEN_WORKER_TOKEN", "MERGEN_CONTROL_URL", "MERGEN_WORKER_ID")

    def _pairs(self, name):
        pairs = {}
        for line in read(HERE / name).splitlines():
            match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
            if match:
                pairs[match.group(1)] = match.group(2)
        return pairs

    def test_dispatcher_secrets_are_blank(self):
        pairs = self._pairs("dispatcher.env.example")
        for key in self.SECRET_KEYS:
            self.assertIn(key, pairs)
            self.assertEqual(pairs[key], "", f"{key} must ship empty")

    def test_executor_never_learns_the_vps_or_the_token(self):
        pairs = self._pairs("executor.env.example")
        for key in self.SECRET_KEYS:
            self.assertNotIn(key, pairs,
                             f"{key} must not exist in the executor environment")
        text = read(HERE / "executor.env.example")
        self.assertNotIn("9100", text)
        self.assertNotIn("tailscale", text.lower())

    def test_gpu_thresholds_exist_and_are_unset(self):
        pairs = self._pairs("executor.env.example")
        for key in ("MERGEN_GPU_MAX_MEMORY_USED_MB", "MERGEN_GPU_MAX_UTILIZATION_PERCENT"):
            self.assertIn(key, pairs)
            self.assertEqual(pairs[key], "",
                             f"{key} must be an explicit deploy-time decision")

    def test_both_examples_agree_with_the_directory_contract(self):
        common = read(HERE / "lib" / "common.sh")
        self.assertIn("MERGEN_STATE_ROOT='/var/lib/mergen'", common)
        self.assertIn('MERGEN_RUNTIME_ROOT="$MERGEN_STATE_ROOT/runtime"', common)
        for name in ("dispatcher.env.example", "executor.env.example"):
            self.assertEqual(self._pairs(name)["MERGEN_RUNTIME_ROOT"],
                             "/var/lib/mergen/runtime")


class SystemdExamples(unittest.TestCase):
    def test_units_are_examples_only(self):
        units = sorted((HERE / "systemd").glob("*.example"))
        self.assertEqual(len(units), 2)
        for unit in units:
            with self.subTest(unit=unit.name):
                self.assertIn("EXAMPLE ONLY", read(unit))

    def test_executor_unit_has_no_network_and_no_secret_file(self):
        text = read(HERE / "systemd" / "mergen-executor.service.example")
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("EnvironmentFile=/etc/mergen/executor.env", text)
        self.assertNotIn("dispatcher.env", text)

    def test_both_units_drop_privileges_and_limit_resources(self):
        for name in ("mergen-dispatcher", "mergen-executor"):
            text = read(HERE / "systemd" / f"{name}.service.example")
            with self.subTest(unit=name):
                for directive in ("NoNewPrivileges=true", "ProtectSystem=strict",
                                  "ProtectHome=true", "UMask=",
                                  "Nice=", "CPUWeight=", "IOWeight=", "MemoryMax="):
                    self.assertIn(directive, text)
                self.assertNotIn("User=root", text)


if __name__ == "__main__":
    unittest.main()
