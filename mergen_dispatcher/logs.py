"""Logging that cannot carry the worker token or the control address.

The code never logs those values, a URL or a job payload. This formatter is
the last line of defence: it removes them from every formatted record,
tracebacks included, should a third-party message ever contain them.
"""
from __future__ import annotations

import logging
import re
import sys
from urllib.parse import urlsplit

BEARER = re.compile(r"(?i)bearer\s+\S+")


class RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: list[str], fmt: str):
        super().__init__(fmt)
        self._secrets = sorted({value for value in secrets if value}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for value in self._secrets:
            text = text.replace(value, "[redacted]")
        return BEARER.sub("Bearer [redacted]", text)

    def format(self, record: logging.LogRecord) -> str:
        return self.redact(super().format(record))


def redacting_handler(config, stream=None) -> logging.Handler:
    host = urlsplit(config.control_url).hostname or ""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(RedactingFormatter([config.token, config.control_url, host],
                                            "%(levelname)s %(name)s: %(message)s"))
    return handler


def quiet_third_party() -> None:
    # httpx logs every request URL at INFO, and that URL is an infrastructure address.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_logging(config) -> None:
    root = logging.getLogger()
    root.handlers[:] = [redacting_handler(config)]
    root.setLevel(logging.INFO)
    quiet_third_party()
