"""IngestSessionStore protocol - journaled staging for harness ingest sessions.

A session is a named bag of text artifacts under one session id:

    session.json               state fold target (slug, page statuses, ...)
    journal.jsonl              append-only begin/submit/finalize/abort entries
    silver/pages/<n>.md        staged polished markdown
    gold/pages/<n>.regions.json  staged validated regions

Nothing in this store is scanned by the DocStore, so staged work is
invisible to list/search until `ingest_finalize` publishes it through the
DocStore and commits the gold completeness marker.
"""
from __future__ import annotations

from typing import Protocol


class IngestSessionStore(Protocol):
    async def write_text(self, session_id: str, name: str, payload: str) -> None:
        """Write (replace) a text artifact. Implementations should make the
        replace atomic so a crash never leaves a half-written session.json."""
        raise NotImplementedError

    async def read_text(self, session_id: str, name: str) -> str | None:
        """Read a text artifact, or None when it does not exist."""
        raise NotImplementedError

    async def append_line(self, session_id: str, name: str, line: str) -> None:
        """Append one line to a journal-style artifact (creates it if needed)."""
        raise NotImplementedError

    async def list_session_ids(self) -> list[str]:
        """Every known session id, in stable (sorted) order."""
        raise NotImplementedError

    async def delete_staged(self, session_id: str) -> None:
        """Discard the staged silver/gold artifacts of a session, keeping
        session.json and the journal for the audit trail."""
        raise NotImplementedError
