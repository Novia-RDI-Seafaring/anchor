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
region geometry is named by grouping candidate item ids - the server
computes `bbox = union(member bboxes)` in BOTTOMLEFT space, so the agent
never emits free-form provenance coordinates. The `approx_bbox` escape
hatch (for visuals docling missed) is snapped to docling items and
stamped `geometry: snapped|coarse` so consumers see the difference.

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
from anchor.extensions.anchor_pdfs.core.ingest.validation import (
    REGION_KINDS,
    bbox_error,
    validate_region,
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
    render_pages_md,
    snap_to_docling_items,
    union_bbox,
)

PROTOCOL_VERSION = 1

MAX_POLISHED_MD_LEN = 400_000

#: Fields a submitted region may carry. The schema is closed: anything
#: else is rejected so drift between agent and server surfaces loudly.
_SUBMIT_REGION_FIELDS = frozenset({
    "id", "kind", "title", "description",
    "member_item_ids", "approx_bbox", "tags", "entities",
})

#: Server-owned per-page task statement, returned on every work item so
#: the skill only has to teach the loop shape, not the task itself.
PAGE_INSTRUCTIONS = (
    "Read the page image (image.path or base64) alongside raw_md. "
    "1) If needs_polish, rewrite raw_md into faithful markdown for this page: "
    "fix reading order, reconstruct tables, transcribe values exactly; never "
    "invent content that is not on the page. "
    "2) List the meaningful regions: for each, pick kind "
    f"({'|'.join(REGION_KINDS)}), a short title, a 1-2 sentence description, "
    "and name its geometry by listing the candidate item ids it covers in "
    "member_item_ids (the server computes the bbox from those). Only when no "
    "candidate covers a visual, send approx_bbox [left, top, right, bottom] "
    "in BOTTOMLEFT page coordinates instead. Optional: tags[], entities[] "
    "(product/model identifiers). "
    "3) Submit with ingest_submit_page; on a rejection, repair the named "
    "fields and resubmit (resubmitting a page replaces it)."
)


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
        return {
            "session_id": session["session_id"],
            "slug": session["slug"],
            "state": session.get("state", "open"),
            "protocol_version": session.get("protocol_version", PROTOCOL_VERSION),
            "page_count": session.get("page_count", len(pages)),
            "pages": pages,
            "resumed": resumed,
            "instructions": (
                "Per page: ingest_get_page -> read the image -> "
                "ingest_submit_page. When every page is submitted, call "
                "ingest_finalize. Resume any time via ingest_status."
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

        docling = await self.extractor.extract(bronze_path)
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
            return {"error": f"unknown session: {session_id}"}
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
            return {"accepted": False, "errors": [_err(0, "", f"unknown session: {session_id}")]}
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
        resolved, errors = self._resolve_regions(regions, page=page, candidates=candidates)

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

    def _resolve_regions(
        self,
        regions: Any,
        *,
        page: int,
        candidates: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Closed-schema check + server-side geometry resolution."""
        if not isinstance(regions, list):
            return [], [_err(0, "regions", "regions must be a list")]
        by_id = {
            c.get("id"): c for c in candidates
            if isinstance(c, dict) and isinstance(c.get("id"), str)
        }
        # snap_to_docling_items expects a docling-shaped dict; the persisted
        # candidates carry the same (label, bbox) payload, scoped to a page.
        docling_view = {"items": [{**c, "page": page} for c in by_id.values()]}
        resolved: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for i, raw in enumerate(regions):
            if not isinstance(raw, dict):
                errors.append(_err(i, "", "region must be an object"))
                continue
            unknown = sorted(set(raw) - _SUBMIT_REGION_FIELDS)
            if unknown:
                errors.append(_err(
                    i, ",".join(unknown),
                    f"unknown fields {unknown}; allowed: {sorted(_SUBMIT_REGION_FIELDS)}",
                ))
                continue

            member_ids = raw.get("member_item_ids")
            approx = raw.get("approx_bbox")
            bbox: list[float] = []
            geometry = ""
            if isinstance(member_ids, list) and member_ids:
                missing = [m for m in member_ids if m not in by_id]
                if missing:
                    errors.append(_err(
                        i, "member_item_ids",
                        f"unknown candidate ids on page {page}: {missing}",
                    ))
                    continue
                bbox = union_bbox([
                    list(by_id[m].get("bbox") or []) for m in member_ids
                ])
                if not bbox:
                    errors.append(_err(
                        i, "member_item_ids",
                        "named candidates have no usable bboxes; send approx_bbox instead",
                    ))
                    continue
                geometry = "members"
            elif approx is not None:
                msg = bbox_error(approx)
                if msg:
                    errors.append(_err(i, "approx_bbox", msg))
                    continue
                approx_f = [float(v) for v in approx]
                snapped, _idx = snap_to_docling_items(docling_view, page, approx_f)
                if snapped:
                    bbox = snapped
                    geometry = "snapped"
                else:
                    # Docling saw nothing under the box (full-bleed chart,
                    # scanned drawing). Keep the coarse box and say so.
                    bbox = approx_f
                    geometry = "coarse"
            else:
                errors.append(_err(
                    i, "member_item_ids",
                    "region needs geometry: member_item_ids (preferred) or approx_bbox",
                ))
                continue

            region: dict[str, Any] = {
                "id": raw.get("id") or f"r{i + 1}",
                "kind": raw.get("kind"),
                "title": raw.get("title"),
                "description": raw.get("description") or "",
                "page": page,
                "bbox": bbox,
                "geometry": geometry,
                "tags": raw.get("tags") or [],
                "entities": raw.get("entities") or [],
            }
            if geometry == "members":
                region["member_item_ids"] = list(member_ids)
            elif approx is not None:
                region["approx_bbox"] = [float(v) for v in approx]
            shape_errors = validate_region(region, index=i)
            if shape_errors:
                errors.extend(shape_errors)
                continue
            resolved.append(region)

        # Duplicate ids within one page would silently overwrite each other
        # downstream; reject so the agent fixes them.
        seen: set[str] = set()
        for i, region in enumerate(resolved):
            if region["id"] in seen:
                errors.append(_err(i, "id", f"duplicate region id {region['id']!r} on page {page}"))
            seen.add(region["id"])
        if errors:
            return [], errors
        return resolved, []

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
            return {"finalized": False, "error": f"unknown session: {session_id}"}
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

        # Local embeddings over the staged regions (title + description),
        # written before the marker so search never sees an unembedded doc.
        embedded_count = 0
        if self.embedder is not None:
            items: list[tuple[int, str, str]] = []
            for page, regions in sorted(staged_regions.items()):
                for r in regions:
                    rid = r.get("id")
                    text = f"{(r.get('title') or '').strip()}. {(r.get('description') or '').strip()}"
                    text = text.strip(". ").strip()
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
            return {"aborted": False, "error": f"unknown session: {session_id}"}
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
