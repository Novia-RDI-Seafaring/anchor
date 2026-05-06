"""Clock protocol — abstracted so tests can freeze time."""
from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    def now(self) -> float:
        return time.time()


class FixedClock:
    """Test helper: always returns the same timestamp."""

    def __init__(self, ts: float = 0.0):
        self._ts = ts

    def now(self) -> float:
        return self._ts

    def advance(self, delta: float) -> None:
        self._ts += delta
