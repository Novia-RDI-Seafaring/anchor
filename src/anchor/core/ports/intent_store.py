"""IntentStore protocol — durable, project-level agent-intent queue (#148).

The store is the source of truth for the pull half of the push-notify /
pull-payload design. It lives at the PROJECT level (one queue per project, not
per canvas), so an intent raised on any canvas is visible from every canvas in
the same project. Records are durable next to the corpus, so a queue survives a
restart and is visible to every process that shares the data dir (a server can
list it, a CLI can resolve it, an MCP-stdio subprocess can enqueue).

Implementations live in ``infra`` (filesystem) and the test doubles
(in-memory). Pure protocol here: no I/O, no framework imports.
"""
from __future__ import annotations

from typing import Protocol

from anchor.core.intents.intent import Intent


class IntentStore(Protocol):
    async def add(self, intent: Intent) -> Intent:
        """Persist a new intent. Idempotent on ``intent.id``."""
        raise NotImplementedError

    async def get(self, intent_id: str) -> Intent | None:
        """The intent with this id, or ``None`` when absent."""
        raise NotImplementedError

    async def list(self) -> list[Intent]:
        """Every intent in this project (pending and resolved), unfiltered.
        Filtering by canvas / status is the service's concern."""
        raise NotImplementedError

    async def replace(self, intent: Intent) -> None:
        """Overwrite an existing intent (used to mark it resolved)."""
        raise NotImplementedError
