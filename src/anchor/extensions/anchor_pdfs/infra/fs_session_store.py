"""Filesystem-backed IngestSessionStore.

Layout (mirrors the proposal in docs/proposals/harness-driven-ingestion.md):

    <data_dir>/staging/ingest/<session_id>/
        session.json
        journal.jsonl
        silver/pages/<n>.md
        gold/pages/<n>.regions.json

Nothing under staging/ is scanned by FsDocStore, so staged work stays
invisible to list/search/gold-map until finalize publishes it.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import aiofiles

from anchor.core.upload_safety import UnsafeUploadError, assert_within

#: Server-minted ids only ("ing-<uuid4 hex>"), but validate anyway: the id
#: arrives back over MCP/HTTP/CLI and becomes a directory name.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


class FsIngestSessionStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "staging" / "ingest"
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        if not _SESSION_ID_RE.fullmatch(session_id or ""):
            raise UnsafeUploadError(f"invalid session id: {session_id!r}")
        target = self.root / session_id
        assert_within(target, self.root)
        return target

    def _artifact_path(self, session_id: str, name: str) -> Path:
        base = self._session_dir(session_id)
        candidate = base / name
        # Containment: artifact names are produced by the session service,
        # but re-validate so a future caller cannot escape the session dir.
        resolved = (base / name).resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError as exc:
            raise UnsafeUploadError(f"artifact escapes session dir: {name!r}") from exc
        return candidate

    async def write_text(self, session_id: str, name: str, payload: str) -> None:
        target = self._artifact_path(session_id, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace: a crash mid-write must never leave a truncated
        # session.json (the resume surface folds over it).
        tmp = target.with_name(target.name + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(payload)
        os.replace(tmp, target)

    async def read_text(self, session_id: str, name: str) -> str | None:
        target = self._artifact_path(session_id, name)
        if not target.is_file():
            return None
        async with aiofiles.open(target, encoding="utf-8") as f:
            return await f.read()

    async def append_line(self, session_id: str, name: str, line: str) -> None:
        target = self._artifact_path(session_id, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "a", encoding="utf-8") as f:
            await f.write(line.rstrip("\n") + "\n")

    async def list_session_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            d.name for d in self.root.iterdir()
            if d.is_dir() and (d / "session.json").is_file()
        )

    async def delete_staged(self, session_id: str) -> None:
        base = self._session_dir(session_id)
        for sub in ("silver", "gold"):
            target = base / sub
            if target.is_dir():
                shutil.rmtree(target)
