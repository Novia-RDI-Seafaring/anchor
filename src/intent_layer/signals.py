"""Count-only notifications. Payloads remain in the durable inbox."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PendingSignal:
    origin_id: str | None
    count: int
    ts: float = 0.0


class PendingSignals(Protocol):
    async def publish(self, signal: PendingSignal) -> None:
        raise NotImplementedError
    def subscribe(self) -> AsyncIterator[PendingSignal]:
        raise NotImplementedError


class MemoryPendingSignals:
    """In-process notifications; does not coordinate independent writers."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[PendingSignal]] = set()

    async def publish(self, signal: PendingSignal) -> None:
        for queue in tuple(self._queues):
            queue.put_nowait(signal)

    async def subscribe(self) -> AsyncIterator[PendingSignal]:
        queue: asyncio.Queue[PendingSignal] = asyncio.Queue()
        self._queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues.discard(queue)
