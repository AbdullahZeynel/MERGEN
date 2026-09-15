"""Plain logging to the journal.

The executor holds no secret, but its inputs are patient data: log lines carry
only an 8-character job tag, a state or an error code, and exception type
names. Never a file name from a manifest, a message from an adapter, or content.
"""
from __future__ import annotations

import logging
import sys


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
