"""IngestService — orchestrates the bronze → silver → gold pipeline.

Pure orchestrator over ports; does not import docling/pymupdf/openai.
Emits IngestProgress + DocBronzed/Silvered/.../Ingested on the bus.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id, slugify
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_pdfs.core.events import (
    DocBronzed,
    DocGoldExtracted,
    DocIngested,
    DocIngestFailed,
    DocPolished,
    DocSilvered,
    IngestProgress,
)
from anchor.extensions.anchor_pdfs.core.ingest.validation import validate_regions
from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
    extract_pointed as _extract_pointed,
)
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.embedder import Embedder
from anchor.extensions.anchor_pdfs.core.ports.md_polisher import PageMdPolisher
from anchor.extensions.anchor_pdfs.core.ports.pdf_extractor import PdfExtractor
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer
from anchor.extensions.anchor_pdfs.core.ports.region_extractor import RegionExtractor
from anchor.extensions.anchor_pdfs.core.ports.synopsis_renderer import (
    MarkdownSynopsisRenderer,
    PdfSynopsisRenderer,
)
from anchor.extensions.anchor_pdfs.core.search import search as _search_topk
from anchor.extensions.anchor_pdfs.core.silver import (
    build_index,
    build_page_candidates,
    build_pages_meta,
    render_pages_md,
    snap_to_docling_items,
    table_bbox_from_items,
    table_cells_from_items,
)
from anchor.extensions.anchor_pdfs.core.synopsis import SynopsisData, compose_synopsis

#: How many times the keyed gold pass is run while it produces 0 regions on a
#: non-empty document before giving up and surfacing `empty_gold` (issue #188).
#: A transient region-extraction failure (empty model response, a timeout that
#: yielded nothing) usually clears on a fresh pass; a genuinely region-less PDF
#: keeps returning 0 and is surfaced as empty_gold after the attempts. Total
#: attempts, not extra retries: 2 means one initial pass plus one retry.
GOLD_EMPTY_MAX_ATTEMPTS = 2

#: Default seconds an ingest waits for the per-slug lock before failing fast
#: (issue #175). A concurrent --force on the same slug holds the lock for its
#: gold pass; rather than block forever, a second ingest waits up to this long
#: then surfaces a clear "another ingest is running" error. Sized above a long
#: gold pass so genuine back-to-back runs queue cleanly, short enough that a
#: wedged run does not hang a caller indefinitely.
INGEST_LOCK_WAIT_SECONDS = 30 * 60


class SynopsisService:
    """Orchestrates entity-scoped synopsis composition for a document.

    Pulls filtered facts via ``compose_synopsis`` (pure core function),
    then delegates output to a renderer port. Kept separate from
    ``IngestService`` because their dependencies barely overlap — ingest
    needs extractors + polishers; synopsis only needs read access and
    a renderer.
    """

    def __init__(
        self,
        store: DocStore,
        *,
        pdf_renderer: PdfSynopsisRenderer | None = None,
        md_renderer: MarkdownSynopsisRenderer | None = None,
    ) -> None:
        self.store = store
        self.pdf_renderer = pdf_renderer
        self.md_renderer = md_renderer

    async def compose(self, *, slug: str, entity: str) -> SynopsisData:
        return await compose_synopsis(store=self.store, slug=slug, entity=entity)

    async def render_pdf(self, *, slug: str, entity: str) -> bytes:
        if self.pdf_renderer is None:
            raise RuntimeError("SynopsisService: no pdf_renderer wired")
        data = await self.compose(slug=slug, entity=entity)
        return await self.pdf_renderer.render_pdf(
            data, resolve_crop=self.store.get_crop_path,
        )

    async def render_markdown(
        self, *, slug: str, entity: str, crop_url_base: str | None = None,
    ) -> str:
        if self.md_renderer is None:
            raise RuntimeError("SynopsisService: no md_renderer wired")
        data = await self.compose(slug=slug, entity=entity)
        if crop_url_base is None:
            crop_url_for = None
        else:
            def crop_url_for(_slug: str, rel: str) -> str:
                return f"{crop_url_base.rstrip('/')}/{_slug}/crops/{rel}"
        return self.md_renderer.render_markdown(data, crop_url_for=crop_url_for)


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
        # The embed_model id is what gets persisted in embeddings.json so
        # consumers (server-side search, in-browser WASM) know which model
        # was used. If not given, fall back to a string attribute exposed
        # by the embedder if it has one (e.g. LocalSentenceTransformerEmbedder).
        self.embed_model_id = embed_model_id or getattr(embedder, "model_id", None)
        self.default_polish_model = default_polish_model
        self.default_region_model = default_region_model
        self.default_dpi = default_dpi
        self.clock: Clock = clock or SystemClock()
        self._gid = global_workspace_id

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
        # this run cross-process and after a restart. Bookkeeping only — a
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
            docling = await self.extractor.extract(bronze_path)
            finish_stage(
                "silver_extract",
                stage_started_at,
                item_count=len(docling.get("items", [])),
            )
            page_count = max(
                (int(it["page"]) for it in docling.get("items", []) if isinstance(it.get("page"), (int, float))),
                default=0,
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
                # Single-writer guard (issue #175): hold a per-slug lock for the
                # whole overwriting gold pass (clear marker -> region loop ->
                # finalize). Two concurrent `anchor ingest --force` on one slug
                # would otherwise interleave their clear/write/mark and leave
                # `.complete.json` desynced from the real artifacts. We wait a
                # bounded time then fail fast with a clear message rather than
                # block forever. The lock spans every retry attempt so the
                # bounded #188 retry stays a single critical section.
                async with self.store.ingest_lock(
                    slug, wait=True, timeout=INGEST_LOCK_WAIT_SECONDS,
                ):
                    # Bounded retry of the whole gold pass (issue #188). A
                    # transient region-extraction failure can yield 0 regions on
                    # a document that genuinely has them; a fresh pass usually
                    # recovers. We retry while the pass produces 0 regions on a
                    # non-empty document, up to GOLD_EMPTY_MAX_ATTEMPTS total. A
                    # doc that genuinely has no extractable regions keeps
                    # returning 0, exits the loop, and is surfaced as empty_gold
                    # (not a silent ok) below.
                    while True:
                        gold_attempts += 1
                        region_count = 0
                        invalid_region_count = 0
                        region_errors = []
                        stage_started_at = self.clock.now()
                        page_timings = []
                        # Mark gold incomplete before the (overwriting) loop so a
                        # crash mid-loop leaves the document invisible-as-gold
                        # instead of a partial blend that reads as complete.
                        await self.store.clear_gold_complete(slug)
                        for page, png in page_pngs.items():
                            page_started_at = self.clock.now()
                            raw_regions = await self.region_extractor.extract_page(
                                page_image=png,
                                page_no=page,
                                docling_items=items_by_page.get(page, []),
                                model=region_model,
                            )
                            snapped: list[dict[str, Any]] = []
                            for r in raw_regions:
                                if not isinstance(r, dict):
                                    snapped.append(r)
                                    continue
                                bbox_any = r.get("bbox") or r.get("approximate_bbox")
                                bbox_list: list[float] = list(bbox_any) if isinstance(bbox_any, list) else []
                                if len(bbox_list) == 4:
                                    snap_bbox, item_indexes = snap_to_docling_items(docling, page, bbox_list)
                                    if snap_bbox:
                                        r = {**r, "bbox": snap_bbox}
                                        cells = table_cells_from_items(
                                            docling.get("items", []),
                                            item_indexes,
                                            region_bbox=bbox_list,
                                        )
                                        if cells and r.get("kind") in {"table", "spec_block"}:
                                            r = {**r, "cells": cells}
                                        table_bbox = table_bbox_from_items(
                                            docling.get("items", []),
                                            item_indexes,
                                            region_bbox=bbox_list,
                                        )
                                        if table_bbox and r.get("kind") == "table":
                                            r = {**r, "bbox": table_bbox}
                                    elif "bbox" not in r:
                                        r = {**r, "bbox": bbox_list}
                                snapped.append(r)
                            # Shared schema gate: only valid regions reach gold.
                            # Invalid ones are dropped and reported instead of
                            # silently persisted (or swallowed upstream).
                            valid, page_errors = validate_regions(snapped)
                            if page_errors:
                                invalid_region_count += len(snapped) - len(valid)
                                region_errors.extend({**e, "page": page} for e in page_errors)
                            await self.store.write_gold_region_file(slug, page, valid)
                            region_count += len(valid)
                            page_finished_at = self.clock.now()
                            page_timings.append({
                                "page": page,
                                "region_count": len(valid),
                                "invalid_region_count": len(snapped) - len(valid),
                                "started_at": page_started_at,
                                "finished_at": page_finished_at,
                                "duration_seconds": round(max(0.0, page_finished_at - page_started_at), 3),
                            })
                            await self._publish(IngestProgress(
                                slug=slug, stage="gold_regions", current=page, total=page_count,
                            ), publish_workspace_id)
                            await record_activity("gold_regions", current=page, total=page_count)
                        finish_stage(
                            "gold_regions",
                            stage_started_at,
                            attempt=gold_attempts,
                            page_count=len(page_timings),
                            region_count=region_count,
                            invalid_region_count=invalid_region_count,
                            model=region_model,
                            pages=page_timings,
                        )
                        if region_count > 0 or gold_attempts >= GOLD_EMPTY_MAX_ATTEMPTS:
                            break
                        # 0 regions on a non-empty doc: retry the whole pass once
                        # more before giving up. Keep the bus/activity honest
                        # about the retry so a watcher does not read the empty
                        # pass as done.
                        await self._publish(IngestProgress(
                            slug=slug, stage="gold_regions_retry",
                            current=gold_attempts, total=GOLD_EMPTY_MAX_ATTEMPTS,
                        ), publish_workspace_id)

                    # 0 regions on a document that has pages/text is treated as a
                    # surfaced empty-gold outcome, not a silent ok (issue #188).
                    # We do NOT mark gold complete: has_gold stays false, so a
                    # consumer never mistakes an empty extraction for a finished
                    # one, and a re-ingest (no --force needed) re-runs the gold
                    # stage. A genuinely region-less PDF lands here too; it is
                    # surfaced as empty_gold with a reason rather than a false ok.
                    empty_gold = region_count == 0
                    if empty_gold:
                        await self._publish(
                            DocGoldExtracted(slug=slug, region_count=0), publish_workspace_id,
                        )
                    else:
                        # Commit point: gold becomes visible (has_gold /
                        # get_gold_map / list_documents) only once the marker
                        # lands, atomically, while we still hold the slug lock.
                        await self.store.mark_gold_complete(slug, {
                            "mode": "keyed",
                            "model": region_model,
                            "region_count": region_count,
                            "completed_at": self.clock.now(),
                        })
                        gold_completed = True
                        await self._publish(DocGoldExtracted(slug=slug, region_count=region_count), publish_workspace_id)

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
        """Embed every gold region of `slug` and write embeddings.json.

        Called automatically at the end of ``ingest_pdf`` when an embedder
        is wired, and exposed publicly so the CLI / agents can backfill
        embeddings for already-ingested gold layers without re-running the
        full pipeline.

        The embedded text per region is ``"{title}. {description}"`` —
        short enough to keep encode fast on CPU, dense enough that synonym
        queries hit. Region markdown is omitted on purpose (it's already
        captured in the page-level silver markdown which can be indexed
        separately if needed).

        Returns the number of regions embedded. Raises if no embedder
        is wired.
        """
        if self.embedder is None:
            raise RuntimeError("IngestService.embed_document called but no embedder wired")
        gold = await self.store.get_gold_map(slug)
        if gold is None:
            return 0
        items: list[tuple[int, str, str]] = []  # (page, region_id, text)
        for page_key, regions in (gold.get("pages") or {}).items():
            try:
                page = int(page_key)
            except (TypeError, ValueError):
                continue
            for r in regions:
                rid = r.get("id")
                if not rid:
                    continue
                title = (r.get("title") or "").strip()
                description = (r.get("description") or "").strip()
                if not title and not description:
                    continue
                text = f"{title}. {description}".strip(". ").strip()
                items.append((page, rid, text))
        if not items:
            return 0
        vectors = await self.embedder.embed([t for _, _, t in items])
        dim = len(vectors[0]) if vectors else 0
        payload: dict[str, Any] = {
            "embed_model": self.embed_model_id or "unknown",
            "dim": dim,
            "embedded_at": self.clock.now(),
            "vectors": [
                {"page": p, "region_id": rid, "text": text, "vector": vec}
                for (p, rid, text), vec in zip(items, vectors, strict=True)
            ],
        }
        await self.store.write_embeddings(slug, payload)
        await self._publish(
            IngestProgress(slug=slug, stage="embed", current=len(items), total=len(items)),
            publish_workspace_id,
        )
        return len(items)

    async def search(self, query: str, *, k: int = 10) -> dict[str, Any]:
        """Semantic search across every doc that has embeddings.json.

        Embeds the query with the same model used at ingest (carried on
        the embedder instance), pulls all embeddings.json on demand, and
        delegates to the pure-core ``search`` function for cosine top-k.

        Returns a small envelope so consumers can verify the query model
        before consuming hits. Documents embedded with another model are
        reported in ``skipped`` instead of being dropped silently:

            { "query": str, "embed_model": str, "k": int,
              "hits": [{"slug","page","region_id","text","score"}],
              "skipped": [{"slug","stored_model","query_model","reason"}] }
        """
        if self.embedder is None:
            raise RuntimeError("IngestService.search called but no embedder wired")
        # bge-style models don't need a prefix; e5-style ones do. We leave
        # this to the embedder impl to handle (LocalSentenceTransformer
        # currently passes through).
        query_model = self.embed_model_id or "unknown"
        vecs = await self.embedder.embed([query])
        if not vecs:
            return {
                "query": query,
                "embed_model": query_model,
                "k": k,
                "hits": [],
                "doc_count": 0,
                "skipped": [],
            }
        qv = vecs[0]
        # Pull every doc's embeddings file. For the POC this is fine; we
        # can cache in memory once the doc count grows.
        manifest = await self.store.list_embeddings()
        compatible = [m for m in manifest if m.get("embed_model") == query_model]
        skipped = [
            {
                "slug": m.get("slug", ""),
                "stored_model": m.get("embed_model") or "unknown",
                "query_model": query_model,
                "reason": "embed_model_mismatch",
            }
            for m in manifest
            if m.get("embed_model") != query_model
        ]
        docs: list[tuple[str, dict]] = []
        for m in compatible:
            payload = await self.store.get_embeddings(m["slug"])
            if payload is not None:
                docs.append((m["slug"], payload))
        hits = _search_topk(query_vector=qv, docs=docs, k=k)
        return {
            "query": query,
            "embed_model": query_model,
            "k": k,
            "hits": hits,
            "doc_count": len(docs),
            "skipped": skipped,
        }

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
