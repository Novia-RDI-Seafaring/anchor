"""Deterministic silver -> index builder.

Produces a compact "table of contents" for a document that the agent can
load cheaply to know what's in the PDF and where to find it, without
calling any LLM. The index is a pure function of the silver Docling JSON
and can be regenerated at any time.

Schema (see cuddly-purring-bonbon plan):
    {
        "document": { "filename", "title", "page_count" },
        "outline":  [ { "level", "title", "page", "bbox" }, ... ],
        "tables":   [ { "id", "page", "bbox", "caption", "shape": {"rows","cols"},
                        "header_row", "first_column_values" }, ... ],
        "figures":  [ { "page", "bbox", "caption" }, ... ],
    }

All bboxes follow the silver Docling convention: [left, top, right, bottom]
in BOTTOMLEFT coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# Default frontier model for silver page md polishing.
DEFAULT_PAGE_MD_MODEL = "gpt-5.4"

# Silver Docling section-header labels we promote into the outline.
_SECTION_LABELS = {"section_header", "title"}


def build_index(docling: dict[str, Any], *, filename: str = "", title: str = "") -> dict[str, Any]:
    """Build an index dict from a silver Docling JSON dict.

    The silver format this consumes has a flat `items` list where each item
    carries at minimum: label, text, page, bbox (list of 4 floats).
    """
    items = docling.get("items")
    if not isinstance(items, list):
        items = []

    pages = {int(it["page"]) for it in items if isinstance(it, dict) and isinstance(it.get("page"), (int, float))}
    page_count = max(pages) if pages else 0

    outline: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []

    # Running caption candidate: the most recent section header on the same page
    # before a table/picture — we use it as a cheap caption hint.
    last_header_by_page: dict[int, str] = {}

    # Resolved title falls back to the first section header if not provided.
    resolved_title = title

    for idx, it in enumerate(items):
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
    """Cheap heading-level heuristic: shorter / ALL-CAPS reads as higher level."""
    if text.isupper() and len(text) <= 40:
        return 1
    if len(text) <= 60:
        return 2
    return 3


def _summarize_table_cells(cells: Any) -> tuple[list[str], list[str], dict[str, int]]:
    """Return (header_row, first_column_values, shape) from docling table cells.

    - header_row: text of row-0 cells in column order (deduped of blanks).
    - first_column_values: text of col-0 cells in row order, excluding row 0
      (the header). Useful so the agent sees 'this table lists SP-5, SP-10, ...'
      without having to open the table.
    - shape: {"rows": int, "cols": int}
    """
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


# ── Per-page markdown rendering ──────────────────────────────────────────────


def render_pages_md(docling: dict[str, Any]) -> dict[int, str]:
    """Render every page of a docling JSON as faithful markdown.

    Pure function — no LLM, no IO. Walks items in reading order (top to bottom,
    left to right using BOTTOMLEFT bbox), groups them per page, and emits a
    markdown string per page. Tables become GitHub-flavored markdown tables.
    """
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
    # BOTTOMLEFT coords: higher top value = higher on page → sort -top, then left.
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

    # Collapse trailing blanks
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _render_table_md(cells: Any) -> str:
    """Render docling cells as a GitHub-flavored markdown table."""
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
    """Per-page summary metadata: item count, label histogram, page bbox.

    Pure function; the result is the on-disk shape of `pages.meta.json`.
    Page bbox is the union of all docling item bboxes on that page (a cheap
    proxy for the printable area when the docling JSON doesn't carry page
    dims directly).
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
                    union[1] = max(union[1], bbox[1])  # BOTTOMLEFT: top is max
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


# ── Bbox helpers — fuzzy text match + snap union ─────────────────────────────


def _normalize_text(s: str) -> str:
    return " ".join(s.lower().split())


def find_items_by_text(
    docling: dict[str, Any],
    needle: str,
    *,
    page: int | None = None,
) -> list[dict[str, Any]]:
    """Return docling items whose text contains `needle` (case-insensitive,
    whitespace-normalized). Optionally restricted to a page.

    Used by the bbox-backfill pass: gold sections name a value, we look up
    which silver items contain that text and copy their bbox over.
    """
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
    """BOTTOMLEFT containment: bbox = [left, top, right, bottom] with top > bottom."""
    if len(bbox) != 4:
        return False
    x, y = point
    left, top, right, bottom = bbox
    return left <= x <= right and bottom <= y <= top


def snap_to_docling_items(
    docling: dict[str, Any],
    page: int,
    approx_bbox: list[float],
) -> tuple[list[float], list[int]]:
    """Snap an approximate bbox (e.g. from a VLM) to docling items on a page.

    Returns `(snapped_bbox, item_indices)` where `snapped_bbox` is the union
    of every item whose bbox center falls inside `approx_bbox`. The indices
    are positions in the original `docling['items']` list — useful for
    building `source_refs` back to silver.
    """
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


# ── Per-page image rendering ─────────────────────────────────────────────────


# ── LLM-polished page markdown ───────────────────────────────────────────────


class PageMdPolisherClient(Protocol):
    """Minimal interface the polisher needs from a vision-capable LLM client.

    Implementations get the page image + the deterministic markdown seed +
    the docling items on the page (so the model can ground itself in real
    text rather than re-OCR-ing the image), and return clean markdown.

    The default `_StubMdPolisher` raises — real clients are plugged in at
    the call site so tests don't pull in OpenAI.
    """

    def polish_page(
        self,
        *,
        page_image: Path,
        page_no: int,
        deterministic_md: str,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> str: ...


@dataclass
class _StubMdPolisher:
    def polish_page(self, **kwargs: Any) -> str:
        raise RuntimeError(
            "No PageMdPolisherClient configured. Pass `client=...` to "
            "polish_pages_md, or build a real client at the call site."
        )


def needs_polish(
    docling: dict[str, Any],
    page: int,
    *,
    item_threshold: int = 25,
) -> bool:
    """Heuristic: pages with many docling items, tables, or pictures benefit
    from an LLM polish pass; short narrative pages don't.

    Default threshold is conservative — chart pages have hundreds of items,
    spec pages a couple dozen, narrative pages well under that.
    """
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


def polish_pages_md(
    docling: dict[str, Any],
    *,
    pages_png_dir: Path,
    deterministic_md: dict[int, str],
    client: PageMdPolisherClient | None = None,
    model: str = DEFAULT_PAGE_MD_MODEL,
    only_pages: list[int] | None = None,
) -> dict[int, str]:
    """Run the polisher over every page (or only the listed ones).

    Returns `{page_no: polished_md}`. Pages that don't need polishing
    (per `needs_polish`) and aren't explicitly listed are returned with
    their deterministic md unchanged.
    """
    items = docling.get("items") or []
    by_page: dict[int, list[dict[str, Any]]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        page = it.get("page")
        if not isinstance(page, (int, float)):
            continue
        by_page.setdefault(int(page), []).append(it)

    extractor = client or _StubMdPolisher()
    out: dict[int, str] = {}
    for page in sorted(by_page):
        seed = deterministic_md.get(page, "")
        wanted = (only_pages and page in only_pages) or needs_polish(docling, page)
        if not wanted:
            out[page] = seed
            continue
        page_image = pages_png_dir / f"{page}.png"
        out[page] = extractor.polish_page(
            page_image=page_image,
            page_no=page,
            deterministic_md=seed,
            docling_items=by_page[page],
            model=model,
        )
    return out


def render_pages_png(pdf_path: Path, out_dir: Path, *, dpi: int = 150) -> list[Path]:
    """Render every page of a PDF to PNG at the given DPI.

    Uses PyMuPDF (already a backend dependency). Writes `out_dir/N.png` for
    each 1-indexed page and returns the list of written paths.
    """
    import pymupdf  # local import — avoids paying the cost when only md is needed

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            target = out_dir / f"{i}.png"
            pix.save(target)
            written.append(target)
    return written
