"""Entry point: `python -P -m mergen_dispatcher` (see mergen-dispatcher.service)."""
from __future__ import annotations

import logging
import signal
import sys

from mergen_dispatcher.config import ConfigError, DispatcherConfig
from mergen_dispatcher.logs import configure_logging
from mergen_dispatcher.runtime import Dispatcher
from mergen_dispatcher.spool import SpoolLayoutError

# Needs an operator, not a restart: the unit sets RestartPreventExitStatus=2.
OPERATOR_ACTION = 2


def main() -> int:
    try:
        config = DispatcherConfig.from_env()
    except ConfigError as exc:
        print(f"mergen-dispatcher: {exc}", file=sys.stderr)
        return OPERATOR_ACTION
    configure_logging(config)
    dispatcher = Dispatcher(config)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: dispatcher.stop())
    try:
        dispatcher.run()
    except SpoolLayoutError as exc:
        logging.getLogger("mergen.dispatcher").error("refusing to start: %s", exc)
        return OPERATOR_ACTION
    finally:
        dispatcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
