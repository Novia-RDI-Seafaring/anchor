"""Port-based orchestration for the bronze -> silver -> gold pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id, slugify
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_pdfs.core.document_retrieval import DocumentRetrieval
from anchor.extensions.anchor_pdfs.core.events import (
    DocBronzed,
    DocIngested,
    DocIngestFailed,
    DocPolished,
    DocSilvered,
    IngestProgress,
)
from anchor.extensions.anchor_pdfs.core.gold_ingest import (
    GOLD_EMPTY_MAX_ATTEMPTS as _GOLD_EMPTY_MAX_ATTEMPTS,
)
from anchor.extensions.anchor_pdfs.core.gold_ingest import (
    INGEST_LOCK_WAIT_SECONDS as _INGEST_LOCK_WAIT_SECONDS,
)
from anchor.extensions.anchor_pdfs.core.gold_ingest import (
    GoldIngest,
)
from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
    extract_pointed as _extract_pointed,
)
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.embedder import Embedder
from anchor.extensions.anchor_pdfs.core.ports.md_polisher import PageMdPolisher
from anchor.extensions.anchor_pdfs.core.ports.pdf_extractor import PdfExtractor
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer
from anchor.extensions.anchor_pdfs.core.ports.region_extractor import RegionExtractor
from anchor.extensions.anchor_pdfs.core.silver import (
    build_index,
    build_page_candidates,
    build_pages_meta,
    find_low_text_pages,
    low_text_pages_warning,
    render_pages_md,
)
from anchor.extensions.anchor_pdfs.core.synopsis_service import (
    SynopsisService as _SynopsisService,
)

GOLD_EMPTY_MAX_ATTEMPTS = _GOLD_EMPTY_MAX_ATTEMPTS
INGEST_LOCK_WAIT_SECONDS = _INGEST_LOCK_WAIT_SECONDS
SynopsisService = _SynopsisService


class IngestService:
    def __init__(
        self,
        store: DocStore,
        bus: EventBus,
        *,
        extractor: PdfExtractor,
        renderer: PdfRenderer,
        polisher: PageMdPolisher | None = None,
        region_extractor: RegionExtractor | None = None,
        embedder: Embedder | None = None,
        embed_model_id: str | None = None,
        default_polish_model: str = "gpt-5.4",
        default_region_model: str = "gpt-5.4",
        default_dpi: int = 150,
        clock: Clock | None = None,
        global_workspace_id: str = "_global",
    ) -> None:
        self.store = store
        self.bus = bus
        self.extractor = extractor
        self.renderer = renderer
        self.polisher = polisher
        self.region_extractor = region_extractor
        self.embedder = embedder
        # Persist the model id so server and browser consumers can interpret
        # embeddings. Prefer an explicit id over the embedder's own attribute.
        self.embed_model_id = embed_model_id or getattr(embedder, "model_id", None)
        self.default_polish_model = default_polish_model
        self.default_region_model = default_region_model
        self.default_dpi = default_dpi
        self.clock: Clock = clock or SystemClock()
        self._gid = global_workspace_id
        self._retrieval = DocumentRetrieval(
            store,
            embedder=self.embedder,
            embed_model_id=self.embed_model_id,
            clock=self.clock,
            publish=self._publish,
        )

    async def ingest_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        *,
        slug: str | None = None,
        workspace_id: str | None = None,
        polish: bool = True,
        regions: bool = True,
        force: bool = False,
        full_page_ocr: bool = False,
        polish_model: str | None = None,
        region_model: str | None = None,
        dpi: int | None = None,
    ) -> dict[str, Any]:
        polish_model = polish_model or self.default_polish_model
        region_model = region_model or self.default_region_model
        dpi = self.default_dpi if dpi is None else dpi
        slug = slug or slugify(Path(filename).stem)

        # Idempotent by contract: if this slug is already gold-extracted, skip the
        # whole (billed, overwriting) pipeline unless the caller forces a fresh
        # pass. Matches the skill's "don't re-ingest unless asked for a fresh pass".
        # Keyed on actual gold completeness (the marker), not silver presence:
        # a crash-interrupted run or a --skip-regions pass is NOT "already
        # ingested" and re-running it completes the document.
        if not force and await self.store.has_gold(slug):
            return {
                "slug": slug,
                "filename": filename,
                "skipped": True,
                "reason": "already ingested (gold exists); pass force=True / --force to "
                "re-ingest and overwrite",
            }
        publish_workspace_id = workspace_id or self._gid
        ingest_started_at = self.clock.now()
        # Live activity record (issue #51): updated through the store as each
        # stage advances so the project-level "what is ingesting" surface sees
        # this run cross-process and after a restart. Bookkeeping only; a
        # write hiccup must never affect the pipeline, so writes are guarded.
        activity = {
            "slug": slug,
            "filename": filename,
            "stage": "bronze",
            "current": 0,
            "total": 0,
            "status": "running",
            "started_at": ingest_started_at,
            "updated_at": ingest_started_at,
        }

        async def record_activity(
            stage: str, *, current: int = 0, total: int = 0,
            status: str = "running", error: str | None = None,
        ) -> None:
            activity.update(
                stage=stage, current=current, total=total, status=status,
                updated_at=self.clock.now(),
            )
            if error is not None:
                activity["error"] = error
            try:
                await self.store.write_ingest_activity(slug, dict(activity))
            except Exception:  # noqa: BLE001 - never let bookkeeping break ingest
                pass

        await record_activity("bronze")
        stages: list[dict[str, Any]] = []
        # Tracks the pipeline stage in flight so a crash reports the real
        # failing stage (not a hardcoded "unknown") on the bus + in the
        # persisted failure record. Updated as each stage begins.
        current_stage = "bronze"

        def finish_stage(stage: str, started_at: float, **fields: Any) -> None:
            finished_at = self.clock.now()
            stages.append({
                "stage": stage,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_seconds": round(max(0.0, finished_at - started_at), 3),
                **fields,
            })

        bronze_path: Path | None = None
        try:
            stage_started_at = self.clock.now()
            bronze_path = await self.store.stash_bronze(pdf_bytes, filename)
            finish_stage("bronze", stage_started_at, output_path=str(bronze_path))
            await self._publish(DocBronzed(slug=slug, bronze_path=str(bronze_path)), publish_workspace_id)

            current_stage = "silver_extract"
            await self._publish(IngestProgress(slug=slug, stage="silver_extract", current=0, total=1), publish_workspace_id)
            await record_activity("silver_extract", current=0, total=1)
            stage_started_at = self.clock.now()
            docling = await self.extractor.extract(
                bronze_path, full_page_ocr=full_page_ocr
            )
            finish_stage(
                "silver_extract",
                stage_started_at,
                item_count=len(docling.get("items", [])),
            )
            page_count = max(
                (int(it["page"]) for it in docling.get("items", []) if isinstance(it.get("page"), (int, float))),
                default=0,
            )
            # Detect pages docling emitted almost no text for (no text layer /
            # vector or scanned content) and surface a non-fatal warning naming
            # them + the full-page-OCR remedy (issue #231). Only when the caller
            # did not already request full-page OCR — that is the remedy.
            low_text_warning: str | None = None
            if not full_page_ocr:
                low_text_pages = find_low_text_pages(docling, page_count)
                low_text_warning = low_text_pages_warning(low_text_pages)
                if low_text_warning:
                    await self._publish(
                        IngestProgress(
                            slug=slug,
                            stage="silver_low_text_warning",
                            current=len(low_text_pages),
                            total=page_count,
                        ),
                        publish_workspace_id,
                    )
            current_stage = "silver_index"
            stage_started_at = self.clock.now()
            index = build_index(docling, filename=filename)
            pages_md = render_pages_md(docling)
            pages_meta = build_pages_meta(docling)
            page_candidates = build_page_candidates(docling)
            await self.store.write_silver_artifact(slug, "index.json", json.dumps(index))
            await self.store.write_silver_artifact(slug, "pages.meta.json", json.dumps(pages_meta))
            for page, md in pages_md.items():
                await self.store.write_silver_artifact(slug, f"pages/{page}.raw.md", md)
            # Persist the per-page docling candidate items (id, label, bbox,
            # text). They power region grouping in the harness protocol and
            # make a session survivable across a crash; until now they only
            # existed in memory during this call.
            for page, candidates in page_candidates.items():
                await self.store.write_silver_artifact(
                    slug, f"pages/{page}.candidates.json", json.dumps(candidates),
                )
            finish_stage(
                "silver_index",
                stage_started_at,
                page_count=page_count,
                page_markdown_count=len(pages_md),
            )

            page_pngs: dict[int, bytes] = {}
            items_by_page: dict[int, list[dict[str, Any]]] = {}
            if page_count:
                current_stage = "silver_render_pages"
                stage_started_at = self.clock.now()
                page_pngs = await self.renderer.render_pages(bronze_path, dpi=dpi)
                for page, png in page_pngs.items():
                    await self.store.write_silver_artifact(slug, f"pages/{page}.png", png)
                for it in docling.get("items", []):
                    if isinstance(it.get("page"), (int, float)):
                        items_by_page.setdefault(int(it["page"]), []).append(it)
                finish_stage(
                    "silver_render_pages",
                    stage_started_at,
                    page_count=len(page_pngs),
                    dpi=dpi,
                )
            await self._publish(DocSilvered(slug=slug, page_count=page_count), publish_workspace_id)

            polished_pages: list[int] = []
            if polish and self.polisher and page_count:
                current_stage = "silver_polish"
                stage_started_at = self.clock.now()
                page_timings: list[dict[str, Any]] = []
                for page, png in page_pngs.items():
                    page_started_at = self.clock.now()
                    polished = await self.polisher.polish_page(
                        page_image=png,
                        page_no=page,
                        deterministic_md=pages_md.get(page, ""),
                        docling_items=items_by_page.get(page, []),
                        model=polish_model,
                    )
                    await self.store.write_silver_artifact(slug, f"pages/{page}.md", polished)
                    polished_pages.append(page)
                    page_finished_at = self.clock.now()
                    page_timings.append({
                        "page": page,
                        "started_at": page_started_at,
                        "finished_at": page_finished_at,
                        "duration_seconds": round(max(0.0, page_finished_at - page_started_at), 3),
                    })
                    await self._publish(IngestProgress(
                        slug=slug, stage="silver_polish", current=page, total=page_count,
                    ), publish_workspace_id)
                    await record_activity("silver_polish", current=page, total=page_count)
                finish_stage(
                    "silver_polish",
                    stage_started_at,
                    page_count=len(polished_pages),
                    model=polish_model,
                    pages=page_timings,
                )
                await self._publish(DocPolished(slug=slug, polished_pages=polished_pages), publish_workspace_id)

            region_count = 0
            invalid_region_count = 0
            region_errors: list[dict[str, Any]] = []
            gold_completed = False
            empty_gold = False
            gold_attempts = 0
            if regions and self.region_extractor and page_count:
                current_stage = "gold_regions"
                gold = await GoldIngest(
                    self.store,
                    self.region_extractor,
                    self.clock,
                    self._publish,
                ).run(
                    slug=slug,
                    docling=docling,
                    page_pngs=page_pngs,
                    items_by_page=items_by_page,
                    page_count=page_count,
                    model=region_model,
                    workspace_id=publish_workspace_id,
                    record_activity=record_activity,
                    finish_stage=finish_stage,
                )
                region_count = gold.region_count
                invalid_region_count = gold.invalid_region_count
                region_errors = gold.region_errors
                gold_completed = gold.completed
                empty_gold = gold.empty
                gold_attempts = gold.attempts


            embedded_count = 0
            if self.embedder is not None:
                current_stage = "embed"
                await record_activity("embed")
                stage_started_at = self.clock.now()
                embedded_count = await self.embed_document(
                    slug, publish_workspace_id=publish_workspace_id,
                )
                finish_stage(
                    "embed",
                    stage_started_at,
                    embedded_count=embedded_count,
                    embed_model=self.embed_model_id,
                )

            ingest_finished_at = self.clock.now()
            # A gold pass that produced 0 regions on a non-empty document is a
            # surfaced non-ok outcome (issue #188): record it as `empty_gold`
            # with an actionable reason so list_documents / the ingest-activity
            # surface flag it, instead of a silent `success` that an autonomous
            # loop reads as done.
            empty_gold_reason = (
                f"gold extraction produced 0 regions after {gold_attempts} "
                f"attempt(s) on a {page_count}-page document. This is usually a "
                "transient region-extraction failure, not a region-less PDF; "
                "re-ingest (pass --force / force=True if the slug now reports gold) "
                "to retry the gold stage."
            )
            timing_report = {
                "slug": slug,
                "filename": filename,
                "status": "empty_gold" if empty_gold else "success",
                "started_at": ingest_started_at,
                "finished_at": ingest_finished_at,
                "duration_seconds": round(max(0.0, ingest_finished_at - ingest_started_at), 3),
                "page_count": page_count,
                "polished_page_count": len(polished_pages),
                "region_count": region_count,
                "invalid_region_count": invalid_region_count,
                "region_errors": region_errors,
                "gold_complete": gold_completed,
                "gold_attempts": gold_attempts,
                "mode": "keyed",
                "embedded_count": embedded_count,
                "options": {
                    "polish": polish,
                    "regions": regions,
                    "polish_model": polish_model if polish and self.polisher else None,
                    "region_model": region_model if regions and self.region_extractor else None,
                    "dpi": dpi,
                    "embed_model": self.embed_model_id if embedded_count else None,
                },
                "stages": stages,
            }
            if empty_gold:
                timing_report["reason"] = empty_gold_reason
            if low_text_warning:
                timing_report["warnings"] = [low_text_warning]
            timing_report_path = await self.store.write_silver_artifact(
                slug,
                "ingest-report.json",
                json.dumps(timing_report, indent=2),
            )

            summary = {
                "slug": slug,
                "filename": filename,
                "page_count": page_count,
                "polished_pages": polished_pages,
                "region_count": region_count,
                "invalid_region_count": invalid_region_count,
                "embedded_count": embedded_count,
                "embed_model": self.embed_model_id if embedded_count else None,
                "timing_report_path": str(timing_report_path),
                "duration_seconds": timing_report["duration_seconds"],
            }
            if empty_gold:
                summary["status"] = "empty_gold"
                summary["reason"] = empty_gold_reason
            if low_text_warning:
                summary["warnings"] = [low_text_warning]
            await record_activity(
                current_stage,
                status="empty_gold" if empty_gold else "done",
                error=empty_gold_reason if empty_gold else None,
            )
            await self._publish(DocIngested(slug=slug, summary=summary), publish_workspace_id)
            return summary

        except Exception as exc:  # surface the failure on the bus before re-raising
            # Persist a failure record so the orphaned bronze (stashed but
            # never silvered) becomes visible as a failed document through
            # list_documents instead of silently absent. Bookkeeping is
            # wrapped so a write hiccup can never mask the original error.
            try:
                await self.store.write_ingest_failure(
                    slug,
                    filename=filename,
                    stage=current_stage,
                    error=str(exc),
                    bronze_path=str(bronze_path) if bronze_path is not None else None,
                    failed_at=self.clock.now(),
                )
            except Exception:  # noqa: BLE001 - never let bookkeeping mask the real failure
                pass
            await record_activity(current_stage, status="failed", error=str(exc))
            await self._publish(DocIngestFailed(slug=slug, stage=current_stage, error=str(exc)), publish_workspace_id)
            raise

    async def embed_document(
        self,
        slug: str,
        *,
        publish_workspace_id: str | None = None,
    ) -> int:
        """Embed one document through the retrieval collaborator."""
        return await self._retrieval.embed_document(
            slug,
            publish_workspace_id=publish_workspace_id,
        )

    async def search(self, query: str, *, k: int = 10) -> dict[str, Any]:
        """Search document embeddings through the retrieval collaborator."""
        return await self._retrieval.search(query, k=k)

    async def derive_region(
        self, slug: str, parent_region_id: str, region: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist a region derived from an existing gold region.

        The generic consumer side of an OIP region producer: a producer
        (e.g. the chart digitizer) hands back a new region derived from one
        it consumed; this links it to its parent and stores it durably. The
        derived region keeps the parent's ``source_ref`` (so provenance
        points at the same page and bbox) and records ``derived_from``.
        Producer-agnostic: the only chart-specific knowledge lives in the
        producer, not here.

        Visible immediately via ``get_regions`` / ``get_gold_map``;
        searchable after the next ``embed`` pass. Raises ``ValueError`` if
        the parent region does not exist.
        """
        regions = await self.store.get_regions(slug)
        parent: dict[str, Any] | None = None
        for _page, regs in (regions.get("pages") or {}).items():
            for r in regs:
                if isinstance(r, dict) and r.get("id") == parent_region_id:
                    parent = r
                    break
            if parent is not None:
                break
        if parent is None:
            raise ValueError(
                f"derive_region: parent region {parent_region_id!r} not found in {slug!r}"
            )

        derived = dict(region)
        derived["derived_from"] = parent_region_id
        # Inherit the parent's provenance unless the producer set its own.
        if not derived.get("source_ref") and parent.get("source_ref"):
            derived["source_ref"] = parent["source_ref"]

        path = await self.store.add_derived_region(slug, derived)
        return {
            "slug": slug,
            "region_id": derived.get("id"),
            "kind": derived.get("kind"),
            "derived_from": parent_region_id,
            "path": str(path),
        }

    async def extract_pointed(
        self,
        slug: str,
        *,
        select: dict[str, Any] | None,
        shape: Any,
    ) -> dict[str, Any]:
        """Pointed extraction: selected regions/entities into a caller shape.

        Resolves ``select`` (region ids / pages / entity) to gold regions and
        fills ``shape`` (by-example or JSON Schema) from their cells, attaching
        a ``source_ref`` provenance entry per filled leaf and listing
        unfillable leaves in ``unfilled``. Pure-core mechanics live in
        ``pointed_extraction``; this is the service seam the adapters call so
        MCP / CLI / HTTP reach the same code path. Raises
        ``PointedExtractionError`` for an unknown slug / missing gold layer.
        """
        return await _extract_pointed(
            store=self.store, slug=slug, select=select, shape=shape,
        )

    async def _publish(self, evt: Any, workspace_id: str | None = None) -> None:
        await self.bus.publish(DomainEvent(
            id=new_event_id(),
            ts=self.clock.now(),
            workspace_id=workspace_id or self._gid,
            type=evt.type,
            payload=evt.model_dump(),
        ))
