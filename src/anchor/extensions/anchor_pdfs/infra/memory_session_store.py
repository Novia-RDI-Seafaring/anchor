"""In-memory IngestSessionStore - tests and ephemeral mode."""
from __future__ import annotations

import asyncio


class MemoryIngestSessionStore:
    def __init__(self) -> None:
        self._artifacts: dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()

    async def write_text(self, session_id: str, name: str, payload: str) -> None:
        async with self._lock:
            self._artifacts[(session_id, name)] = payload

    async def read_text(self, session_id: str, name: str) -> str | None:
        return self._artifacts.get((session_id, name))

    async def append_line(self, session_id: str, name: str, line: str) -> None:
        async with self._lock:
            prior = self._artifacts.get((session_id, name), "")
            self._artifacts[(session_id, name)] = prior + line.rstrip("\n") + "\n"

    async def list_session_ids(self) -> list[str]:
        return sorted({
            sid for (sid, name) in self._artifacts if name == "session.json"
        })

    async def delete_staged(self, session_id: str) -> None:
        async with self._lock:
            staged = [
                key for key in self._artifacts
                if key[0] == session_id and (
                    key[1].startswith("silver/") or key[1].startswith("gold/")
                )
            ]
            for key in staged:
                del self._artifacts[key]
