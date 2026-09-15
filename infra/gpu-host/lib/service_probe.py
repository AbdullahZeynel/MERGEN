"""Runs inside one MERGEN service venv; see probe() in lib/services.sh.

Reports, as key=value lines, what that interpreter really gets from a release:
whether every service module imports from the release's src/, the spool gate
version, which distributions the venv holds and, given an env file, whether
the service would accept its configuration. A configuration value is never
printed: a rejected setting is reported by variable name only.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import pkgutil
import re
import sys
from pathlib import Path

PACKAGES = {"dispatcher": "mergen_dispatcher", "executor": "mergen_executor"}
CONFIGS = {"dispatcher": ("mergen_dispatcher.config", "DispatcherConfig"),
           "executor": ("mergen_executor.config", "ExecutorConfig")}
MODEL = {"torch", "torchvision", "torchaudio", "monai", "nnunet", "nnunetv2", "tensorflow",
         "jax", "jaxlib", "onnxruntime", "onnxruntime-gpu", "cupy", "triton"}
HTTP = {"httpx", "httpcore", "h11", "anyio", "requests", "urllib3", "aiohttp"}
VARIABLE = re.compile(r"\bMERGEN_[A-Z0-9_]+\b")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_env(path: str) -> dict[str, str]:
    """systemd EnvironmentFile basics: KEY=VALUE, comments, one level of quotes."""
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        match = ASSIGNMENT.match(line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[match.group(1)] = value
    return values


def imports(service: str, src: Path) -> list[str]:
    package = PACKAGES[service]
    problems = []
    names = ["backend.archive_io", "backend.live_contracts", "mergen_spool.contract",
             "mergen_spool.fs", "mergen_spool.gate", package]
    root = importlib.import_module(package)
    names += [f"{package}.{item.name}" for item in pkgutil.iter_modules(root.__path__)
              if not item.name.startswith("test_")]
    for name in names:
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - the type is the report
            problems.append(f"{name}:{type(exc).__name__}")
            continue
        origin = Path(getattr(module, "__file__", "") or "").resolve()
        if not origin.is_relative_to(src):
            problems.append(f"{name}:outside-release")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=sorted(PACKAGES), required=True)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    src = Path(os.environ.get("PYTHONPATH", "")).resolve()

    try:
        problems = imports(args.service, src)
    except Exception as exc:  # noqa: BLE001
        problems = [f"{PACKAGES[args.service]}:{type(exc).__name__}"]
    print("imports=" + ("ok" if not problems else "failed:" + ",".join(problems)))
    if problems:
        return 1

    from mergen_spool import contract
    print(f"gate_version={contract.GATE_VERSION}")
    print(f"schema_version={contract.SCHEMA_VERSION}")
    if args.service == "executor":
        from mergen_executor.adapter import default_imaging_adapter
        print("adapter=" + ("none" if default_imaging_adapter() is None else "present"))

    installed = sorted({normalise(dist.metadata["Name"] or "") for dist in importlib.metadata.distributions()}
                       - {""})
    print("distributions=" + ",".join(installed))
    model = sorted(set(installed) & MODEL)
    print("model_packages=" + (",".join(model) or "none"))
    http = sorted(set(installed) & HTTP)
    print("http_client=" + ("absent" if not http else "present:" + ",".join(http)))

    if not args.env_file:
        print("config=skipped")
        return 0
    try:
        environ = read_env(args.env_file)
    except (OSError, UnicodeDecodeError):
        print("config=unreadable")
        return 0
    module_name, class_name = CONFIGS[args.service]
    config_class = getattr(importlib.import_module(module_name), class_name)
    try:
        config_class.from_env(environ)
    except ValueError as exc:
        names = sorted(set(VARIABLE.findall(str(exc)))) or ["unnamed"]
        print("config=invalid:" + ",".join(names))
    else:
        print("config=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
