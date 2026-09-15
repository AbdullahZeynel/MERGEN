"""A fake GPU host for the service staging tests. Not a test module itself.

stage-services.sh and verify-services.sh run for real against a temporary
root (--root). Only what needs root, systemd, a network or real accounts is
replaced, by small commands placed first on PATH that call back into this
file: id, getent, chown, stat, runuser, systemctl, systemd-analyze, and a
python3 whose `-m venv` builds a venv with a fake pip and a canned probe.
Ownership is kept per inode, so it survives the scripts' renames, and every
fake invocation is logged for the tests to inspect.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
COMMANDS = ("id", "getent", "chown", "stat", "runuser", "systemctl", "systemd-analyze")
USERS = {"root": (0, 0), "mergen": (1500, 1500), "mergen-dispatcher": (991, 991),
         "mergen-executor": (992, 992)}
SHELLS = {"root": "/bin/bash", "mergen": "/bin/bash"}
GROUPS = {"root": (0, []), "mergen": (1500, []), "mergen-dispatcher": (991, []),
          "mergen-executor": (992, []), "mergen-svc": (990, ["mergen-dispatcher", "mergen-executor"]),
          "video": (44, []), "render": (109, [])}


class FakeHost:
    def __init__(self, base: Path):
        self.base = base
        self.root, self.bin, self.source = base / "root", base / "bin", base / "source"
        self.state_file, self.log = base / "state.json", base / "calls.log"
        self.python = self.bin / "python3"
        self.save({"root": True, "active": [], "pip_fail": "", "analyze_fail": False, "config": {},
                   "users": USERS, "groups": GROUPS, "owners": {}})
        self.bin.mkdir()
        for name in (*COMMANDS, "python3"):
            wrapper = self.bin / name
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{__file__}" {name} "$@"\n', encoding="utf-8")
            wrapper.chmod(0o755)
        self._copy_source()
        self._lay_out_host()

    # -- state -----------------------------------------------------------------
    def load(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    def set(self, **values) -> None:
        state = self.load()
        state.update(values)
        self.save(state)

    def own(self, path: Path, owner: str, group: str) -> None:
        state = self.load()
        info = os.lstat(path)
        state["owners"][f"{info.st_dev}:{info.st_ino}"] = [owner, group]
        self.save(state)

    def owner_of(self, path: Path) -> tuple[str, str]:
        return tuple(_owner(self.load(), path))

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    # -- layout ------------------------------------------------------------------
    def _copy_source(self) -> None:
        names = ["backend/archive_io.py", "backend/live_contracts.py", "infra/gpu-host/dispatcher.env.example",
                 "infra/gpu-host/executor.env.example", "infra/gpu-host/systemd/mergen-dispatcher.service.example",
                 "infra/gpu-host/systemd/mergen-executor.service.example"]
        for package in ("mergen_spool", "mergen_dispatcher", "mergen_executor"):
            names += [f"{package}/{item.name}" for item in (REPO / package).iterdir() if item.is_file()]
        for name in names:
            (self.source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, self.source / name)

    def path(self, absolute: str) -> Path:
        return self.root / absolute.lstrip("/")

    def _lay_out_host(self) -> None:
        """What install-base.sh --apply leaves: accounts, directories, no env file."""
        for absolute, mode, owner, group in (
                ("/opt/mergen", 0o755, "root", "root"), ("/etc/mergen", 0o751, "root", "root"),
                ("/etc/systemd/system", 0o755, "root", "root"), ("/var/lib/mergen", 0o755, "root", "root"),
                ("/var/lib/mergen/dispatcher", 0o700, "mergen-dispatcher", "mergen-dispatcher"),
                ("/var/lib/mergen/executor", 0o700, "mergen-executor", "mergen-executor"),
                ("/var/lib/mergen/runtime", 0o2770, "mergen-dispatcher", "mergen-svc"),
                ("/srv/mergen-models", 0o750, "mergen", "mergen-svc")):
            path = self.path(absolute)
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(mode)
            self.own(path, owner, group)

    def write_env(self, service: str, text: str, mode: int = 0o640) -> Path:
        path = self.path(f"/etc/mergen/{service}.env")
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        self.own(path, "root", f"mergen-{service}")
        return path

    # -- running -------------------------------------------------------------------
    def environ(self, fake_root: bool = True) -> dict:
        env = {"PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}", "FAKE_HOST_BASE": str(self.base),
               "LC_ALL": "C.UTF-8"}
        self.set(root=fake_root)
        return env

    def stage(self, *args: str, version: str = "r1", fake_root: bool = True) -> subprocess.CompletedProcess:
        command = ["bash", str(HERE / "stage-services.sh"), "--version", version, "--root", str(self.root),
                   "--python", str(self.python), "--source", str(self.source), *args]
        return subprocess.run(command, capture_output=True, text=True, env=self.environ(fake_root))

    def verify(self, phase: str) -> subprocess.CompletedProcess:
        command = ["bash", str(HERE / "verify-services.sh"), f"--{phase}", "--root", str(self.root)]
        return subprocess.run(command, capture_output=True, text=True, env=self.environ())

    def snapshot(self) -> dict:
        found = {}
        for top in (self.root, self.source):
            for path in sorted(top.rglob("*")):
                info = os.lstat(path)
                if stat.S_ISLNK(info.st_mode):
                    detail = os.readlink(path)
                elif stat.S_ISREG(info.st_mode):
                    detail = path.read_bytes()
                else:
                    detail = None
                found[str(path)] = (stat.S_IMODE(info.st_mode), info.st_mtime_ns, detail)
        return found


# -- the fake commands -------------------------------------------------------------
def _owner(state: dict, path: Path) -> list[str]:
    info = os.lstat(path)
    return state["owners"].get(f"{info.st_dev}:{info.st_ino}", ["root", "root"])


def _log(base: Path, line: str) -> None:
    with open(base / "calls.log", "a", encoding="utf-8") as log:
        log.write(line + "\n")


def _groups_of(state: dict, user: str) -> set[str]:
    uid, gid = state["users"][user]
    names = {name for name, (number, members) in state["groups"].items() if number == gid or user in members}
    return names


def command(name: str, args: list[str], base: Path) -> int:
    state = json.loads((base / "state.json").read_text(encoding="utf-8"))
    _log(base, " ".join([name, *args]))
    args = [arg for arg in args if arg != "--"]
    if name == "id":
        if args == ["-u"]:
            print(0 if state["root"] else os.getuid())
            return 0
        if len(args) == 2 and args[0] == "-u" and args[1] in state["users"]:
            print(state["users"][args[1]][0])
            return 0
        return 1
    if name == "getent":
        table, keys = args[0], args[1:]
        if table == "passwd":
            rows = {user: f"{user}:x:{uid}:{gid}::/var/lib/{user}:{SHELLS.get(user, '/usr/sbin/nologin')}"
                    for user, (uid, gid) in state["users"].items()}
        else:
            rows = {group: f"{group}:x:{gid}:{','.join(members)}" for group, (gid, members) in state["groups"].items()}
        wanted = keys or list(rows)
        if any(key not in rows for key in wanted):
            return 2
        print("\n".join(rows[key] for key in wanted))
        return 0
    if name == "chown":
        recursive = "-R" in args
        args = [arg for arg in args if arg != "-R"]
        owner, group = args[0].split(":")
        for target in args[1:]:
            paths = [Path(target)]
            if recursive:
                paths += [Path(root) / item for root, dirs, files in os.walk(target) for item in dirs + files]
            for path in paths:
                info = os.lstat(path)
                state["owners"][f"{info.st_dev}:{info.st_ino}"] = [owner, group]
        (base / "state.json").write_text(json.dumps(state), encoding="utf-8")
        return 0
    if name == "stat":
        fmt, target = args[args.index("-c") + 1], Path(args[-1])
        try:
            info = os.lstat(target)
        except OSError:
            return 1
        owner, group = _owner(state, target)
        print(fmt.replace("%a", format(stat.S_IMODE(info.st_mode), "o")).replace("%U", owner).replace("%G", group))
        return 0
    if name == "runuser":
        user, test = args[args.index("-u") + 1], args[args.index("-u") + 2:]
        if test[:2] != ["test", "-r"]:
            return 97
        target = Path(test[2])
        mode, (owner, group) = stat.S_IMODE(os.lstat(target).st_mode), _owner(state, target)
        if user == owner:
            readable = mode & 0o400
        elif group in _groups_of(state, user):
            readable = mode & 0o040
        else:
            readable = mode & 0o004
        return 0 if readable else 1
    if name == "systemctl":
        if args and args[0] == "is-active":
            return 0 if args[-1] in state["active"] else 3
        return 97  # anything else would change the host
    if name == "systemd-analyze":
        return 1 if state["analyze_fail"] else 0
    if name == "python3":
        if args[:2] == ["-m", "venv"]:
            venv = Path(args[2])
            (venv / "bin").mkdir(parents=True)
            (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
            python = venv / "bin" / "python"
            # The probe runs under `env -i`, so the wrapper carries its own state path.
            python.write_text(f'#!/bin/sh\nFAKE_HOST_BASE="{base}" exec "{sys.executable}" "{__file__}" '
                              f'venv-python "{venv}" "$@"\n', encoding="utf-8")
            python.chmod(0o755)
            return 0
        return subprocess.run([sys.executable, *args]).returncode
    if name == "venv-python":
        return venv_python(Path(args[0]), args[1:], state)
    return 97


def venv_python(venv: Path, args: list[str], state: dict) -> int:
    service = venv.name
    installed = venv / "installed.txt"
    if args[:3] == ["-m", "pip", "install"]:
        if state["pip_fail"] == service:
            return 1
        requirements = Path(args[args.index("-r") + 1])
        names = [re.split(r"[<>=!~;\[ ]", line.strip())[0].lower() for line in requirements.read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        installed.write_text("\n".join(names) + "\n", encoding="utf-8")
        return 0
    if args[:3] == ["-m", "pip", "freeze"]:
        print("\n".join(f"{name}==0" for name in installed.read_text().split()))
        return 0
    if args[:1] == ["-P"] and args[1].endswith("service_probe.py"):
        src = Path(os.environ["PYTHONPATH"])
        names = installed.read_text().split() if installed.exists() else []
        gate = re.search(r"^GATE_VERSION = (\d+)$", (src / "mergen_spool/contract.py").read_text(), re.M)
        print("imports=ok")
        print(f"gate_version={gate.group(1)}")
        print("schema_version=1")
        if service == "executor":
            print("adapter=none")
        print("distributions=" + ",".join(sorted(names)))
        print("model_packages=none")
        http = sorted(set(names) & {"httpx", "httpcore", "h11", "anyio"})
        print("http_client=" + ("present:" + ",".join(http) if http else "absent"))
        print("config=" + (state["config"].get(service, "ok") if "--env-file" in args else "skipped"))
        return 0
    return 97


if __name__ == "__main__":
    sys.exit(command(sys.argv[1], sys.argv[2:], Path(os.environ["FAKE_HOST_BASE"])))
