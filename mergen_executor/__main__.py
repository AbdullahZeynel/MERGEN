"""Entry point: `python -P -m mergen_executor` (see mergen-executor.service)."""
from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Mapping

from mergen_executor.adapter import default_imaging_adapter
from mergen_executor.config import ConfigError, ExecutorConfig
from mergen_executor.layout import LayoutError
from mergen_executor.logs import configure_logging
from mergen_executor.runtime import Executor

# Needs an operator, not a restart: the unit sets RestartPreventExitStatus=2.
OPERATOR_ACTION = 2
LOG = logging.getLogger("mergen.executor")


def main(environ: Mapping[str, str] | None = None) -> int:
    try:
        config = ExecutorConfig.from_env(environ)
    except ConfigError as exc:
        print(f"mergen-executor: {exc}", file=sys.stderr)
        return OPERATOR_ACTION
    configure_logging()
    executor = Executor(config, default_imaging_adapter())
    try:
        executor.start()
    except LayoutError as exc:
        LOG.error("refusing to start: %s", exc)
        return OPERATOR_ACTION
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: executor.stop())
    try:
        executor.loop()
    except LayoutError as exc:
        LOG.error("stopping: %s", exc)
        return OPERATOR_ACTION
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
