"""Resolve a ``source_ref`` to the most precise stored evidence (#242 P2b).

A ref may carry optional selectors beyond the region: ``item_id`` (one
silver item, ``p<page>-i<n>``) and ``cell`` (``{row, col}`` of a table).
Resolution precedence is cell > item > region > bbox; the answer reports
which layer resolved (``precision``) so callers — the viewer's highlight,
an agent citing evidence — can trust the bbox they get. A ref that names
a selector whose geometry is not stored falls through to the next layer
rather than failing, so legacy refs resolve exactly as before.

A ref may also name MORE THAN ONE place, under ``also``. One claim can be
evidenced in several spots at once: the value in a specification table and
the callout that names the same dimension on the drawing beside it. Which
of them is "the" place is not a judgement the resolver should make, so the
ref keeps its own shape as the primary -- that is what a caller scrolls to
-- and the extra places come back alongside it, each resolved on its own
terms and reporting its own precision. ``also`` does not nest: a place is
a place, not a tree.
"""
from __future__ import annotations

import re
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.region_inspect import find_region
from anchor.extensions.anchor_pdfs.core.silver import table_cells_from_items

_ITEM_ID = re.compile(r"^p(\d+)-i\d+$")


def _bbox(value: Any) -> list[float] | None:
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
    ):
        return [float(v) for v in value]
    return None


#: How many extra places one ref may name. A highlight the reader cannot
#: count at a glance is not evidence, it is confetti.
MAX_ALSO = 8


def _numbers(text: str) -> list[float] | None:
    """An even run of at least two coordinate pairs, or nothing."""
    parts = [t.strip() for t in (text or "").split(",") if t.strip()]
    if len(parts) < 4 or len(parts) % 2:
        return None
    out: list[float] = []
    for t in parts:
        try:
            out.append(float(t))
        except ValueError:
            return None
    return out


def parse_place(text: str) -> dict[str, Any] | None:
    """Parse the compact form of one place, e.g. ``p3/r1/item:p3-i6``.

    The long form (a JSON object) is what agents write through MCP and the
    CLI. This is for the places that have to survive a URL: an ``anchor:``
    link in a Markdown card, and the ``also=`` query parameter. Shapes:

        p3                      the page
        p3/r4                   a region on it
        p3/r1/item:p3-i6        one silver item
        p3/r2/cell:1,2          one table cell
        p3/line:x1,y1,x2,y2     a stroke, not a box

    A line is for geometry a rectangle describes badly. A dimension on an
    engineering drawing is a span between two witness lines, and boxing it
    would cover the part of the drawing the span is measuring. Tracing the
    stroke the draughtsman already drew says the same thing in the drawing's
    own language. Points are page coordinates, in pairs, at least two.

    Returns None for anything it does not recognise, so one malformed extra
    place never costs the reader the ones that were fine.
    """
    parts = [seg for seg in (text or "").strip().split("/") if seg]
    if not parts:
        return None
    m = re.match(r"^p(\d+)$", parts[0])
    if not m:
        return None
    place: dict[str, Any] = {"page": int(m.group(1))}
    if len(parts) > 1:
        place["region_id"] = parts[1]
    # `p3/line:...` puts the selector where a region id would go, because a
    # stroke does not belong to one region: a dimension crosses whatever it
    # measures.
    if len(parts) > 1 and parts[1].startswith("line:"):
        pts = _numbers(parts[1][len("line:") :])
        if pts is None:
            return None
        return {"page": place["page"], "line": pts}
    if len(parts) > 2:
        kind, _, rest = parts[2].partition(":")
        if kind == "line" and rest:
            pts = _numbers(rest)
            if pts is None:
                return None
            place["line"] = pts
            return place
        if kind == "item" and rest:
            place["item_id"] = rest
        elif kind == "cell":
            nums = rest.split(",")
            if len(nums) == 2 and all(n.strip().lstrip("-").isdigit() for n in nums):
                place["cell"] = {"row": int(nums[0]), "col": int(nums[1])}
            else:
                return None
        else:
            return None
    return place


async def resolve_source_ref(
    store: DocStore, slug: str, ref: dict[str, Any]
) -> dict[str, Any] | None:
    """Return ``{slug, page, bbox, precision, ...selectors}`` or None.

    When the ref names extra places under ``also``, each is resolved too and
    the answer carries ``also: [...]``. An extra place that does not resolve
    is dropped rather than failing the whole answer: the reader still gets
    the evidence that IS there, which beats a highlight that never appears.
    """
    primary = await _resolve_one(store, slug, ref)
    if primary is None:
        return None
    extras = ref.get("also")
    if not isinstance(extras, list):
        return primary
    resolved: list[dict[str, Any]] = []
    for extra in extras[:MAX_ALSO]:
        if isinstance(extra, str):
            extra = parse_place(extra)
        if not isinstance(extra, dict):
            continue
        # One level only. A place is a place, not a tree.
        one = await _resolve_one(store, slug, {k: v for k, v in extra.items() if k != "also"})
        if one is not None:
            resolved.append(one)
    if resolved:
        primary["also"] = resolved
    return primary


async def _resolve_one(
    store: DocStore, slug: str, ref: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve exactly one place.

    ``ref.slug`` wins over the ``slug`` argument. Page is taken from the
    ref, parsed from ``item_id``, or found via the region id.
    """
    slug = ref.get("slug") or slug
    store = store.snapshot(slug)
    page = ref.get("page") if isinstance(ref.get("page"), int) else None
    region_id = ref.get("region_id") if isinstance(ref.get("region_id"), str) else None
    item_id = ref.get("item_id") if isinstance(ref.get("item_id"), str) else None
    cell = ref.get("cell") if isinstance(ref.get("cell"), dict) else None

    if page is None and item_id:
        m = _ITEM_ID.match(item_id)
        if m:
            page = int(m.group(1))

    region: dict[str, Any] | None = None
    if region_id:
        token = f"p{page}/{region_id}" if page is not None else region_id
        found = await find_region(store, slug, token)
        if found is not None:
            page, region = found

    if page is None:
        # A bare bbox ref still answers, page unknown refs cannot.
        return None

    def _answer(bbox: list[float], precision: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "slug": slug,
            "page": page,
            "bbox": bbox,
            "precision": precision,
        }
        if region_id:
            out["region_id"] = region_id
        if item_id and precision == "item":
            out["item_id"] = item_id
        if cell and precision == "cell":
            out["cell"] = {"row": cell.get("row"), "col": cell.get("col")}
        return out

    line = ref.get("line")
    if isinstance(line, list) and len(line) >= 4 and len(line) % 2 == 0:
        try:
            pts = [float(v) for v in line]
        except (TypeError, ValueError):
            pts = []
        if pts:
            xs, ys = pts[0::2], pts[1::2]
            out = _answer([min(xs), min(ys), max(xs), max(ys)], "line")
            # The bounds are there for callers that only understand boxes.
            # The stroke is the point.
            out["line"] = pts
            return out

    if cell is not None:
        bbox = await _cell_bbox(store, slug, page, region, cell)
        if bbox is not None:
            return _answer(bbox, "cell")

    if item_id:
        candidates = await store.get_page_candidates(slug, page) or []
        for c in candidates:
            if isinstance(c, dict) and c.get("id") == item_id:
                bbox = _bbox(c.get("bbox"))
                if bbox is not None:
                    return _answer(bbox, "item")
                break

    if region is not None:
        bbox = _bbox(region.get("bbox")) or _bbox(region.get("approx_bbox"))
        if bbox is not None:
            return _answer(bbox, "region")

    bbox = _bbox(ref.get("bbox"))
    if bbox is not None:
        return _answer(bbox, "bbox")
    return None


async def _cell_bbox(
    store: DocStore,
    slug: str,
    page: int,
    region: dict[str, Any] | None,
    cell: dict[str, Any],
) -> list[float] | None:
    row, col = cell.get("row"), cell.get("col")
    if not isinstance(row, int) or not isinstance(col, int):
        return None

    def pick(cells: Any) -> list[float] | None:
        for c in cells or []:
            if (
                isinstance(c, dict)
                and c.get("row") == row
                and c.get("col") == col
            ):
                return _bbox(c.get("bbox"))
        return None

    if region is not None:
        bbox = pick(region.get("cells"))
        if bbox is not None:
            return bbox
    # Fall back to the silver table geometry (#270 stores per-cell bboxes).
    candidates = await store.get_page_candidates(slug, page) or []
    region_bbox = _bbox(region.get("bbox")) if region else None
    return pick(table_cells_from_items(candidates, region_bbox=region_bbox))
