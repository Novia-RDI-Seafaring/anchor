"""Gold coverage invariant (#242 P1, closes #231).

Every meaningful silver item must belong to at least one gold chunk, or it is
invisible to search. Gold membership used to be entirely at the model's /
agent's discretion, so a caption-less table or an unboxed paragraph could
silently fall out of gold. This module is the reconciliation pass that runs
after gold is assembled (keyed: after the extractor's final attempt; harness:
in ``ingest_finalize``) and synthesizes *additive* fallback chunks for
whatever the authored regions left uncovered. Authored gold is never altered.

Vocabulary: "meaningful" is defined against Anchor's normalized item labels
(``MEANINGFUL_LABELS``), not against any one layout detector. Docling emits
these labels today; another extractor (#279) maps its own labels onto them.

Granularity (hybrid, chosen for retrieval quality):
- a table is one chunk (self-contained; its cells embed via the #242
  embedding fallback in ``region_search_text``);
- contiguous uncovered text items are merged into one chunk, bounded by the
  nearest heading and a size cap, so embeddings see paragraph-to-section
  units rather than stray lines. Provenance stays exact: ``member_item_ids``
  lists every merged item and ``bbox`` is their union.

Headings (``title`` / ``section_header``) are not required to be covered on
their own (a bare heading carries no retrievable fact); they delimit runs and
supply the run's title, and join the run as a member when uncovered.
"""
from __future__ import annotations

import re
from typing import Any

from anchor.extensions.anchor_pdfs.core.silver import (
    region_content_from_items,
    table_cells_from_items,
    union_bbox,
)

#: Normalized item labels whose content must be reachable through gold.
MEANINGFUL_LABELS: frozenset[str] = frozenset({
    "text",
    "paragraph",
    "list_item",
    "table",
    "footnote",
    "caption",
    "formula",
    "code",
})

#: Labels that delimit text runs and provide titles; not required on their own.
HEADING_LABELS: frozenset[str] = frozenset({"title", "section_header"})

#: Soft cap on merged text per synthesized chunk (characters of item text).
DEFAULT_MAX_RUN_CHARS = 1500

_MAX_TITLE = 120
_REGION_ID_RE = re.compile(r"^r(\d+)$")


def covered_item_ids(regions: list[dict[str, Any]]) -> set[str]:
    """Candidate ids the authored regions already cover.

    Reads ``member_item_ids`` (harness members; keyed snapper after #242) and
    ``table_slice.candidate_id`` (cell-granular table selections, #270)."""
    covered: set[str] = set()
    for region in regions:
        if not isinstance(region, dict):
            continue
        members = region.get("member_item_ids")
        if isinstance(members, list):
            covered.update(m for m in members if isinstance(m, str))
        table_slice = region.get("table_slice")
        if isinstance(table_slice, dict):
            cid = table_slice.get("candidate_id")
            if isinstance(cid, str):
                covered.add(cid)
    return covered


def _next_region_index(regions: list[dict[str, Any]]) -> int:
    """Continue the per-page ``r{n}`` sequence after the highest authored id."""
    highest = 0
    for region in regions:
        if not isinstance(region, dict):
            continue
        match = _REGION_ID_RE.match(str(region.get("id") or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _title_from_text(text: str, fallback: str) -> str:
    first = " ".join((text or "").strip().split())
    if not first:
        return fallback
    # First sentence-ish, else a hard cut.
    cut = re.split(r"(?<=[.!?:])\s", first, maxsplit=1)[0]
    if len(cut) > _MAX_TITLE:
        cut = cut[: _MAX_TITLE - 1].rstrip() + "…"
    return cut


def _table_title(candidate: dict[str, Any], heading: str | None) -> str:
    if heading:
        return heading
    preview = candidate.get("cells_preview") or {}
    header_row = preview.get("header_row") if isinstance(preview, dict) else None
    if isinstance(header_row, list) and header_row:
        cells = [str(c).strip() for c in header_row if str(c).strip()]
        if cells:
            return _title_from_text(" · ".join(cells), "Table")
    return "Table"


def _make_region(
    *,
    index: int,
    page: int,
    kind: str,
    title: str,
    members: list[dict[str, Any]],
    content_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    bbox = union_bbox([list(m.get("bbox") or []) for m in members])
    if not bbox:
        return None
    region: dict[str, Any] = {
        "id": f"r{index}",
        "kind": kind,
        "title": title[:_MAX_TITLE] or kind,
        # Deliberately empty: the embedding fallback then renders content /
        # cells into the search text (#242 P1b).
        "description": "",
        "page": page,
        "bbox": bbox,
        "geometry": "members",
        "member_item_ids": [m["id"] for m in members],
        "tags": ["coverage"],
        "entities": [],
        "coverage_fallback": True,
    }
    content = region_content_from_items(content_items)
    if content:
        region["content"] = content
    if kind == "table":
        cells = table_cells_from_items(content_items)
        if cells:
            region["cells"] = cells
    return region


def synthesize_coverage_regions(
    page: int,
    candidates: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    *,
    full_items: list[dict[str, Any]] | None = None,
    max_run_chars: int = DEFAULT_MAX_RUN_CHARS,
) -> list[dict[str, Any]]:
    """Fallback gold regions for the page's uncovered meaningful candidates.

    ``candidates`` is the page's silver candidate list (``build_page_candidates``
    order, ids ``p{page}-i{idx}``). ``full_items`` optionally supplies the
    uncapped docling items aligned by position, so chunk content is not
    truncated to the candidate-text preview. Returns only the new regions;
    the caller appends them to the authored ones.
    """
    covered = covered_item_ids(regions)
    index = _next_region_index(regions)
    out: list[dict[str, Any]] = []

    def content_item(pos: int) -> dict[str, Any]:
        if full_items is not None and 0 <= pos < len(full_items):
            item = full_items[pos]
            if isinstance(item, dict):
                return item
        return candidates[pos]

    heading: str | None = None
    pending_heading: dict[str, Any] | None = None  # uncovered heading awaiting a run
    run: list[int] = []
    run_chars = 0

    def flush_run() -> None:
        nonlocal index, run, run_chars, pending_heading
        if not run:
            pending_heading = None
            return
        positions = list(run)
        if pending_heading is not None:
            positions.insert(0, pending_heading["_pos"])
        members = [candidates[p] for p in positions]
        content_items = [content_item(p) for p in positions]
        first_text = candidates[run[0]].get("text") or ""
        title = heading or _title_from_text(first_text, "Text")
        region = _make_region(
            index=index, page=page, kind="text", title=title,
            members=members, content_items=content_items,
        )
        if region is not None:
            out.append(region)
            index += 1
        run = []
        run_chars = 0
        pending_heading = None

    for pos, cand in enumerate(candidates):
        if not isinstance(cand, dict):
            continue
        label = str(cand.get("label") or "")
        cid = cand.get("id")
        text = str(cand.get("text") or "")

        if label in HEADING_LABELS:
            flush_run()
            heading = _title_from_text(text, "") or None
            pending_heading = {**cand, "_pos": pos} if cid not in covered else None
            continue

        if label not in MEANINGFUL_LABELS:
            continue
        if cid in covered:
            flush_run()
            continue

        if label == "table":
            flush_run()
            region = _make_region(
                index=index, page=page, kind="table",
                title=_table_title(cand, heading),
                members=[cand], content_items=[content_item(pos)],
            )
            if region is not None:
                out.append(region)
                index += 1
            continue

        # Text-like: merge into the current run, bounded by the size cap.
        if run and run_chars + len(text) > max_run_chars:
            flush_run()
        run.append(pos)
        run_chars += len(text)

    flush_run()
    return out


def coverage_stats(
    candidates: list[dict[str, Any]], regions: list[dict[str, Any]]
) -> dict[str, int]:
    """Meaningful-candidate coverage numbers for an ingest report."""
    covered = covered_item_ids(regions)
    meaningful = [
        c for c in candidates
        if isinstance(c, dict) and str(c.get("label") or "") in MEANINGFUL_LABELS
    ]
    covered_count = sum(1 for c in meaningful if c.get("id") in covered)
    return {
        "meaningful_items": len(meaningful),
        "covered_items": covered_count,
        "uncovered_items": len(meaningful) - covered_count,
    }
