"""Port-based orchestration for the bronze -> silver -> gold pipeline."""
from __future__ import annotations

import json
import re
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
    _parse_region_token,
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
    normalize_items,
    render_pages_md,
)
from anchor.extensions.anchor_pdfs.core.synopsis_service import (
    SynopsisService as _SynopsisService,
)

GOLD_EMPTY_MAX_ATTEMPTS = _GOLD_EMPTY_MAX_ATTEMPTS
INGEST_LOCK_WAIT_SECONDS = _INGEST_LOCK_WAIT_SECONDS
SynopsisService = _SynopsisService

#: Matches the trailing r-number of a gold region id: plain ``r4`` as well as
#: producer-prefixed forms like ``lkh:p4-r1``. Used to mint the next free id.
_REGION_ID_SUFFIX = re.compile(r"r(\d+)$")


class RegionNotRemovableError(ValueError):
    """Raised when a removal targets a region without ``derived_from``.

    Model-extracted gold is the ground truth of an ingest pass and is never
    deletable through the region API; only OIP-derived records may be removed.
    """


class AmbiguousRegionError(ValueError):
    """A bare region id matched regions on more than one page (#287).

    Region ids are only unique per page (``r1`` exists on page 1 *and*
    page 4), so silently picking the first match binds provenance to the
    wrong region. Carries the colliding ``region_id`` and the sorted
    candidate ``pages`` so adapters can render a structured error; the
    message tells the caller to qualify the page (``p<page>/<id>``).
    """

    def __init__(self, message: str, *, region_id: str, pages: list[int]) -> None:
        super().__init__(message)
        self.region_id = region_id
        self.pages = pages


def _next_region_id(page_regions: list[dict[str, Any]]) -> str:
    """Mint the next free ``r<n>`` id on a page (#304)."""
    highest = 0
    for region in page_regions:
        rid = region.get("id")
        if not isinstance(rid, str):
            continue
        match = _REGION_ID_SUFFIX.search(rid)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"r{highest + 1}"


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
            # Boundary normaliser (#281): every extractor's boxes leave here as
            # top-left PDF points, validated against the reported page sizes.
            docling = normalize_items(
                await self.extractor.extract(bronze_path, full_page_ocr=full_page_ocr)
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
            coverage_fallback_count = 0
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
                coverage_fallback_count = gold.coverage_fallback_count
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
                "coverage_fallback_count": coverage_fallback_count,
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
                "coverage_fallback_count": coverage_fallback_count,
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

    async def resolve_source_ref(
        self, slug: str, ref: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Resolve a source_ref to the most precise stored evidence bbox
        (cell > item > region > bbox); see core.source_ref_resolve."""
        from anchor.extensions.anchor_pdfs.core.source_ref_resolve import (
            resolve_source_ref,
        )

        return await resolve_source_ref(self.store, slug, ref)

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

        A region without an ``id`` gets the next free ``r<n>`` on its page
        minted here (#304) — a stored region must always be addressable
        (inspect_region, evidence-edge source_refs), so the consumer never
        persists an id-less record.

        ``parent_region_id`` accepts the same tokens ``inspect_region`` does:
        ``p4/r1`` (page 4, region r1), ``4/r1``, or a bare ``r1``. Region ids
        are only unique per page (#287), so a page-qualified token binds to
        that page's region, and a *bare* id that matches regions on multiple
        pages raises ``AmbiguousRegionError`` (listing the candidate pages)
        instead of silently picking the first.
        """
        page_hint, parent_id = _parse_region_token(parent_region_id)
        regions = await self.store.get_regions(slug)
        matches: list[tuple[int, dict[str, Any]]] = []
        for _page, regs in (regions.get("pages") or {}).items():
            for r in regs:
                if isinstance(r, dict) and r.get("id") == parent_id:
                    matches.append((int(_page), r))
        if page_hint is not None:
            matches = [(p, r) for p, r in matches if p == page_hint]
        if not matches:
            raise ValueError(
                f"derive_region: parent region {parent_region_id!r} not found in {slug!r}"
            )
        if len(matches) > 1:
            pages = sorted({p for p, _r in matches})
            raise AmbiguousRegionError(
                f"derive_region: parent region id {parent_id!r} exists on "
                f"pages {pages} of {slug!r}; qualify the page, e.g. "
                f"'p{pages[0]}/{parent_id}'",
                region_id=parent_id,
                pages=pages,
            )
        parent_page, parent = matches[0]

        derived = dict(region)
        derived["derived_from"] = parent_id
        # Inherit the parent's provenance unless the producer set its own.
        # Ordinary gold regions store no source_ref, so synthesize the
        # parent's — otherwise the docstring's promise (provenance points at
        # the same page and bbox) silently fails for the common case.
        if not derived.get("source_ref"):
            parent_ref = parent.get("source_ref")
            if not isinstance(parent_ref, dict) or not parent_ref:
                parent_ref = {
                    "slug": slug,
                    "page": parent_page,
                    "region_id": parent_id,
                    "bbox": parent.get("bbox") or parent.get("approx_bbox"),
                }
            derived["source_ref"] = parent_ref

        if not derived.get("id"):
            # Mint the next free `r<n>` on the page the region will land on
            # (#304): scan that page's stored ids for the highest r-number.
            # Explicit producer ids pass through untouched.
            sref = derived.get("source_ref")
            dest_page = (
                sref["page"]
                if isinstance(sref, dict) and isinstance(sref.get("page"), int)
                else derived.get("page")
                if isinstance(derived.get("page"), int)
                else parent_page
            )
            page_regions: list[dict[str, Any]] = []
            for _page, regs in (regions.get("pages") or {}).items():
                if int(_page) == dest_page:
                    page_regions = [r for r in regs if isinstance(r, dict)]
                    break
            derived["id"] = _next_region_id(page_regions)

        path = await self.store.add_derived_region(slug, derived)
        return {
            "slug": slug,
            "region_id": derived.get("id"),
            "kind": derived.get("kind"),
            "derived_from": parent_id,
            "path": str(path),
        }

    async def remove_region(self, slug: str, region_id: str) -> dict[str, Any]:
        """Remove one OIP-derived gold region (#304).

        The cleanup half of ``derive_region``: only regions carrying
        ``derived_from`` may be removed — model-extracted gold is the ground
        truth of an ingest pass and stays. The region id accepts the same
        tokens ``inspect_region`` does (``p4/r2``, ``4/r2``, or a bare
        ``r2``, first match across pages).

        Rewrites the region's page file without the record and drops its
        vector from ``embeddings.json`` when one exists, so search never
        returns a region that no longer resolves. Raises ``ValueError`` when
        the region does not exist and ``RegionNotRemovableError`` when it is
        not a derived region.
        """
        from anchor.extensions.anchor_pdfs.core.region_inspect import find_region

        found = await find_region(self.store, slug, region_id)
        if found is None:
            raise ValueError(
                f"remove_region: region {region_id!r} not found in {slug!r}"
            )
        page, region = found
        rid = region.get("id")
        if not region.get("derived_from"):
            raise RegionNotRemovableError(
                f"remove_region: region {rid!r} in {slug!r} is model-extracted "
                "gold (no derived_from) and cannot be removed; only regions "
                "created by derive_region are deletable"
            )
        regions = await self.store.get_regions(slug, page)
        page_regions: list[dict[str, Any]] = []
        for _page, regs in (regions.get("pages") or {}).items():
            if int(_page) == page:
                page_regions = [r for r in regs if isinstance(r, dict)]
                break
        kept = [r for r in page_regions if r.get("id") != rid]
        await self.store.write_gold_region_file(slug, page, kept)

        # Keep the embedding index consistent: drop the removed region's
        # vector so a search hit can never point at a record that is gone.
        embeddings_removed = 0
        payload = await self.store.get_embeddings(slug)
        if payload is not None:
            vectors = payload.get("vectors", [])
            kept_vectors = [
                v
                for v in vectors
                if not (
                    isinstance(v, dict)
                    and v.get("region_id") == rid
                    and v.get("page") == page
                )
            ]
            embeddings_removed = len(vectors) - len(kept_vectors)
            if embeddings_removed:
                payload["vectors"] = kept_vectors
                await self.store.write_embeddings(slug, payload)

        return {
            "slug": slug,
            "page": page,
            "region_id": rid,
            "removed": True,
            "derived_from": region.get("derived_from"),
            "embeddings_removed": embeddings_removed,
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
