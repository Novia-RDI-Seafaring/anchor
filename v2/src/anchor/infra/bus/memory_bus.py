"""In-process EventBus — asyncio queues, multi-subscriber.

Subscribers get an async iterator that yields events tagged for their
workspace_id (or all events if subscribed globally with `None`).
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from anchor.core.events.envelope import DomainEvent


class MemoryEventBus:
    def __init__(self) -> None:
        self._subscribers: list[tuple[str | None, asyncio.Queue[DomainEvent | None]]] = []
        self._lock = asyncio.Lock()

    async def publish(self, event: DomainEvent) -> None:
        async with self._lock:
            targets = list(self._subscribers)
        for filter_id, queue in targets:
            if filter_id is None or filter_id == event.workspace_id:
                await queue.put(event)

    async def _register(self, filter_id: str | None) -> asyncio.Queue[DomainEvent | None]:
        async with self._lock:
            queue: asyncio.Queue[DomainEvent | None] = asyncio.Queue()
            self._subscribers.append((filter_id, queue))
            return queue

    async def _unregister(self, queue: asyncio.Queue[DomainEvent | None]) -> None:
        async with self._lock:
            self._subscribers = [(fid, q) for fid, q in self._subscribers if q is not queue]

    async def subscribe(self, workspace_id: str | None = None) -> AsyncIterator[DomainEvent]:
        """Yield events filtered to workspace_id (or all if None)."""
        queue = await self._register(workspace_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            await self._unregister(queue)

    async def close(self) -> None:
        """Cause every subscriber to terminate cleanly."""
        async with self._lock:
            queues = [q for _, q in self._subscribers]
        for q in queues:
            await q.put(None)
