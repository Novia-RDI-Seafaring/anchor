"""Locked, retryable gold-region extraction for the PDF ingest pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from anchor.core.clock import Clock
from anchor.extensions.anchor_pdfs.core.events import DocGoldExtracted, IngestProgress
from anchor.extensions.anchor_pdfs.core.ingest.coverage import synthesize_coverage_regions
from anchor.extensions.anchor_pdfs.core.ingest.geometry import (
    BLOCK_KINDS,
    PICTURE_KINDS,
    adopt_table,
    disown_shared_members,
    headed_blocks_in,
    in_page_points,
    keep_block_items,
    keep_in_table,
    keep_picture_items,
    merge_into_pictures,
    merged_region,
    mostly_inside,
    needs_adoption,
    outside_tables,
    page_size_of,
    picture_frames,
    settle_shared_tables,
)
from anchor.extensions.anchor_pdfs.core.ingest.region_resolution import source_region_metadata
from anchor.extensions.anchor_pdfs.core.ingest.validation import (
    MAX_LIST_FIELD_ITEMS,
    MAX_LIST_ITEM_LEN,
    require_unique_region_ids,
    validate_regions,
)
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.region_extractor import RegionExtractor
from anchor.extensions.anchor_pdfs.core.silver import (
    build_page_candidates,
    region_content_from_items,
    snap_to_docling_items,
    table_bbox_from_items,
    table_data_from_items,
    union_bbox,
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
    #: Chunks synthesized by the coverage invariant (#242); included in
    #: ``region_count``. The extractor's own output is
    #: ``region_count - coverage_fallback_count``.
    coverage_fallback_count: int = 0


class GoldIngest:
    """Extract, validate, and atomically commit one document's gold regions."""

    def __init__(
        self,
        store: DocStore,
        extractor: RegionExtractor | None,
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
        dpi: int | None = None,
    ) -> GoldIngestResult:
        if self.extractor is None:
            raise ValueError("Keyed gold ingestion requires a region extractor")
        attempts = 0
        region_count = 0
        invalid_count = 0
        region_errors: list[dict[str, Any]] = []

        # The extractor sees the page's candidates (ids, labels, boxes in
        # points, text) so it can name a region's items instead of guessing a
        # box; the coverage pass below reads the same candidates.
        page_candidates = build_page_candidates(docling)

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
                pages_valid: dict[int, list[dict[str, Any]]] = {}

                for page, png in page_pngs.items():
                    page_started_at = self.clock.now()
                    raw_regions = await self.extractor.extract_page(
                        page_image=png,
                        page_no=page,
                        docling_items=page_candidates.get(page) or items_by_page.get(page, []),
                        model=model,
                        page_size=page_size_of(docling, page),
                        dpi=dpi,
                    )
                    snapped = self._snap_regions(docling, page, raw_regions, dpi=dpi)
                    require_unique_region_ids(snapped, page=page)
                    valid, page_errors = validate_regions(snapped)
                    if page_errors:
                        invalid_count += len(snapped) - len(valid)
                        region_errors.extend(
                            {**error, "page": page}
                            for error in page_errors
                        )
                    pages_valid[page] = valid
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

            # Empty/retry is judged on the extractor's own output; the coverage
            # pass below must not mask a model that returned nothing.
            empty = region_count == 0
            fallback_count = 0
            if empty:
                await self.publish(
                    DocGoldExtracted(slug=slug, region_count=0),
                    workspace_id,
                )
            else:
                # Coverage invariant (#242): every meaningful silver item lands
                # in at least one chunk. Additive post-pass over the final
                # authored gold, validated before any page is written.
                items_by_page_full = _items_by_page(docling)
                for page, valid in pages_valid.items():
                    extra = synthesize_coverage_regions(
                        page,
                        page_candidates.get(page, []),
                        valid,
                        full_items=items_by_page_full.get(page),
                    )
                    if extra:
                        fallback_count += len(extra)
                    pages_valid[page] = valid + extra
                    require_unique_region_ids(pages_valid[page], page=page)
                # Validate every page before exposing any page's gold.
                for page, valid in pages_valid.items():
                    stored = [source_region_metadata(r) for r in valid] if await self.store.get_page_items(slug, page) is not None else valid
                    await self.store.write_gold_region_file(slug, page, stored)
                region_count += fallback_count
                await self.store.mark_gold_complete(slug, {
                    "mode": "keyed",
                    "model": model,
                    "region_count": region_count,
                    "coverage_fallback_count": fallback_count,
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
            coverage_fallback_count=fallback_count,
        )

    async def run_text(
        self,
        *,
        slug: str,
        docling: dict[str, Any],
        workspace_id: str,
        record_activity: RecordActivity,
        finish_stage: FinishStage,
    ) -> GoldIngestResult:
        """Build grounded gold from silver without a model-authored pass."""
        started_at = self.clock.now()
        candidates = build_page_candidates(docling)
        full_items = _items_by_page(docling)
        pages: dict[int, list[dict[str, Any]]] = {}
        async with self.store.ingest_lock(
            slug, wait=True, timeout=INGEST_LOCK_WAIT_SECONDS,
        ):
            await self.store.clear_gold_complete(slug)
            for current, (page, items) in enumerate(candidates.items(), 1):
                regions = synthesize_coverage_regions(
                    page, items, [], full_items=full_items.get(page),
                )
                require_unique_region_ids(regions, page=page)
                valid, errors = validate_regions(regions)
                if errors:
                    raise ValueError(f"Invalid text-profile regions on page {page}: {errors}")
                pages[page] = valid
                await self.publish(IngestProgress(
                    slug=slug, stage="gold_regions", current=current, total=len(candidates),
                ), workspace_id)
                await record_activity("gold_regions", current=current, total=len(candidates))
            count = sum(len(regions) for regions in pages.values())
            if count:
                for page, regions in pages.items():
                    stored = [source_region_metadata(r) for r in regions] if await self.store.get_page_items(slug, page) is not None else regions
                    await self.store.write_gold_region_file(slug, page, stored)
                await self.store.mark_gold_complete(slug, {
                    "mode": "text", "model": None, "region_count": count,
                    "coverage_fallback_count": count, "completed_at": self.clock.now(),
                })
            await self.publish(DocGoldExtracted(slug=slug, region_count=count), workspace_id)
        finish_stage(
            "gold_regions", started_at, profile="text", model=None,
            page_count=len(pages), region_count=count, attempt=1,
        )
        return GoldIngestResult(
            region_count=count, invalid_region_count=0, region_errors=[],
            completed=count > 0, empty=count == 0, attempts=1,
            coverage_fallback_count=count,
        )

    @staticmethod
    def _snap_regions(
        docling: dict[str, Any],
        page: int,
        raw_regions: list[dict[str, Any]],
        *,
        dpi: int | None = None,
    ) -> list[dict[str, Any]]:
        """Ground the extractor's boxes in Docling items.

        The extractor is a model looking at a raster, so its boxes are taken
        with care: pixels are scaled to points when the page size and ``dpi``
        are known; a picture region is its picture and what is inside it; a
        table or spec block is one table and its heading. There is no repair
        round on this path, so the corrections are made here rather than
        asked for.
        """
        items = docling.get("items", [])
        page_size = page_size_of(docling, page)
        # Global item index -> position within this page (the `p{page}-i{idx}`
        # candidate id scheme), so snapped regions can record exactly which
        # silver items they cover — the same provenance the harness path
        # writes, and what the coverage invariant (#242) reads.
        page_position = {
            idx: pos
            for pos, idx in enumerate(
                i for i, it in enumerate(items)
                if isinstance(it, dict) and it.get("page") == page
            )
        }
        by_candidate = {f"p{page}-i{pos}": idx for idx, pos in page_position.items()}
        snapped: list[dict[str, Any]] = []
        for region in raw_regions:
            if not isinstance(region, dict):
                snapped.append(region)
                continue
            region = _unnest_geometry(_tidy_string_lists(region))

            # Named items first: the geometry the harness path uses, and the
            # one that cannot land in the wrong unit.
            named = region.get("member_item_ids")
            if isinstance(named, list) and named:
                item_indexes = [
                    by_candidate[member] for member in named
                    if isinstance(member, str) and member in by_candidate
                ]
                frame = union_bbox([list(items[i].get("bbox") or []) for i in item_indexes])
                if frame:
                    item_indexes = _block_item_indexes(items, item_indexes, region.get("kind"), frame)
                    snapped.append(_ground(region, items, item_indexes, page, page_position, frame))
                    continue
                region = {k: v for k, v in region.items() if k != "member_item_ids"}

            bbox_value = region.get("bbox") or region.get("approximate_bbox")
            bbox = list(bbox_value) if isinstance(bbox_value, list) else []
            if len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
                bbox = [float(v) for v in bbox]
                if page_size:
                    bbox, note = in_page_points(bbox, page_size, dpi)
                    if note:
                        region = {**region, "geometry_note": note}
                snap_bbox, item_indexes = snap_to_docling_items(docling, page, bbox)
                if snap_bbox:
                    item_indexes = _block_item_indexes(items, item_indexes, region.get("kind"), bbox)
                    region = _ground(region, items, item_indexes, page, page_position, bbox)
                elif region.get("bbox") != bbox:
                    region = {**region, "bbox": bbox}
            snapped.append(region)

        # A drawing's labels and the key's letters look alike; the key owns
        # its letters, so a picture region named by both gives them up.
        regions = [r if isinstance(r, dict) else {} for r in snapped]
        for pos, kept in disown_shared_members(regions).items():
            indexes = [by_candidate[m] for m in kept if m in by_candidate]
            if not indexes:
                continue
            frame = union_bbox([list(items[i].get("bbox") or []) for i in indexes])
            region = {**snapped[pos], "member_item_ids": kept}
            if frame:
                region["bbox"] = frame
            region["content"] = region_content_from_items(items, indexes)
            snapped[pos] = region
            regions[pos] = region

        # One table, one block: a table two blocks name goes to the block
        # whose heading is nearest above it.
        regions = [r if isinstance(r, dict) else {} for r in snapped]
        lookup = lambda mid: items[by_candidate[mid]] if mid in by_candidate else None  # noqa: E731
        tables = {mid: items[i] for mid, i in by_candidate.items() if items[i].get("label") == "table"}
        headings = {mid: items[i] for mid, i in by_candidate.items() if items[i].get("label") == "section_header"}
        for pos, kept in settle_shared_tables(regions, lookup, tables, headings).items():
            indexes = [by_candidate[m] for m in kept if m in by_candidate]
            frame = union_bbox([list(items[i].get("bbox") or []) for i in indexes])
            region = {**snapped[pos], "member_item_ids": kept}
            if frame:
                region["bbox"] = frame
            region["content"] = region_content_from_items(items, indexes)
            for field in ("cells", "table_topology"):
                region.pop(field, None)
            snapped[pos] = region

        # One drawing in the PDF is one region: picture regions take their
        # Docling picture's frame, and views of one drawing merge.
        pictures = [
            box for it in items
            if isinstance(it, dict) and it.get("page") == page and it.get("label") == "picture"
            and (box := _item_bbox(it))
        ]
        frames, absorbed = merge_into_pictures(regions, pictures)
        for pos, frame in frames.items():
            region = merged_region(snapped[pos], [snapped[o] for o in absorbed.get(pos, [])])
            region["bbox"] = frame
            indexes = [by_candidate[m] for m in region.get("member_item_ids") or [] if m in by_candidate]
            region["content"] = region_content_from_items(items, indexes)
            snapped[pos] = region
        gone = {o for others in absorbed.values() for o in others}
        snapped = [r for pos, r in enumerate(snapped) if pos not in gone]
        regions = [r if isinstance(r, dict) else {} for r in snapped]

        # A key the picture's frame takes in is a region of its own, whether
        # or not the extractor drew one: a heading in the frame with text
        # under it in its column. The cut below then gives it its room.
        page_items = [(mid, items[idx]) for mid, idx in by_candidate.items() if isinstance(items[idx], dict)]
        claimed = {
            m for r in regions if r.get("kind") not in PICTURE_KINDS
            for m in r.get("member_item_ids") or []
        }
        next_index = 1 + max(
            (int(m.group(1)) for r in regions if (m := re.search(r"(\d+)$", str(r.get("id") or "")))),
            default=0,
        )
        for region in list(regions):
            if region.get("kind") not in PICTURE_KINDS or not _item_bbox(region):
                continue
            free = [(mid, it) for mid, it in page_items if mid not in claimed]
            for block in headed_blocks_in(_item_bbox(region), free):
                indexes = [by_candidate[m] for m in block["members"]]
                key = {
                    "id": f"p{page}-r{next_index}",
                    "kind": "spec_block",
                    "title": block["title"],
                    "description": "",
                    "tags": [],
                    "member_item_ids": block["members"],
                    "bbox": block["bbox"],
                    "content": region_content_from_items(items, indexes),
                    "split_from": region.get("id"),
                }
                next_index += 1
                claimed.update(block["members"])
                snapped.append(key)
        regions = [r if isinstance(r, dict) else {} for r in snapped]

        # A picture that spans a drawing and the key beside it gives the key
        # its own room: the frame is cut at the sibling region's edge and the
        # members outside the cut go with it.
        own_boxes = {
            pos: [
                box for member in region.get("member_item_ids") or []
                if member in by_candidate
                and items[by_candidate[member]].get("label") != "picture"
                and (box := _item_bbox(items[by_candidate[member]]))
            ]
            for pos, region in enumerate(regions)
            if region.get("kind") in PICTURE_KINDS
        }
        for pos, frame in picture_frames(regions, own_boxes).items():
            region = snapped[pos]
            kept = [
                member for member in region.get("member_item_ids") or []
                if member in by_candidate and (
                    items[by_candidate[member]].get("label") == "picture"
                    or mostly_inside(_item_bbox(items[by_candidate[member]]), frame)
                )
            ]
            region = {**region, "bbox": frame, "member_item_ids": kept}
            content = region_content_from_items(items, [by_candidate[m] for m in kept])
            region["content"] = content
            snapped[pos] = region
        return snapped


def _ground(
    region: dict[str, Any],
    items: list[Any],
    item_indexes: list[int],
    page: int,
    page_position: dict[int, int],
    region_bbox: list[float],
) -> dict[str, Any]:
    """The region as its items make it: box, member ids, content, table data."""
    bbox = union_bbox([list(items[i].get("bbox") or []) for i in item_indexes])
    member_ids = [f"p{page}-i{page_position[i]}" for i in item_indexes if i in page_position]
    grounded = {**region, "bbox": bbox, "member_item_ids": member_ids}
    content = region_content_from_items(items, item_indexes)
    if content:
        grounded["content"] = content
    table_data = table_data_from_items(items, item_indexes, region_bbox=region_bbox)
    if table_data and grounded.get("kind") in BLOCK_KINDS:
        grounded.update(table_data)
    table_bbox = table_bbox_from_items(items, item_indexes, region_bbox=region_bbox)
    if table_bbox and grounded.get("kind") == "table":
        grounded["bbox"] = table_bbox
    return grounded


def _item_bbox(item: Any) -> list[float] | None:
    raw = item.get("bbox") if isinstance(item, dict) else None
    if isinstance(raw, list) and len(raw) == 4:
        try:
            return [float(v) for v in raw]
        except (TypeError, ValueError):
            return None
    return None


def _block_item_indexes(
    items: list[Any],
    indexes: list[int],
    kind: Any,
    region_bbox: list[float],
) -> list[int]:
    """The absorbed items a region of ``kind`` keeps (see ``ingest.geometry``)."""
    absorbed = [items[i] for i in indexes]
    if kind in PICTURE_KINDS:
        kept = keep_picture_items(absorbed)
    elif kind in BLOCK_KINDS:
        indexes = _with_adopted_table(items, indexes)
        absorbed = [items[i] for i in indexes]
        kept = keep_block_items(absorbed, region_bbox)
    else:
        return indexes
    return [indexes[pos] for pos in kept]


def _with_adopted_table(items: list[Any], indexes: list[int]) -> list[int]:
    """A block named without its table takes the page table it means."""
    named = [items[i] for i in indexes]
    pages = {item.get("page") for item in named}
    page_tables = [
        i for i, item in enumerate(items)
        if isinstance(item, dict) and item.get("label") == "table" and item.get("page") in pages
    ]
    tables = [items[i] for i in page_tables]
    if not needs_adoption(named, tables):
        return indexes
    chosen = adopt_table(named, tables)
    if chosen is None:
        if any(item.get("label") == "table" for item in named):
            return indexes
        return [indexes[pos] for pos in outside_tables(named, tables)] or indexes
    table_index = page_tables[chosen]
    table_box = _item_bbox(items[table_index]) or []
    kept = [indexes[pos] for pos in keep_in_table(named, table_box)]
    return sorted({table_index, *kept})


def _unnest_geometry(region: dict[str, Any]) -> dict[str, Any]:
    """``{"geometry": {"member_item_ids": [...]}}`` as top-level fields.

    Asked for "geometry", a model may answer with an object of that name.
    Its contents are the fields the grounding reads, so lift them out; the
    stored region keeps ``geometry`` for the string the harness path writes.
    """
    nested = region.get("geometry")
    if not isinstance(nested, dict):
        return region
    lifted = {k: v for k, v in region.items() if k != "geometry"}
    for field in ("member_item_ids", "bbox", "approximate_bbox"):
        if field in nested and field not in lifted:
            lifted[field] = nested[field]
    return lifted


def _tidy_string_lists(region: dict[str, Any]) -> dict[str, Any]:
    """``tags`` and ``entities`` as the schema wants them: strings, bounded.

    The extractor sometimes sends a number or an object where a string was
    asked for. On this path a rejected field would drop the whole region
    with no way to ask again, so scalars become strings and objects go.
    """
    tidy = dict(region)
    for field in ("tags", "entities"):
        value = tidy.get(field)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            continue
        tidy[field] = [
            str(item)[:MAX_LIST_ITEM_LEN]
            for item in value
            if item is not None and not isinstance(item, (dict, list))
        ][:MAX_LIST_FIELD_ITEMS]
    return tidy


def _items_by_page(docling: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    """Docling items grouped per page in docling order (aligned with
    ``build_page_candidates`` positions)."""
    out: dict[int, list[dict[str, Any]]] = {}
    for it in docling.get("items") or []:
        if not isinstance(it, dict):
            continue
        page = it.get("page")
        if isinstance(page, (int, float)):
            out.setdefault(int(page), []).append(it)
    return out
