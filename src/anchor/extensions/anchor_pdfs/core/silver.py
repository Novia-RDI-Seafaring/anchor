"""Silver builders — pure functions over docling JSON dicts.

NOTE: the I/O-coupled helpers (`render_pages_png`, the `polish_pages_md`
driver, `PageMdPolisherClient` Protocol) live in `infra/pdf/` and
`core/ports/md_polisher.py` respectively. This module is dict-in / dict-out.
"""
from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.silver_quality import (
    LOW_TEXT_CHAR_THRESHOLD as _LOW_TEXT_CHAR_THRESHOLD,
)
from anchor.extensions.anchor_pdfs.core.silver_quality import (
    find_low_text_pages as _find_low_text_pages,
)
from anchor.extensions.anchor_pdfs.core.silver_quality import (
    low_text_pages_warning as _low_text_pages_warning,
)

LOW_TEXT_CHAR_THRESHOLD = _LOW_TEXT_CHAR_THRESHOLD
find_low_text_pages = _find_low_text_pages
low_text_pages_warning = _low_text_pages_warning

# Silver Docling section-header labels we promote into the outline.
_SECTION_LABELS = {"section_header", "title"}

#: Canonical bbox convention for every silver/gold/source_ref bbox (#281,
#: mirrors OIP `pdf-page-bbox`): PDF points, top-left origin,
#: ``[left, top, right, bottom]`` with ``top <= bottom``.
BBOX_ORIGIN = "top-left"


def normalize_items(docling: dict[str, Any]) -> dict[str, Any]:
    """Enforce the bbox contract at the extractor boundary (#281).

    Every ``PdfExtractor`` must deliver ``BBOX_ORIGIN`` boxes in PDF points.
    This normaliser is the one place that guarantees it, so a second
    extractor cannot silently ship flipped or out-of-page boxes:

    - an extractor that declares ``coord_origin: "bottom-left"`` is converted
      here using the page heights it reported (``docling["pages"]``);
    - every bbox is normalised to ``top <= bottom`` / ``left <= right``;
    - boxes that are not four finite numbers are dropped (``[]``), and boxes
      outside the page are clamped to it when the page size is known.

    Returns a new dict stamped ``coord_origin: BBOX_ORIGIN``.
    """
    items = docling.get("items")
    if not isinstance(items, list):
        return {**docling, "coord_origin": BBOX_ORIGIN}
    pages = docling.get("pages") if isinstance(docling.get("pages"), dict) else {}
    origin = str(docling.get("coord_origin") or BBOX_ORIGIN).lower().replace("_", "-")
    if origin not in {"top-left", "bottom-left"}:
        raise ValueError(f"extractor declared unsupported coord_origin {origin!r}")

    def size_of(page: Any) -> tuple[float, float] | None:
        entry = pages.get(page) if pages else None
        if entry is None and pages:
            entry = pages.get(str(page))
        if isinstance(entry, dict):
            w, h = entry.get("width"), entry.get("height")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
                return float(w), float(h)
        return None

    def fix(bbox: Any, size: tuple[float, float] | None) -> list[float]:
        clean = _clean_bbox(bbox)
        if len(clean) != 4:
            return []
        if origin == "bottom-left":
            if size is None:
                raise ValueError(
                    "extractor declared bottom-left bboxes but reported no page sizes"
                )
            clean = flip_bbox_y(clean, size[1])
        left, right = sorted((clean[0], clean[2]))
        top, bottom = sorted((clean[1], clean[3]))
        if size is not None:
            w, h = size
            left, right = max(0.0, min(left, w)), max(0.0, min(right, w))
            top, bottom = max(0.0, min(top, h)), max(0.0, min(bottom, h))
        return [left, top, right, bottom]

    out_items: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        size = size_of(it.get("page"))
        fixed = {**it, "bbox": fix(it.get("bbox"), size)}
        cells = it.get("cells")
        if isinstance(cells, list):
            fixed["cells"] = [
                {**c, "bbox": fix(c.get("bbox"), size)} if isinstance(c, dict) and c.get("bbox") else c
                for c in cells
            ]
        out_items.append(fixed)
    tables = docling.get("tables")
    out_tables = None
    if isinstance(tables, list):
        out_tables = []
        for t in tables:
            if not isinstance(t, dict):
                continue
            size = size_of(t.get("page"))
            fixed_t = {**t, "bbox": fix(t.get("bbox"), size)}
            if isinstance(t.get("cells"), list):
                fixed_t["cells"] = [
                    {**c, "bbox": fix(c.get("bbox"), size)} if isinstance(c, dict) and c.get("bbox") else c
                    for c in t["cells"]
                ]
            out_tables.append(fixed_t)
    out = {**docling, "items": out_items, "coord_origin": BBOX_ORIGIN}
    if out_tables is not None:
        out["tables"] = out_tables
    return out


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
        # Reading order: top-left origin, so a smaller y is higher on the page.
        bbox = it.get("bbox") or [0, 0, 0, 0]
        top = min(bbox[1], bbox[3]) if len(bbox) == 4 else 0
        left = bbox[0] if len(bbox) == 4 else 0
        return (float(top), float(left))

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
            md = render_table_cells_md(it.get("cells"))
            if md:
                lines.append(md)
                lines.append("")

    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def render_table_cells_md(cells: Any) -> str:
    """Render table cells as compact markdown while preserving cell order."""
    if not isinstance(cells, list) or not cells:
        return ""
    grid: dict[tuple[int, int], str] = {}
    row_indexes: set[int] = set()
    column_indexes: set[int] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        r = cell.get("row")
        c = cell.get("col")
        if not isinstance(r, int) or not isinstance(c, int):
            continue
        text = (cell.get("text") or "").strip().replace("|", "\\|").replace("\n", " ")
        # Two cells can resolve to the same (row, col): docling repeats a
        # span's text across the positions it covers, and dense tables can
        # emit distinct cells at one grid coordinate. A plain assignment
        # keeps only the last and silently drops the rest (issue #129:
        # missing / collapsed values). Coalesce instead - dedup identical
        # text (span repetition), but preserve distinct texts side by side.
        existing = grid.get((r, c))
        if existing and text and text != existing:
            grid[(r, c)] = f"{existing} {text}"
        elif not existing:
            grid[(r, c)] = text
        row_indexes.add(r)
        column_indexes.add(c)
    rows = sorted(row_indexes)
    columns = sorted(column_indexes)
    if not rows or not columns:
        return ""

    def row_md(r: int) -> str:
        return "| " + " | ".join(grid.get((r, c), "") for c in columns) + " |"

    out = [row_md(rows[0]), "| " + " | ".join(["---"] * len(columns)) + " |"]
    for r in rows[1:]:
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

    page_sizes = docling.get("pages") if isinstance(docling.get("pages"), dict) else {}

    pages: dict[str, Any] = {}
    for page in sorted(by_page):
        page_items = by_page[page]
        labels: dict[str, int] = {}
        item_ids: list[str] = []
        bboxes: list[list[float]] = []
        for idx, it in enumerate(page_items):
            label = it.get("label") or "unknown"
            labels[label] = labels.get(label, 0) + 1
            item_ids.append(f"p{page}-i{idx}")
            bbox = _clean_bbox(it.get("bbox"))
            if len(bbox) == 4:
                bboxes.append(bbox)
        entry: dict[str, Any] = {
            "item_count": len(page_items),
            "labels": labels,
            "item_ids": item_ids,
            "bbox_union": union_bbox(bboxes),
        }
        size = page_sizes.get(page) or page_sizes.get(str(page))
        if isinstance(size, dict) and size.get("width") and size.get("height"):
            entry["page_size"] = [float(size["width"]), float(size["height"])]
        pages[str(page)] = entry

    return {
        "page_count": max(by_page) if by_page else 0,
        # Every bbox in silver/gold is top-left PDF points (#281). The stamp
        # lets a reader tell migrated data from legacy bottom-left files.
        "bbox_origin": BBOX_ORIGIN,
        "pages": pages,
    }


# Cap candidate text so a dense page does not balloon the persisted
# candidates file or the harness work-item payload. The agent reads the
# page image and raw markdown for the full content; candidate text is a
# grouping aid, not the content channel.
_CANDIDATE_TEXT_MAX = 800

# Cap server-derived region content so gold and embedding payloads remain
# bounded on dense tables.
_REGION_CONTENT_MAX = 6000


def region_content_from_items(
    items: Any,
    indexes: list[int] | None = None,
) -> str:
    """Render selected Docling items as trusted gold-region content."""
    if not isinstance(items, list):
        return ""
    selected = items
    if indexes is not None:
        selected = [items[index] for index in indexes if 0 <= index < len(items)]
    if not selected:
        return ""
    content = _render_page_md(
        [item for item in selected if isinstance(item, dict)]
    ).strip()
    return content[:_REGION_CONTENT_MAX].rstrip()


def region_search_text(region: dict[str, Any]) -> str:
    """Combine unique region fields for embedding and retrieval.

    #242 embedding fallback: the default text is ``title`` + ``description`` +
    ``content``. When the model authored no ``description``, a caption-less
    table (issue #231) would otherwise embed as just its title — and its cell
    values, the only searchable content it has, are invisible. In that case we
    fall back to the reconstructed table-cell text so the values stay findable.
    Deduped so a well-described table whose ``content`` already renders the grid
    is not double-counted.
    """
    parts: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if not isinstance(value, str):
            return
        text = value.strip()
        normalized = " ".join(text.split()).casefold()
        if text and normalized not in seen:
            seen.add(normalized)
            parts.append(text)

    for key in ("title", "description", "content"):
        add(region.get(key))

    description = region.get("description")
    if not (isinstance(description, str) and description.strip()):
        add(render_table_cells_md(region.get("cells")))

    return "\n\n".join(parts)


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
    """Union of bboxes in the canonical top-left convention (#281).

    Order-tolerant on input (either y ordering per box); the result is
    ``[left, top, right, bottom]`` with ``top <= bottom``."""
    cleaned = [b for b in bboxes if len(b) == 4]
    if not cleaned:
        return []
    left = min(min(b[0], b[2]) for b in cleaned)
    top = min(min(b[1], b[3]) for b in cleaned)
    right = max(max(b[0], b[2]) for b in cleaned)
    bottom = max(max(b[1], b[3]) for b in cleaned)
    return [left, top, right, bottom]


def flip_bbox_y(bbox: list[float], page_height: float) -> list[float]:
    """Convert a bbox between bottom-left and top-left origins (``y' = h - y``).

    The mapping is its own inverse. Returns ``[left, top, right, bottom]``
    normalised to ``top <= bottom`` in the target orientation."""
    if len(bbox) != 4:
        return []
    left, right = sorted((float(bbox[0]), float(bbox[2])))
    y0, y1 = sorted((page_height - float(bbox[1]), page_height - float(bbox[3])))
    return [left, y0, right, y1]


def bbox_center(bbox: list[float]) -> tuple[float, float] | None:
    if len(bbox) != 4:
        return None
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def point_in_bbox(point: tuple[float, float], bbox: list[float]) -> bool:
    """Containment in page space (top-left convention; tolerates either Y
    ordering, so it is orientation-agnostic)."""
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
