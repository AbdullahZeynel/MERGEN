"""Tiny subprocess used only by G4 isolation tests; no model or patient data."""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path


def main() -> int:
    request = json.load(sys.stdin)
    output = Path(request.get("outputDir") or os.environ["TMPDIR"])
    behavior = (Path(request["modelRoot"]) / "behavior").read_text().strip() \
        if (Path(request["modelRoot"]) / "behavior").exists() else "complete"
    if behavior == "env" and any(key.startswith(("MERGEN_CONTROL_", "MERGEN_WORKER_", "MERGEN_VPS_"))
                                 for key in os.environ):
        return 8
    if request["operation"] == "run" and behavior == "escape":
        try:
            (output.parent / "escaped").write_text("bad")
            return 9
        except PermissionError:
            pass
    elif request["operation"] == "run" and behavior == "block":
        signal.signal(signal.SIGTERM, lambda *_: None)
        while True:
            time.sleep(1)
    elif request["operation"] == "run" and behavior == "descendant":
        child = os.fork()
        if child == 0:
            signal.signal(signal.SIGTERM, lambda *_: None)
            while True:
                time.sleep(1)
        (output / "child.pid").write_text(str(child))
    elif request["operation"] == "run" and behavior.startswith("report:"):
        (output / ".adapter-response.json").write_text(
            json.dumps({"error": behavior.split(":", 1)[1]}), encoding="utf-8")
        return 0
    if request["operation"] == "run":
        (output / "result.zip").write_bytes(b"test-result")
    (output / ".adapter-response.json").write_text(
        json.dumps({"result": "result.zip"}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
