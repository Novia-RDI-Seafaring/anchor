"""IngestSessionService - the harness-driven ingestion protocol.

Splits the pipeline at its natural seam: Anchor runs every mechanical
step (bronze stash, docling extraction, silver index + raw markdown +
page PNGs + candidate items), while the harness agent performs the two
cognitive steps (page-markdown polish, region grouping) page by page
through a transactional work-order protocol:

    ingest_begin    -> mechanical front half + open a journaled session
    ingest_get_page -> work item (image path, raw md, candidate boxes)
    ingest_submit_page -> validate + stage (idempotent per page)
    ingest_status   -> resume surface (pages done / remaining)
    ingest_finalize -> embeddings + atomic publish to gold
    ingest_abort    -> discard staging

The server is the trust boundary: submissions pass a closed schema, and
region geometry is named by grouping candidate item ids or selecting table
cells. The server computes provenance coordinates in the canonical top-left
PDF-points convention (#281). The
`approx_bbox` escape hatch (for visuals docling missed) is snapped to docling
items and stamped `geometry: snapped|coarse` so consumers see the difference.

Pure orchestration over ports; no I/O, no framework imports.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id, slugify
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_pdfs.core.events import (
    DocBronzed,
    DocGoldExtracted,
    DocIngested,
    DocPolished,
    DocSilvered,
)
from anchor.extensions.anchor_pdfs.core.ingest.region_resolution import (
    PAGE_INSTRUCTIONS,
    resolve_regions,
)
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.embedder import Embedder
from anchor.extensions.anchor_pdfs.core.ports.pdf_extractor import PdfExtractor
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer
from anchor.extensions.anchor_pdfs.core.ports.session_store import IngestSessionStore
from anchor.extensions.anchor_pdfs.core.silver import (
    build_index,
    build_page_candidates,
    build_pages_meta,
    needs_polish,
    normalize_items,
    region_search_text,
    render_pages_md,
)

PROTOCOL_VERSION = 2

MAX_POLISHED_MD_LEN = 400_000

def _err(index: int, field: str, message: str) -> dict[str, Any]:
    return {"region_index": index, "field": field, "message": message}


class IngestSessionService:
    """Sibling of IngestService for the harness protocol (see module doc)."""

    def __init__(
        self,
        doc_store: DocStore,
        session_store: IngestSessionStore,
        bus: EventBus,
        *,
        extractor: PdfExtractor,
        renderer: PdfRenderer,
        embedder: Embedder | None = None,
        embed_model_id: str | None = None,
        default_dpi: int = 150,
        clock: Clock | None = None,
        global_workspace_id: str = "_global",
    ) -> None:
        self.doc_store = doc_store
        self.sessions = session_store
        self.bus = bus
        self.extractor = extractor
        self.renderer = renderer
        self.embedder = embedder
        self.embed_model_id = embed_model_id or getattr(embedder, "model_id", None)
        self.default_dpi = default_dpi
        self.clock: Clock = clock or SystemClock()
        self._gid = global_workspace_id

    # ── Session persistence helpers ─────────────────────────────────────

    def _staging_root(self) -> str | None:
        root = getattr(self.sessions, "root", None)
        return str(root) if root is not None else None

    def _unknown_session(self, session_id: str) -> str:
        """Honest miss: say where we looked and how to fix a data-dir mismatch.

        The CLI default data dir depends on the invoking directory, so an
        agent that changes cwd between sibling commands resolves a different
        project and the session 'disappears'. Naming the searched root turns
        that from a dead end into a one-flag fix.
        """
        where = self._staging_root()
        looked = f" (searched {where})" if where else ""
        return (
            f"unknown session: {session_id}{looked}. Sessions live under "
            "<data_dir>/staging/ingest; if this session was created in a "
            "different project, pass --data-dir from the begin work order "
            "or run from that project folder."
        )

    async def _load_session(self, session_id: str) -> dict[str, Any] | None:
        raw = await self.sessions.read_text(session_id, "session.json")
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def _save_session(self, session: dict[str, Any]) -> None:
        session["updated_at"] = self.clock.now()
        await self.sessions.write_text(
            session["session_id"], "session.json", json.dumps(session, indent=2),
        )

    async def _journal(self, session_id: str, op: str, **fields: Any) -> None:
        entry = {"op": op, "ts": self.clock.now(), **fields}
        await self.sessions.append_line(session_id, "journal.jsonl", json.dumps(entry))

    async def _find_session_by_slug(self, slug: str, *, states: set[str]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for sid in await self.sessions.list_session_ids():
            session = await self._load_session(sid)
            if not session or session.get("slug") != slug:
                continue
            if session.get("state") not in states:
                continue
            if best is None or session.get("updated_at", 0) > best.get("updated_at", 0):
                best = session
        return best

    @staticmethod
    def _remaining_pages(session: dict[str, Any]) -> list[int]:
        return sorted(
            int(p) for p, info in (session.get("pages") or {}).items()
            if info.get("status") != "submitted"
        )

    def _work_order(self, session: dict[str, Any], *, resumed: bool) -> dict[str, Any]:
        pages = [
            {
                "page": int(p),
                "status": info.get("status", "pending"),
                "needs_polish": bool(info.get("needs_polish")),
                "candidate_count": int(info.get("candidate_count", 0)),
            }
            for p, info in sorted(
                (session.get("pages") or {}).items(), key=lambda kv: int(kv[0]),
            )
        ]
        # The data dir pins every follow-up call to the same project: the CLI
        # default is resolved from the invoking directory, so an agent that
        # changes cwd between sibling commands would otherwise lose the session.
        staging = self._staging_root()
        data_dir = str(Path(staging).parent.parent) if staging else None
        return {
            "session_id": session["session_id"],
            "slug": session["slug"],
            "state": session.get("state", "open"),
            "protocol_version": session.get("protocol_version", PROTOCOL_VERSION),
            "page_count": session.get("page_count", len(pages)),
            "pages": pages,
            "resumed": resumed,
            "data_dir": data_dir,
            "instructions": (
                "Per page: ingest_get_page -> read the image -> "
                "ingest_submit_page. When every page is submitted, call "
                "ingest_finalize. Resume any time via ingest_status. "
                "CLI callers: pass --data-dir <data_dir from this work order> "
                "on every ingest-session command; the default depends on the "
                "directory you invoke from."
            ),
        }

    # ── Operations ──────────────────────────────────────────────────────

    async def ingest_begin(
        self,
        pdf_bytes: bytes,
        filename: str,
        *,
        slug: str | None = None,
        dpi: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Mechanical front half + open (or resume) a session for `slug`."""
        dpi = self.default_dpi if dpi is None else dpi
        slug = slug or slugify(Path(filename).stem)

        # Same idempotency contract as the keyed pipeline: published gold
        # short-circuits unless forced.
        if not force and await self.doc_store.has_gold(slug):
            return {
                "slug": slug,
                "filename": filename,
                "skipped": True,
                "reason": "already ingested (gold exists); pass force=true to re-ingest",
            }

        # One open session per slug: begin on an open session resumes it;
        # a forced begin aborts it and starts fresh.
        existing = await self._find_session_by_slug(slug, states={"open", "finalizing"})
        if existing is not None:
            if not force:
                return self._work_order(existing, resumed=True)
            await self.ingest_abort(existing["session_id"])

        bronze_path = await self.doc_store.stash_bronze(pdf_bytes, filename)
        await self._publish(DocBronzed(slug=slug, bronze_path=str(bronze_path)))

        # Boundary normaliser (#281): top-left PDF points regardless of extractor.
        docling = normalize_items(await self.extractor.extract(bronze_path))
        index = build_index(docling, filename=filename)
        pages_md = render_pages_md(docling)
        pages_meta = build_pages_meta(docling)
        page_candidates = build_page_candidates(docling)
        await self.doc_store.write_silver_artifact(slug, "index.json", json.dumps(index))
        await self.doc_store.write_silver_artifact(slug, "pages.meta.json", json.dumps(pages_meta))
        for page, md in pages_md.items():
            await self.doc_store.write_silver_artifact(slug, f"pages/{page}.raw.md", md)
        for page, candidates in page_candidates.items():
            await self.doc_store.write_silver_artifact(
                slug, f"pages/{page}.candidates.json", json.dumps(candidates),
            )
        page_count = max(page_candidates, default=0)
        if page_count:
            page_pngs = await self.renderer.render_pages(bronze_path, dpi=dpi)
            for page, png in page_pngs.items():
                await self.doc_store.write_silver_artifact(slug, f"pages/{page}.png", png)
        await self._publish(DocSilvered(slug=slug, page_count=page_count))

        now = self.clock.now()
        session = {
            "session_id": f"ing-{uuid4().hex}",
            "slug": slug,
            "filename": filename,
            "state": "open",
            "protocol_version": PROTOCOL_VERSION,
            "dpi": dpi,
            "page_count": page_count,
            "pages": {
                str(page): {
                    "status": "pending",
                    "needs_polish": needs_polish(docling, page),
                    "candidate_count": len(candidates),
                    "region_count": 0,
                }
                for page, candidates in page_candidates.items()
            },
            "created_at": now,
            "updated_at": now,
        }
        await self._save_session(session)
        await self._journal(
            session["session_id"], "begin",
            slug=slug, filename=filename, page_count=page_count, force=force,
        )
        return self._work_order(session, resumed=False)

    async def ingest_get_page(self, session_id: str, page: int) -> dict[str, Any]:
        """Work item for one page: image path, raw markdown, candidate boxes."""
        session = await self._load_session(session_id)
        if session is None:
            return {"error": self._unknown_session(session_id)}
        if session.get("state") not in ("open", "finalizing"):
            return {"error": f"session {session_id} is {session.get('state')}; not readable"}
        page_info = (session.get("pages") or {}).get(str(page))
        if page_info is None:
            return {"error": f"page {page} not in session (1..{session.get('page_count')})"}
        slug = session["slug"]
        image_path = await self.doc_store.get_page_image_path(slug, page)
        raw_md = await self.doc_store.get_page_text(slug, page)
        candidates = await self.doc_store.get_page_candidates(slug, page) or []
        return {
            "session_id": session_id,
            "slug": slug,
            "page": page,
            "status": page_info.get("status", "pending"),
            "needs_polish": bool(page_info.get("needs_polish")),
            "image_path": str(image_path) if image_path is not None else None,
            "raw_md": raw_md or "",
            "candidates": candidates,
            "instructions": PAGE_INSTRUCTIONS,
            "protocol_version": session.get("protocol_version", PROTOCOL_VERSION),
        }

    async def ingest_submit_page(
        self,
        session_id: str,
        page: int,
        *,
        regions: list[dict[str, Any]],
        polished_md: str | None = None,
        protocol_version: int | None = None,
    ) -> dict[str, Any]:
        """Validate + stage one page. Idempotent: resubmitting replaces it."""
        session = await self._load_session(session_id)
        if session is None:
            return {"accepted": False, "errors": [_err(0, "", self._unknown_session(session_id))]}
        if session.get("state") != "open":
            return {"accepted": False, "errors": [_err(
                0, "", f"session is {session.get('state')}; only open sessions accept pages",
            )]}
        if protocol_version is not None and protocol_version != session.get(
            "protocol_version", PROTOCOL_VERSION,
        ):
            return {"accepted": False, "errors": [_err(
                0, "protocol_version",
                f"protocol_version {protocol_version} does not match the session's "
                f"{session.get('protocol_version', PROTOCOL_VERSION)}; re-run ingest_begin",
            )]}
        page_info = (session.get("pages") or {}).get(str(page))
        if page_info is None:
            return {"accepted": False, "errors": [_err(
                0, "page", f"page {page} not in session (1..{session.get('page_count')})",
            )]}

        slug = session["slug"]
        candidates = await self.doc_store.get_page_candidates(slug, page) or []
        resolved, errors = resolve_regions(regions, page=page, candidates=candidates)

        if polished_md is not None:
            if not isinstance(polished_md, str) or not polished_md.strip():
                errors.append(_err(0, "polished_md", "polished_md must be a non-empty string when given"))
            elif len(polished_md) > MAX_POLISHED_MD_LEN:
                errors.append(_err(0, "polished_md", f"polished_md too long (max {MAX_POLISHED_MD_LEN} chars)"))

        if errors:
            return {"accepted": False, "page": page, "errors": errors}

        await self.sessions.write_text(
            session_id, f"gold/pages/{page}.regions.json",
            json.dumps({"page": page, "regions": resolved}, indent=2),
        )
        if polished_md is not None:
            await self.sessions.write_text(session_id, f"silver/pages/{page}.md", polished_md)
        page_info["status"] = "submitted"
        page_info["region_count"] = len(resolved)
        page_info["has_polished_md"] = polished_md is not None
        await self._save_session(session)
        await self._journal(
            session_id, "submit_page",
            page=page, region_count=len(resolved), polished=polished_md is not None,
        )
        return {
            "accepted": True,
            "page": page,
            "region_count": len(resolved),
            "remaining_pages": self._remaining_pages(session),
        }


    async def ingest_status(
        self, session_id: str | None = None, *, slug: str | None = None,
    ) -> dict[str, Any]:
        """Resume surface: where is this session (or this slug's session)?"""
        session: dict[str, Any] | None = None
        if session_id:
            session = await self._load_session(session_id)
        elif slug:
            session = await self._find_session_by_slug(slug, states={"open", "finalizing"})
            if session is None:
                session = await self._find_session_by_slug(
                    slug, states={"published", "aborted"},
                )
        if session is None:
            ref = session_id or slug or "(nothing given)"
            return {"error": f"no ingest session found for {ref}"}
        return {
            "session_id": session["session_id"],
            "slug": session["slug"],
            "state": session.get("state"),
            "protocol_version": session.get("protocol_version", PROTOCOL_VERSION),
            "page_count": session.get("page_count", 0),
            "pages": [
                {
                    "page": int(p),
                    "status": info.get("status", "pending"),
                    "region_count": int(info.get("region_count", 0)),
                }
                for p, info in sorted(
                    (session.get("pages") or {}).items(), key=lambda kv: int(kv[0]),
                )
            ],
            "pages_remaining": self._remaining_pages(session),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
        }

    async def ingest_finalize(
        self,
        session_id: str,
        *,
        allow_missing_pages: list[int] | None = None,
        declared_model: str | None = None,
    ) -> dict[str, Any]:
        """Completeness check, embeddings, atomic publish to gold."""
        session = await self._load_session(session_id)
        if session is None:
            return {"finalized": False, "error": self._unknown_session(session_id)}
        if session.get("state") == "published":
            return {"finalized": False, "error": "session already published"}
        if session.get("state") == "aborted":
            return {"finalized": False, "error": "session was aborted; re-run ingest_begin"}

        allowed_missing = {int(p) for p in (allow_missing_pages or [])}
        remaining = self._remaining_pages(session)
        missing_pages = sorted(p for p in remaining if p in allowed_missing)
        pending = [p for p in remaining if p not in allowed_missing]
        if pending:
            return {
                "finalized": False,
                "error": "pages still pending; submit them or list them in allow_missing_pages",
                "pending_pages": pending,
            }

        slug = session["slug"]
        started_at = self.clock.now()
        session["state"] = "finalizing"
        await self._save_session(session)
        await self._journal(session_id, "finalize_start", declared_model=declared_model)

        # The marker is the commit point: flip it off first so a crash
        # mid-publish leaves the doc invisible-as-gold, never blended.
        await self.doc_store.clear_gold_complete(slug)

        submitted_pages = sorted(
            int(p) for p, info in (session.get("pages") or {}).items()
            if info.get("status") == "submitted"
        )
        region_count = 0
        polished_pages: list[int] = []
        staged_regions: dict[int, list[dict[str, Any]]] = {}
        for page in submitted_pages:
            raw = await self.sessions.read_text(session_id, f"gold/pages/{page}.regions.json")
            if raw is None:
                continue
            payload = json.loads(raw)
            regions = payload.get("regions", []) if isinstance(payload, dict) else []
            staged_regions[page] = regions
            await self.doc_store.write_gold_region_file(slug, page, regions)
            region_count += len(regions)
            md = await self.sessions.read_text(session_id, f"silver/pages/{page}.md")
            if md is not None:
                await self.doc_store.write_silver_artifact(slug, f"pages/{page}.md", md)
                polished_pages.append(page)

        # Local embeddings include trusted server-derived region content and
        # are written before the marker so search never sees an unembedded doc.
        embedded_count = 0
        if self.embedder is not None:
            items: list[tuple[int, str, str]] = []
            for page, regions in sorted(staged_regions.items()):
                for r in regions:
                    rid = r.get("id")
                    text = region_search_text(r)
                    if rid and text:
                        items.append((page, rid, text))
            if items:
                vectors = await self.embedder.embed([t for _, _, t in items])
                await self.doc_store.write_embeddings(slug, {
                    "embed_model": self.embed_model_id or "unknown",
                    "dim": len(vectors[0]) if vectors else 0,
                    "embedded_at": self.clock.now(),
                    "vectors": [
                        {"page": p, "region_id": rid, "text": text, "vector": vec}
                        for (p, rid, text), vec in zip(items, vectors, strict=True)
                    ],
                })
                embedded_count = len(items)

        finished_at = self.clock.now()
        report = {
            "slug": slug,
            "filename": session.get("filename", ""),
            "status": "success",
            "mode": "harness",
            "declared_model": declared_model,
            "protocol_version": session.get("protocol_version", PROTOCOL_VERSION),
            "session_id": session_id,
            "started_at": session.get("created_at"),
            "finished_at": finished_at,
            "finalize_duration_seconds": round(max(0.0, finished_at - started_at), 3),
            "page_count": session.get("page_count", 0),
            "polished_page_count": len(polished_pages),
            "region_count": region_count,
            "embedded_count": embedded_count,
            "missing_pages": missing_pages,
            "options": {"dpi": session.get("dpi"), "embed_model": self.embed_model_id if embedded_count else None},
        }
        await self.doc_store.write_silver_artifact(
            slug, "ingest-report.json", json.dumps(report, indent=2),
        )

        await self.doc_store.mark_gold_complete(slug, {
            "mode": "harness",
            "declared_model": declared_model,
            "region_count": region_count,
            "session_id": session_id,
            "completed_at": finished_at,
        })

        session["state"] = "published"
        await self._save_session(session)
        await self._journal(session_id, "finalize_done", region_count=region_count)

        summary = {
            "finalized": True,
            "slug": slug,
            "session_id": session_id,
            "mode": "harness",
            "declared_model": declared_model,
            "page_count": session.get("page_count", 0),
            "polished_pages": polished_pages,
            "region_count": region_count,
            "embedded_count": embedded_count,
            "missing_pages": missing_pages,
        }
        if polished_pages:
            await self._publish(DocPolished(slug=slug, polished_pages=polished_pages))
        await self._publish(DocGoldExtracted(slug=slug, region_count=region_count))
        await self._publish(DocIngested(slug=slug, summary=summary))
        return summary

    async def ingest_abort(self, session_id: str) -> dict[str, Any]:
        """Discard staging. Bronze/silver stay (deterministic, cheap)."""
        session = await self._load_session(session_id)
        if session is None:
            return {"aborted": False, "error": self._unknown_session(session_id)}
        if session.get("state") == "published":
            return {"aborted": False, "error": "session already published; nothing to abort"}
        await self.sessions.delete_staged(session_id)
        session["state"] = "aborted"
        await self._save_session(session)
        await self._journal(session_id, "abort")
        return {"aborted": True, "session_id": session_id, "slug": session["slug"]}

    async def _publish(self, evt: Any) -> None:
        await self.bus.publish(DomainEvent(
            id=new_event_id(),
            ts=self.clock.now(),
            workspace_id=self._gid,
            type=evt.type,
            payload=evt.model_dump(),
        ))
