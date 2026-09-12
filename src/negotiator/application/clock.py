"""Monotonic elapsed time with explicit units and a terminal snapshot."""

import time
from collections.abc import Callable

from negotiator.domain.preferences import finite_number


class SessionClock:
    def __init__(self, duration_seconds: float, *, now: Callable[[], float] = time.monotonic):
        self.duration_seconds = finite_number(duration_seconds, "Duration")
        if self.duration_seconds <= 0:
            raise ValueError("Duration must be positive seconds.")
        self._now = now
        self._started = now()
        self._elapsed = 0.0
        self._stopped = False

    @property
    def elapsed_seconds(self) -> float:
        if not self._stopped:
            elapsed = finite_number(self._now() - self._started, "Clock elapsed time")
            self._elapsed = min(self.duration_seconds, max(self._elapsed, elapsed))
        return self._elapsed

    @property
    def elapsed_fraction(self) -> float:
        return self.elapsed_seconds / self.duration_seconds

    @property
    def remaining_seconds(self) -> float:
        return self.duration_seconds - self.elapsed_seconds

    @property
    def expired(self) -> bool:
        return self.remaining_seconds == 0

    def stop(self) -> None:
        self._elapsed = self.elapsed_seconds
        self._stopped = True
