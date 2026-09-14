"""Background lease renewal and bounded exponential backoff."""
from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable

from mergen_dispatcher.control import LeaseLost

LOG = logging.getLogger("mergen.dispatcher")


class Backoff:
    """Exponential delay with a ceiling. Jitter keeps two hosts from retrying
    in lockstep after a shared outage."""

    def __init__(self, initial: float, maximum: float, jitter: Callable[[], float] = random.random):
        self.initial, self.maximum, self._jitter = initial, maximum, jitter
        self.failures = 0

    def next(self) -> float:
        delay = min(self.maximum, self.initial * 2 ** min(self.failures, 32))
        self.failures += 1
        return delay * (0.5 + self._jitter() / 2)

    def reset(self) -> None:
        self.failures = 0


class LeaseKeeper:
    """Keeps one job lease alive from claim to publication.

    The VPS decides ownership: a refused renewal means another worker may hold
    the job now. Without a successful renewal the lease is also lost once its
    last known deadline passes, so a network outage cannot stretch it.
    `valid()` is what every step that could publish checks first.
    """

    def __init__(self, renew: Callable[[str], int], job_id: str, lease_seconds: int, *,
                 started: float, renew_every: float, backoff: Backoff,
                 clock: Callable[[], float] = time.monotonic):
        self._renew, self._job_id, self._clock, self._backoff = renew, job_id, clock, backoff
        self._renew_every = renew_every
        # From the moment the request left: the VPS set its deadline later.
        self._deadline = started + lease_seconds
        self._interval = min(renew_every, lease_seconds / 3)
        self._margin = min(5.0, lease_seconds / 10)
        self._lost = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"lease-{job_id[:8]}", daemon=True)

    def start(self) -> "LeaseKeeper":
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def lost(self) -> bool:
        return self._lost.is_set()

    def valid(self) -> bool:
        return not self._lost.is_set() and self._clock() < self._deadline - self._margin

    def _run(self) -> None:
        delay = self._interval
        while not self._stop.wait(delay):
            started = self._clock()
            try:
                seconds = self._renew(self._job_id)
            except LeaseLost:
                LOG.warning("job %s: the VPS refused the lease renewal", self._job_id[:8])
                self._lost.set()
                return
            except Exception as exc:  # noqa: BLE001 - any failure is "not renewed"
                remaining = self._deadline - self._clock()
                if remaining <= 0:
                    LOG.warning("job %s: lease expired without a renewal", self._job_id[:8])
                    self._lost.set()
                    return
                LOG.info("job %s: lease renewal failed (%s), retrying", self._job_id[:8],
                         type(exc).__name__)
                delay = max(0.01, min(self._backoff.next(), remaining / 2))
                continue
            self._backoff.reset()
            self._deadline = started + seconds
            self._interval = min(self._renew_every, seconds / 3)
            delay = self._interval
