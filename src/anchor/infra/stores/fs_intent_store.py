"""Filesystem-backed IntentStore — the durable project-level intent queue (#148).

Layout (one queue per project, under the project data dir):

    intents/
        <id>.json    # one Intent, JSON

Each file is one intent; the directory is the whole queue. Because the records
live on disk next to the corpus, the queue is visible to every process that
shares the data dir and a restart rebuilds it from disk — so a drop-to-ingest
enqueued by the UI is still there for an agent that connects later, even in a
different process. Writes are atomic (write-temp + ``os.replace``) so a
concurrent reader never sees a half-written file.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import aiofiles

from anchor.core.intents.intent import Intent
from anchor.core.upload_safety import UnsafeUploadError, assert_within

#: An intent id is a server-generated uuid fragment; this guards the on-disk
#: filename stem so a crafted id can never escape the intents directory.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class FsIntentStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "intents"
        self._lock = asyncio.Lock()

    def _path(self, intent_id: str) -> Path:
        if not intent_id or not _ID_RE.fullmatch(intent_id):
            raise UnsafeUploadError(f"unsafe intent id: {intent_id!r}")
        target = self.root / f"{intent_id}.json"
        assert_within(target, self.root)
        return target

    async def add(self, intent: Intent) -> Intent:
        await self._write(intent)
        return intent

    async def replace(self, intent: Intent) -> None:
        await self._write(intent)

    async def _write(self, intent: Intent) -> None:
        target = self._path(intent.id)
        async with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(intent.to_dict())
            tmp = target.with_suffix(".json.tmp")
            async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
                await f.write(payload)
            os.replace(tmp, target)

    async def get(self, intent_id: str) -> Intent | None:
        try:
            target = self._path(intent_id)
        except UnsafeUploadError:
            return None
        if not target.is_file():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return Intent.from_dict(data) if isinstance(data, dict) else None

    async def list(self) -> list[Intent]:
        out: list[Intent] = []
        if not self.root.is_dir():
            return out
        for p in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(data, dict):
                data.setdefault("id", p.stem)
                out.append(Intent.from_dict(data))
        return out
