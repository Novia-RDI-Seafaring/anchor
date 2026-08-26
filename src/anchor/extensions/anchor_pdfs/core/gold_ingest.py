"""Locked, retryable gold-region extraction for the PDF ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from anchor.core.clock import Clock
from anchor.extensions.anchor_pdfs.core.events import DocGoldExtracted, IngestProgress
from anchor.extensions.anchor_pdfs.core.ingest.validation import validate_regions
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.region_extractor import RegionExtractor
from anchor.extensions.anchor_pdfs.core.silver import (
    region_content_from_items,
    snap_to_docling_items,
    table_bbox_from_items,
    table_cells_from_items,
)

GOLD_EMPTY_MAX_ATTEMPTS = 2
INGEST_LOCK_WAIT_SECONDS = 30 * 60


class Publish(Protocol):
    async def __call__(self, event: Any, workspace_id: str | None = None) -> None:
        pass


class RecordActivity(Protocol):
    async def __call__(
        self,
        stage: str,
        *,
        current: int = 0,
        total: int = 0,
        status: str = "running",
        error: str | None = None,
    ) -> None:
        pass


class FinishStage(Protocol):
    def __call__(self, stage: str, started_at: float, **fields: Any) -> None:
        pass


@dataclass(frozen=True)
class GoldIngestResult:
    region_count: int
    invalid_region_count: int
    region_errors: list[dict[str, Any]]
    completed: bool
    empty: bool
    attempts: int


class GoldIngest:
    """Extract, validate, and atomically commit one document's gold regions."""

    def __init__(
        self,
        store: DocStore,
        extractor: RegionExtractor,
        clock: Clock,
        publish: Publish,
    ) -> None:
        self.store = store
        self.extractor = extractor
        self.clock = clock
        self.publish = publish

    async def run(
        self,
        *,
        slug: str,
        docling: dict[str, Any],
        page_pngs: dict[int, bytes],
        items_by_page: dict[int, list[dict[str, Any]]],
        page_count: int,
        model: str | None,
        workspace_id: str,
        record_activity: RecordActivity,
        finish_stage: FinishStage,
    ) -> GoldIngestResult:
        attempts = 0
        region_count = 0
        invalid_count = 0
        region_errors: list[dict[str, Any]] = []

        async with self.store.ingest_lock(
            slug,
            wait=True,
            timeout=INGEST_LOCK_WAIT_SECONDS,
        ):
            while True:
                attempts += 1
                region_count = 0
                invalid_count = 0
                region_errors = []
                stage_started_at = self.clock.now()
                page_timings: list[dict[str, Any]] = []
                await self.store.clear_gold_complete(slug)

                for page, png in page_pngs.items():
                    page_started_at = self.clock.now()
                    raw_regions = await self.extractor.extract_page(
                        page_image=png,
                        page_no=page,
                        docling_items=items_by_page.get(page, []),
                        model=model,
                    )
                    snapped = self._snap_regions(docling, page, raw_regions)
                    valid, page_errors = validate_regions(snapped)
                    if page_errors:
                        invalid_count += len(snapped) - len(valid)
                        region_errors.extend(
                            {**error, "page": page}
                            for error in page_errors
                        )
                    await self.store.write_gold_region_file(slug, page, valid)
                    region_count += len(valid)
                    page_finished_at = self.clock.now()
                    page_timings.append({
                        "page": page,
                        "region_count": len(valid),
                        "invalid_region_count": len(snapped) - len(valid),
                        "started_at": page_started_at,
                        "finished_at": page_finished_at,
                        "duration_seconds": round(
                            max(0.0, page_finished_at - page_started_at),
                            3,
                        ),
                    })
                    await self.publish(
                        IngestProgress(
                            slug=slug,
                            stage="gold_regions",
                            current=page,
                            total=page_count,
                        ),
                        workspace_id,
                    )
                    await record_activity(
                        "gold_regions",
                        current=page,
                        total=page_count,
                    )

                finish_stage(
                    "gold_regions",
                    stage_started_at,
                    attempt=attempts,
                    page_count=len(page_timings),
                    region_count=region_count,
                    invalid_region_count=invalid_count,
                    model=model,
                    pages=page_timings,
                )
                if region_count > 0 or attempts >= GOLD_EMPTY_MAX_ATTEMPTS:
                    break
                await self.publish(
                    IngestProgress(
                        slug=slug,
                        stage="gold_regions_retry",
                        current=attempts,
                        total=GOLD_EMPTY_MAX_ATTEMPTS,
                    ),
                    workspace_id,
                )

            empty = region_count == 0
            if empty:
                await self.publish(
                    DocGoldExtracted(slug=slug, region_count=0),
                    workspace_id,
                )
            else:
                await self.store.mark_gold_complete(slug, {
                    "mode": "keyed",
                    "model": model,
                    "region_count": region_count,
                    "completed_at": self.clock.now(),
                })
                await self.publish(
                    DocGoldExtracted(slug=slug, region_count=region_count),
                    workspace_id,
                )

        return GoldIngestResult(
            region_count=region_count,
            invalid_region_count=invalid_count,
            region_errors=region_errors,
            completed=not empty,
            empty=empty,
            attempts=attempts,
        )

    @staticmethod
    def _snap_regions(
        docling: dict[str, Any],
        page: int,
        raw_regions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items = docling.get("items", [])
        snapped: list[dict[str, Any]] = []
        for region in raw_regions:
            if not isinstance(region, dict):
                snapped.append(region)
                continue
            bbox_value = region.get("bbox") or region.get("approximate_bbox")
            bbox = list(bbox_value) if isinstance(bbox_value, list) else []
            if len(bbox) == 4:
                snap_bbox, item_indexes = snap_to_docling_items(docling, page, bbox)
                if snap_bbox:
                    region = {**region, "bbox": snap_bbox}
                    content = region_content_from_items(items, item_indexes)
                    if content:
                        region = {**region, "content": content}
                    cells = table_cells_from_items(
                        items,
                        item_indexes,
                        region_bbox=bbox,
                    )
                    if cells and region.get("kind") in {"table", "spec_block"}:
                        region = {**region, "cells": cells}
                    table_bbox = table_bbox_from_items(
                        items,
                        item_indexes,
                        region_bbox=bbox,
                    )
                    if table_bbox and region.get("kind") == "table":
                        region = {**region, "bbox": table_bbox}
                elif "bbox" not in region:
                    region = {**region, "bbox": bbox}
            snapped.append(region)
        return snapped
