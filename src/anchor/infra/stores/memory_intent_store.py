"""In-memory IntentStore — test double + ephemeral runtime (#148).

Mirrors :class:`anchor.infra.stores.fs_intent_store.FsIntentStore` semantics
without touching disk: idempotent upsert keyed on ``intent.id`` and a flat
project-level listing. Used by tests and any wiring that does not need the queue
to survive a restart.
"""
from __future__ import annotations

import asyncio

from anchor.core.intents.intent import Intent


class MemoryIntentStore:
    def __init__(self) -> None:
        self._items: dict[str, Intent] = {}
        self._lock = asyncio.Lock()

    async def add(self, intent: Intent) -> Intent:
        async with self._lock:
            self._items[intent.id] = intent.model_copy(deep=True)
        return intent

    async def replace(self, intent: Intent) -> None:
        async with self._lock:
            self._items[intent.id] = intent.model_copy(deep=True)

    async def get(self, intent_id: str) -> Intent | None:
        async with self._lock:
            found = self._items.get(intent_id)
            return found.model_copy(deep=True) if found is not None else None

    async def list(self) -> list[Intent]:
        async with self._lock:
            return [i.model_copy(deep=True) for i in self._items.values()]
