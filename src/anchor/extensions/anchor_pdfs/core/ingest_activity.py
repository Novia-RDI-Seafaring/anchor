"""Ingest-activity record + registry — the project-level "what is ingesting"
surface (issue #51).

The bronze -> silver -> gold pipeline already streams ``IngestProgress`` and
``DocBronzed/.../DocIngested/DocIngestFailed`` on the in-process bus, but those
are bus-only: an ingest started by the CLI or an MCP-stdio subprocess runs in a
*different* process, so its progress never reaches a running ``anchor serve``.

The fix is a small durable record per in-flight ingest, written by
``IngestService`` through the ``DocStore`` as each stage advances. Because it
lives on disk next to the corpus, the same record is visible to every process
that shares the data dir: a server can list it, an agent can pull it, and a
restart rebuilds the whole surface from disk (so a crashed or out-of-process
ingest is still visible). ``IngestActivityRegistry`` is the read model over
those records; it is pure (no I/O of its own) and reads through the store port.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: How long a terminal (done / failed) record stays in the active listing
#: before it is pruned. Long enough that a UI poll/SSE tick reliably catches
#: the resolution and clears its row; short enough that the surface returns to
#: empty on its own. Callers can override per registry.
DEFAULT_TERMINAL_TTL_SECONDS = 20.0

#: Status values a record can carry. ``running`` = still in flight;
#: ``done`` / ``failed`` / ``empty_gold`` are terminal. ``empty_gold`` is a
#: gold pass that finished mechanically but produced 0 regions on a non-empty
#: document (issue #188) — distinct from ``done`` so an autonomous loop can
#: retry / re-ingest --force instead of reading it as success.
RUNNING = "running"
DONE = "done"
FAILED = "failed"
EMPTY_GOLD = "empty_gold"


@dataclass
class IngestActivity:
    """One in-flight (or just-resolved) ingest, as the activity surface sees it.

    ``current`` / ``total`` mirror the pipeline's ``IngestProgress`` so the UI
    can draw a progress bar; for stages without a natural denominator they are
    ``0`` / ``0`` and the UI shows an indeterminate bar.
    """

    slug: str
    filename: str = ""
    stage: str = "bronze"
    current: int = 0
    total: int = 0
    status: str = RUNNING
    started_at: float = 0.0
    updated_at: float = 0.0
    error: str | None = None

    @property
    def pct(self) -> int | None:
        """Whole-percent progress for the current stage, or ``None`` when the
        stage has no denominator (draw an indeterminate bar)."""
        if self.total <= 0:
            return None
        return max(0, min(100, round(100 * self.current / self.total)))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "slug": self.slug,
            "filename": self.filename,
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "pct": self.pct,
        }
        if self.error is not None:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IngestActivity:
        return cls(
            slug=str(raw.get("slug", "")),
            filename=str(raw.get("filename", "") or ""),
            stage=str(raw.get("stage", "bronze") or "bronze"),
            current=int(raw.get("current", 0) or 0),
            total=int(raw.get("total", 0) or 0),
            status=str(raw.get("status", RUNNING) or RUNNING),
            started_at=float(raw.get("started_at", 0.0) or 0.0),
            updated_at=float(raw.get("updated_at", 0.0) or 0.0),
            error=(str(raw["error"]) if raw.get("error") is not None else None),
        )


@dataclass
class IngestActivityRegistry:
    """Read model over the durable ingest-activity records.

    Stateless beyond config: every ``snapshot`` reads the records through the
    store port, so it reflects the current on-disk truth — including ingests
    started in another process and ones left behind by a crash. ``now`` is
    injected (the service clock) so the terminal-TTL prune is deterministic in
    tests.
    """

    store: Any  # DocStore (structural — keeps core free of the port import cycle)
    terminal_ttl_seconds: float = DEFAULT_TERMINAL_TTL_SECONDS
    _now: Any = field(default=None, repr=False)

    async def snapshot(self, *, now: float | None = None) -> list[IngestActivity]:
        """All ingests worth showing: every running record, plus terminal ones
        still inside the TTL window. Sorted newest-first by ``started_at``."""
        records = await self.store.list_ingest_activity()
        items = [IngestActivity.from_dict(r) for r in records]
        ref = now if now is not None else (self._now() if callable(self._now) else 0.0)
        kept: list[IngestActivity] = []
        for it in items:
            if it.status == RUNNING:
                kept.append(it)
                continue
            # Terminal: keep it briefly so the UI sees the resolution, then drop.
            if ref <= 0 or (ref - it.updated_at) <= self.terminal_ttl_seconds:
                kept.append(it)
        kept.sort(key=lambda a: (a.started_at, a.slug), reverse=True)
        return kept

    async def get(self, slug: str) -> IngestActivity | None:
        raw = await self.store.read_ingest_activity(slug)
        return IngestActivity.from_dict(raw) if raw is not None else None
