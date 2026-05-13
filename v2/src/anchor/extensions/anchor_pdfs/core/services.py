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
from anchor.extensions.anchor_pdfs.core.events import (
    DocBronzed,
    DocGoldExtracted,
    DocIngestFailed,
    DocIngested,
    DocPolished,
    DocSilvered,
    IngestProgress,
)
from anchor.core.ids import new_event_id, slugify
from anchor.extensions.anchor_pdfs.core.silver import build_index, build_pages_meta, render_pages_md, snap_to_docling_items
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_pdfs.core.ports.md_polisher import PageMdPolisher
from anchor.extensions.anchor_pdfs.core.ports.pdf_extractor import PdfExtractor
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer
from anchor.extensions.anchor_pdfs.core.ports.region_extractor import RegionExtractor
from anchor.extensions.anchor_pdfs.core.ports.synopsis_renderer import (
    MarkdownSynopsisRenderer,
    PdfSynopsisRenderer,
)
from anchor.extensions.anchor_pdfs.core.synopsis import SynopsisData, compose_synopsis


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
        clock: Clock | None = None,
        global_workspace_id: str = "_global",
    ) -> None:
        self.store = store
        self.bus = bus
        self.extractor = extractor
        self.renderer = renderer
        self.polisher = polisher
        self.region_extractor = region_extractor
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
        polish_model: str = "gpt-5.4",
        region_model: str = "gpt-5.4",
        dpi: int = 150,
    ) -> dict[str, Any]:
        slug = slug or slugify(Path(filename).stem)
        publish_workspace_id = workspace_id or self._gid
        try:
            bronze_path = await self.store.stash_bronze(pdf_bytes, filename)
            await self._publish(DocBronzed(slug=slug, bronze_path=str(bronze_path)), publish_workspace_id)

            await self._publish(IngestProgress(slug=slug, stage="silver_extract", current=0, total=1), publish_workspace_id)
            docling = await self.extractor.extract(bronze_path)
            page_count = max(
                (int(it["page"]) for it in docling.get("items", []) if isinstance(it.get("page"), (int, float))),
                default=0,
            )
            index = build_index(docling, filename=filename)
            pages_md = render_pages_md(docling)
            pages_meta = build_pages_meta(docling)
            await self.store.write_silver_artifact(slug, "index.json", json.dumps(index))
            await self.store.write_silver_artifact(slug, "pages.meta.json", json.dumps(pages_meta))
            for page, md in pages_md.items():
                await self.store.write_silver_artifact(slug, f"pages/{page}.raw.md", md)

            page_pngs: dict[int, bytes] = {}
            items_by_page: dict[int, list[dict[str, Any]]] = {}
            if page_count:
                page_pngs = await self.renderer.render_pages(bronze_path, dpi=dpi)
                for page, png in page_pngs.items():
                    await self.store.write_silver_artifact(slug, f"pages/{page}.png", png)
                for it in docling.get("items", []):
                    if isinstance(it.get("page"), (int, float)):
                        items_by_page.setdefault(int(it["page"]), []).append(it)
            await self._publish(DocSilvered(slug=slug, page_count=page_count), publish_workspace_id)

            polished_pages: list[int] = []
            if polish and self.polisher and page_count:
                for page, png in page_pngs.items():
                    polished = await self.polisher.polish_page(
                        page_image=png,
                        page_no=page,
                        deterministic_md=pages_md.get(page, ""),
                        docling_items=items_by_page.get(page, []),
                        model=polish_model,
                    )
                    await self.store.write_silver_artifact(slug, f"pages/{page}.md", polished)
                    polished_pages.append(page)
                    await self._publish(IngestProgress(
                        slug=slug, stage="silver_polish", current=page, total=page_count,
                    ), publish_workspace_id)
                await self._publish(DocPolished(slug=slug, polished_pages=polished_pages), publish_workspace_id)

            region_count = 0
            if regions and self.region_extractor and page_count:
                for page, png in page_pngs.items():
                    raw_regions = await self.region_extractor.extract_page(
                        page_image=png,
                        page_no=page,
                        docling_items=items_by_page.get(page, []),
                        model=region_model,
                    )
                    snapped: list[dict[str, Any]] = []
                    for r in raw_regions:
                        bbox_any = r.get("bbox")
                        bbox_list: list[float] = list(bbox_any) if isinstance(bbox_any, list) else []
                        if len(bbox_list) == 4:
                            snap_bbox, _ = snap_to_docling_items(docling, page, bbox_list)
                            if snap_bbox:
                                r = {**r, "bbox": snap_bbox}
                        snapped.append(r)
                    await self.store.write_gold_region_file(slug, page, snapped)
                    region_count += len(snapped)
                    await self._publish(IngestProgress(
                        slug=slug, stage="gold_regions", current=page, total=page_count,
                    ), publish_workspace_id)
                await self._publish(DocGoldExtracted(slug=slug, region_count=region_count), publish_workspace_id)

            summary = {
                "slug": slug,
                "filename": filename,
                "page_count": page_count,
                "polished_pages": polished_pages,
                "region_count": region_count,
            }
            await self._publish(DocIngested(slug=slug, summary=summary), publish_workspace_id)
            return summary

        except Exception as exc:  # surface the failure on the bus before re-raising
            await self._publish(DocIngestFailed(slug=slug, stage="unknown", error=str(exc)), publish_workspace_id)
            raise

    async def _publish(self, evt: Any, workspace_id: str | None = None) -> None:
        await self.bus.publish(DomainEvent(
            id=new_event_id(),
            ts=self.clock.now(),
            workspace_id=workspace_id or self._gid,
            type=evt.type,
            payload=evt.model_dump(),
        ))
