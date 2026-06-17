"""Silver builders — pure functions over docling JSON dicts.

NOTE: the I/O-coupled helpers (`render_pages_png`, the `polish_pages_md`
driver, `PageMdPolisherClient` Protocol) live in `infra/pdf/` and
`core/ports/md_polisher.py` respectively. This module is dict-in / dict-out.
"""
from __future__ import annotations

from typing import Any

# Silver Docling section-header labels we promote into the outline.
_SECTION_LABELS = {"section_header", "title"}


def build_index(docling: dict[str, Any], *, filename: str = "", title: str = "") -> dict[str, Any]:
    """Build an index dict from a silver Docling JSON dict."""
    items = docling.get("items")
    if not isinstance(items, list):
        items = []

    pages = {int(it["page"]) for it in items if isinstance(it, dict) and isinstance(it.get("page"), (int, float))}
    page_count = max(pages) if pages else 0

    outline: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []

    last_header_by_page: dict[int, str] = {}
    resolved_title = title

    for it in items:
        if not isinstance(it, dict):
            continue
        label = it.get("label")
        page = it.get("page")
        bbox = it.get("bbox")
        text = (it.get("text") or "").strip()

        if not isinstance(page, (int, float)):
            continue
        page = int(page)

        if label in _SECTION_LABELS and text:
            level = 1 if label == "title" else _guess_level(text)
            outline.append({"level": level, "title": text, "page": page, "bbox": _clean_bbox(bbox)})
            last_header_by_page[page] = text
            if not resolved_title:
                resolved_title = text

        elif label == "table":
            caption = last_header_by_page.get(page, "")
            header_row, first_col, shape = _summarize_table_cells(it.get("cells"))
            tables.append({
                "id": f"t{len(tables) + 1}",
                "page": page,
                "bbox": _clean_bbox(bbox),
                "caption": caption,
                "shape": shape,
                "header_row": header_row,
                "first_column_values": first_col,
                "cells": _clean_table_cells(it.get("cells")),
            })

        elif label == "picture":
            caption = last_header_by_page.get(page, "")
            figures.append({"page": page, "bbox": _clean_bbox(bbox), "caption": caption})

    return {
        "document": {
            "filename": filename,
            "title": resolved_title,
            "page_count": page_count,
        },
        "outline": outline,
        "tables": tables,
        "figures": figures,
    }


def _clean_bbox(bbox: Any) -> list[float]:
    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
        return [float(v) for v in bbox]
    return []


def _guess_level(text: str) -> int:
    if text.isupper() and len(text) <= 40:
        return 1
    if len(text) <= 60:
        return 2
    return 3


def _summarize_table_cells(cells: Any) -> tuple[list[str], list[str], dict[str, int]]:
    if not isinstance(cells, list):
        return [], [], {"rows": 0, "cols": 0}

    rows = cols = 0
    row_0: dict[int, str] = {}
    col_0: dict[int, str] = {}

    for cell in cells:
        if not isinstance(cell, dict):
            continue
        r = cell.get("row")
        c = cell.get("col")
        text = (cell.get("text") or "").strip()
        if not isinstance(r, int) or not isinstance(c, int):
            continue
        rows = max(rows, r + 1)
        cols = max(cols, c + 1)
        if r == 0 and text and c not in row_0:
            row_0[c] = text
        if c == 0 and r > 0 and text and r not in col_0:
            col_0[r] = text

    header_row = [row_0[c] for c in sorted(row_0)]
    first_column_values = [col_0[r] for r in sorted(col_0)]
    return header_row, first_column_values, {"rows": rows, "cols": cols}


def _clean_table_cells(cells: Any) -> list[dict[str, Any]]:
    if not isinstance(cells, list):
        return []
    out: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        row = cell.get("row")
        col = cell.get("col")
        if not isinstance(row, int) or not isinstance(col, int):
            continue
        clean: dict[str, Any] = {
            "row": row,
            "col": col,
            "text": cell.get("text") if isinstance(cell.get("text"), str) else "",
        }
        bbox = _clean_bbox(cell.get("bbox"))
        if bbox:
            clean["bbox"] = bbox
        out.append(clean)
    return out


def table_cells_from_items(
    items: Any,
    indexes: list[int] | None = None,
    region_bbox: list[float] | None = None,
) -> list[dict[str, Any]]:
    table = table_item_from_items(items, indexes, region_bbox=region_bbox)
    if not table:
        return []
    return _clean_table_cells(table.get("cells"))


def table_bbox_from_items(
    items: Any,
    indexes: list[int] | None = None,
    region_bbox: list[float] | None = None,
) -> list[float]:
    table = table_item_from_items(items, indexes, region_bbox=region_bbox)
    if not table:
        return []
    return _clean_bbox(table.get("bbox"))


def table_item_from_items(
    items: Any,
    indexes: list[int] | None = None,
    *,
    region_bbox: list[float] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    selected = items
    if indexes is not None:
        selected = [items[i] for i in indexes if 0 <= i < len(items)]
    tables = [
        it for it in selected
        if isinstance(it, dict)
        and it.get("label") == "table"
        and _clean_table_cells(it.get("cells"))
    ]
    if not tables:
        return None
    if region_bbox:
        return max(
            tables,
            key=lambda it: (
                _bbox_overlap_area(_clean_bbox(it.get("bbox")), region_bbox),
                _bbox_area(_clean_bbox(it.get("bbox"))),
            ),
        )
    return tables[0]


def _bbox_area(bbox: list[float]) -> float:
    if len(bbox) != 4:
        return 0.0
    return abs((bbox[2] - bbox[0]) * (bbox[1] - bbox[3]))


def _bbox_overlap_area(a: list[float], b: list[float]) -> float:
    if len(a) != 4 or len(b) != 4:
        return 0.0
    left = max(min(a[0], a[2]), min(b[0], b[2]))
    right = min(max(a[0], a[2]), max(b[0], b[2]))
    bottom = max(min(a[1], a[3]), min(b[1], b[3]))
    top = min(max(a[1], a[3]), max(b[1], b[3]))
    if right <= left or top <= bottom:
        return 0.0
    return (right - left) * (top - bottom)


# ── Per-page markdown rendering ──────────────────────────────────────────────


def render_pages_md(docling: dict[str, Any]) -> dict[int, str]:
    """Render every page of a docling JSON as faithful markdown."""
    items = docling.get("items")
    if not isinstance(items, list):
        return {}

    by_page: dict[int, list[dict[str, Any]]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        page = it.get("page")
        if not isinstance(page, (int, float)):
            continue
        by_page.setdefault(int(page), []).append(it)

    out: dict[int, str] = {}
    for page in sorted(by_page):
        out[page] = _render_page_md(by_page[page])
    return out


def _render_page_md(items: list[dict[str, Any]]) -> str:
    def sort_key(it: dict[str, Any]) -> tuple[float, float]:
        bbox = it.get("bbox") or [0, 0, 0, 0]
        top = bbox[1] if len(bbox) == 4 else 0
        left = bbox[0] if len(bbox) == 4 else 0
        return (-float(top), float(left))

    ordered = sorted(items, key=sort_key)
    lines: list[str] = []
    in_list = False

    for it in ordered:
        label = it.get("label")
        text = (it.get("text") or "").strip()

        if label != "list_item" and in_list:
            lines.append("")
            in_list = False

        if label == "title" and text:
            lines.append(f"# {text}")
            lines.append("")
        elif label == "section_header" and text:
            level = 1 if text.isupper() and len(text) <= 40 else 2
            lines.append(f"{'#' * (level + 1)} {text}")
            lines.append("")
        elif label == "text" and text:
            lines.append(text)
            lines.append("")
        elif label == "list_item" and text:
            lines.append(f"- {text}")
            in_list = True
        elif label == "footnote" and text:
            lines.append(f"> {text}")
            lines.append("")
        elif label == "picture":
            cap = text or "figure"
            lines.append(f"_[figure: {cap}]_")
            lines.append("")
        elif label == "table":
            md = _render_table_md(it.get("cells"))
            if md:
                lines.append(md)
                lines.append("")

    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _render_table_md(cells: Any) -> str:
    if not isinstance(cells, list) or not cells:
        return ""
    grid: dict[tuple[int, int], str] = {}
    rows = cols = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        r = cell.get("row")
        c = cell.get("col")
        if not isinstance(r, int) or not isinstance(c, int):
            continue
        text = (cell.get("text") or "").strip().replace("|", "\\|").replace("\n", " ")
        grid[(r, c)] = text
        rows = max(rows, r + 1)
        cols = max(cols, c + 1)
    if rows == 0 or cols == 0:
        return ""

    def row_md(r: int) -> str:
        return "| " + " | ".join(grid.get((r, c), "") for c in range(cols)) + " |"

    out = [row_md(0), "| " + " | ".join(["---"] * cols) + " |"]
    for r in range(1, rows):
        out.append(row_md(r))
    return "\n".join(out)


# ── Per-page metadata ────────────────────────────────────────────────────────


def build_pages_meta(docling: dict[str, Any]) -> dict[str, Any]:
    items = docling.get("items")
    if not isinstance(items, list):
        items = []

    by_page: dict[int, list[dict[str, Any]]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        page = it.get("page")
        if not isinstance(page, (int, float)):
            continue
        by_page.setdefault(int(page), []).append(it)

    pages: dict[str, Any] = {}
    for page in sorted(by_page):
        page_items = by_page[page]
        labels: dict[str, int] = {}
        item_ids: list[str] = []
        union: list[float] | None = None
        for idx, it in enumerate(page_items):
            label = it.get("label") or "unknown"
            labels[label] = labels.get(label, 0) + 1
            item_ids.append(f"p{page}-i{idx}")
            bbox = _clean_bbox(it.get("bbox"))
            if len(bbox) == 4:
                if union is None:
                    union = list(bbox)
                else:
                    union[0] = min(union[0], bbox[0])
                    union[1] = max(union[1], bbox[1])
                    union[2] = max(union[2], bbox[2])
                    union[3] = min(union[3], bbox[3])
        pages[str(page)] = {
            "item_count": len(page_items),
            "labels": labels,
            "item_ids": item_ids,
            "bbox_union": union or [],
        }

    return {
        "page_count": max(by_page) if by_page else 0,
        "pages": pages,
    }


# Cap candidate text so a dense page does not balloon the persisted
# candidates file or the harness work-item payload. The agent reads the
# page image and raw markdown for the full content; candidate text is a
# grouping aid, not the content channel.
_CANDIDATE_TEXT_MAX = 800


def build_page_candidates(docling: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    """Per-page docling candidate items: `{page: [{id, label, bbox, text}]}`.

    Ids reuse the stable `p{page}-i{idx}` scheme `build_pages_meta` mints,
    with `idx` being the item's position within its page (docling order),
    so the two artifacts always agree. Table items additionally carry a
    `cells_preview` so an agent can group a table without reading cells.
    """
    items = docling.get("items")
    if not isinstance(items, list):
        items = []

    by_page: dict[int, list[dict[str, Any]]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        page = it.get("page")
        if not isinstance(page, (int, float)):
            continue
        by_page.setdefault(int(page), []).append(it)

    out: dict[int, list[dict[str, Any]]] = {}
    for page in sorted(by_page):
        candidates: list[dict[str, Any]] = []
        for idx, it in enumerate(by_page[page]):
            text = (it.get("text") or "").strip()
            candidate: dict[str, Any] = {
                "id": f"p{page}-i{idx}",
                "label": it.get("label") or "unknown",
                "bbox": _clean_bbox(it.get("bbox")),
                "text": text[:_CANDIDATE_TEXT_MAX],
            }
            if it.get("label") == "table":
                header_row, _, shape = _summarize_table_cells(it.get("cells"))
                candidate["cells_preview"] = {"shape": shape, "header_row": header_row}
                cells = _clean_table_cells(it.get("cells"))
                if cells:
                    candidate["cells"] = cells
            candidates.append(candidate)
        out[page] = candidates
    return out


# ── Bbox helpers ─────────────────────────────────────────────────────────────


def _normalize_text(s: str) -> str:
    return " ".join(s.lower().split())


def find_items_by_text(
    docling: dict[str, Any],
    needle: str,
    *,
    page: int | None = None,
) -> list[dict[str, Any]]:
    """Return docling items whose text contains `needle` (case-insensitive)."""
    items = docling.get("items")
    if not isinstance(items, list):
        return []
    target = _normalize_text(needle)
    if not target:
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if page is not None and it.get("page") != page:
            continue
        text = _normalize_text(it.get("text") or "")
        if target in text:
            out.append(it)
    return out


def union_bbox(bboxes: list[list[float]]) -> list[float]:
    """Compute the BOTTOMLEFT bbox union of a list of bboxes."""
    cleaned = [b for b in bboxes if len(b) == 4]
    if not cleaned:
        return []
    left = min(b[0] for b in cleaned)
    top = max(b[1] for b in cleaned)
    right = max(b[2] for b in cleaned)
    bottom = min(b[3] for b in cleaned)
    return [left, top, right, bottom]


def bbox_center(bbox: list[float]) -> tuple[float, float] | None:
    if len(bbox) != 4:
        return None
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def point_in_bbox(point: tuple[float, float], bbox: list[float]) -> bool:
    """BOTTOMLEFT containment. Tolerates either Y ordering."""
    if len(bbox) != 4:
        return False
    x, y = point
    if bbox[0] > bbox[2]:
        return False
    left, right = bbox[0], bbox[2]
    bottom, top = min(bbox[1], bbox[3]), max(bbox[1], bbox[3])
    return left <= x <= right and bottom <= y <= top


def snap_to_docling_items(
    docling: dict[str, Any],
    page: int,
    approx_bbox: list[float],
) -> tuple[list[float], list[int]]:
    """Snap an approximate bbox (e.g. from a VLM) to docling items on a page."""
    items = docling.get("items")
    if not isinstance(items, list) or len(approx_bbox) != 4:
        return ([], [])

    absorbed_bboxes: list[list[float]] = []
    absorbed_idx: list[int] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict) or it.get("page") != page:
            continue
        bbox = _clean_bbox(it.get("bbox"))
        center = bbox_center(bbox)
        if center is None:
            continue
        if point_in_bbox(center, approx_bbox):
            absorbed_bboxes.append(bbox)
            absorbed_idx.append(idx)

    return (union_bbox(absorbed_bboxes), absorbed_idx)


def needs_polish(
    docling: dict[str, Any],
    page: int,
    *,
    item_threshold: int = 25,
) -> bool:
    """Heuristic: pages with many items, tables, or pictures benefit from polish."""
    items = docling.get("items")
    if not isinstance(items, list):
        return False
    page_items = [it for it in items if isinstance(it, dict) and it.get("page") == page]
    if not page_items:
        return False
    if len(page_items) >= item_threshold:
        return True
    labels = {it.get("label") for it in page_items}
    return "table" in labels or "picture" in labels
