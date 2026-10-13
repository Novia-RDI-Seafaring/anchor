"""Geometry guards shared by the two gold paths.

A region extractor, harness or model, hands back a box or a list of items.
Three things go wrong often enough to guard against here, in one place:

* the box is in raster pixels, not PDF points (``in_page_points``);
* a picture region drags along the table under the drawing
  (``keep_picture_items``);
* a block region runs on past its block into the next one, so two regions
  claim the same Docling table (``keep_block_items``).

Items are Docling items in top-left points, each with ``label`` and ``bbox``.
"""

from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.silver import union_bbox

#: Region kinds whose geometry is a picture.
PICTURE_KINDS = frozenset({"diagram", "figure", "chart"})

#: Region kinds whose geometry is one table (plus its heading).
BLOCK_KINDS = frozenset({"table", "spec_block"})

#: Docling items that are one block on the page.
EXCLUSIVE_LABELS = frozenset({"table", "picture"})

#: Slack, in points, for a bbox at the page edge.
PAGE_TOLERANCE = 2.0

#: How far above its table a heading may sit and still be the block's heading.
HEADING_GAP = 40.0


def in_page_points(
    bbox: list[float],
    page_size: list[float] | tuple[float, float],
    dpi: int | None,
) -> tuple[list[float], str | None]:
    """Return the bbox in points, or why it cannot be.

    A bbox inside the page is taken as points. One outside the page that fits
    the raster the extractor looked at is pixels, and is scaled. One outside
    both is a mistake worth saying so about.
    """
    width, height = float(page_size[0]), float(page_size[1])

    def inside(box: list[float], w: float, h: float) -> bool:
        tol = PAGE_TOLERANCE
        return box[0] >= -tol and box[1] >= -tol and box[2] <= w + tol and box[3] <= h + tol

    if inside(bbox, width, height):
        return bbox, None
    if dpi and inside(bbox, width * dpi / 72.0, height * dpi / 72.0):
        scale = 72.0 / dpi
        return [round(v * scale, 3) for v in bbox], None
    return bbox, (
        f"bbox {bbox} lies outside the page ({width:.0f} x {height:.0f} pt); "
        "send top-left PDF points, not pixels"
    )


def page_size_of(docling: dict[str, Any], page: int) -> list[float] | None:
    """``[width, height]`` in points for ``page``, from Docling's page table."""
    pages = docling.get("pages")
    if not isinstance(pages, dict):
        return None
    entry = pages.get(page) or pages.get(str(page))
    if isinstance(entry, dict) and entry.get("width") and entry.get("height"):
        return [float(entry["width"]), float(entry["height"])]
    return None


def keep_picture_items(items: list[dict[str, Any]]) -> list[int]:
    """Positions of the items a picture region keeps: its pictures and the
    items inside them. Without a picture among ``items`` every position is
    kept; there is nothing to clip to."""
    pictures = [_bbox(item) for item in items if item.get("label") == "picture"]
    pictures = [bbox for bbox in pictures if bbox]
    if not pictures:
        return list(range(len(items)))
    frame = union_bbox(pictures)
    return [
        pos for pos, item in enumerate(items)
        if item.get("label") == "picture" or mostly_inside(_bbox(item), frame)
    ]


def keep_block_items(items: list[dict[str, Any]], region_bbox: list[float]) -> list[int]:
    """Positions of the items a block region keeps: one table and its heading.

    With one table or none, every position is kept. With several, the block
    is the table ``region_bbox`` frames most completely, the topmost when it
    frames several whole (a box that runs on runs downward, so the block it
    was drawn for is the first one). The others, and whatever sits in them,
    go. A section heading just above the table stays.
    """
    tables = [(pos, _bbox(item)) for pos, item in enumerate(items) if item.get("label") == "table"]
    tables = [(pos, bbox) for pos, bbox in tables if bbox]
    if len(tables) < 2:
        return list(range(len(items)))

    def framed(entry: tuple[int, list[float]]) -> tuple[float, float]:
        bbox = entry[1]
        area = max(bbox[2] - bbox[0], 0.0) * max(bbox[3] - bbox[1], 0.0)
        fraction = overlap_area(bbox, region_bbox) / area if area > 0 else 0.0
        return (round(fraction, 3), -bbox[1])

    chosen_pos, chosen = max(tables, key=framed)
    kept: list[int] = []
    for pos, item in enumerate(items):
        bbox = _bbox(item)
        if pos == chosen_pos:
            kept.append(pos)
        elif item.get("label") == "table":
            continue
        elif mostly_inside(bbox, chosen):
            kept.append(pos)
        elif item.get("label") == "section_header" and bbox and _heads(bbox, chosen):
            kept.append(pos)
    return kept


def disown_shared_members(regions: list[dict[str, Any]]) -> dict[int, list[str]]:
    """Members a picture region must give up: the ones a block also names.

    A drawing's labels and the key beside it are both single letters; a
    model listing "the drawing" takes the key's letters along. The key is
    the block that owns them. Returns ``{position: remaining member ids}``
    for the picture regions that lose something.
    """
    owned: set[str] = set()
    for region in regions:
        if region.get("kind") not in PICTURE_KINDS:
            owned.update(m for m in region.get("member_item_ids") or [] if isinstance(m, str))
    changed: dict[int, list[str]] = {}
    for pos, region in enumerate(regions):
        if region.get("kind") not in PICTURE_KINDS:
            continue
        members = [m for m in region.get("member_item_ids") or [] if isinstance(m, str)]
        kept = [m for m in members if m not in owned]
        if kept != members:
            changed[pos] = kept
    return changed


def merge_into_pictures(
    regions: list[dict[str, Any]],
    pictures: list[list[float]],
) -> tuple[dict[int, list[float]], dict[int, list[int]]]:
    """Picture regions take the shape of the Docling picture they sit in.

    The PDF is the authority on what a drawing is. A model that names a
    drawing by its labels leaves the lines out, and the box crops it; a
    model that sees two views in one drawing calls them two diagrams. Both
    are corrected here: a picture region grows to its picture, and several
    picture regions inside one picture become one region. Splitting a
    drawing into views is a reader's request, made afterwards.

    Returns ``({keeper position: picture bbox}, {keeper position: absorbed
    positions})``; the keeper is the first region inside the picture.
    """
    frames: dict[int, list[float]] = {}
    absorbed: dict[int, list[int]] = {}
    taken: set[int] = set()
    for picture in pictures:
        inside = [
            pos for pos, region in enumerate(regions)
            if pos not in taken
            and region.get("kind") in PICTURE_KINDS
            and (box := _bbox(region)) and mostly_inside(box, picture)
        ]
        if not inside:
            continue
        keeper, *others = inside
        taken.update(inside)
        boxes = [list(picture)] + [b for pos in inside if (b := _bbox(regions[pos]))]
        frames[keeper] = union_bbox(boxes)
        if others:
            absorbed[keeper] = others
    return frames, absorbed


def merged_region(keeper: dict[str, Any], others: list[dict[str, Any]]) -> dict[str, Any]:
    """One region from several views of one drawing: titles and descriptions
    joined, members, tags and entities in first-seen order."""
    group = [keeper, *others]

    def joined(field: str, sep: str) -> str:
        parts = [str(r.get(field) or "").strip() for r in group]
        return sep.join(dict.fromkeys(p for p in parts if p))

    def union(field: str) -> list[Any]:
        return list(dict.fromkeys(v for r in group for v in (r.get(field) or []) if isinstance(v, str)))

    merged = {**keeper, "title": joined("title", "; ")[:300] or keeper.get("title")}
    description = joined("description", "\n\n")
    if description:
        merged["description"] = description[:4000]
    for field in ("member_item_ids", "tags", "entities"):
        values = union(field)
        if values or field in keeper:
            merged[field] = values
    return merged


def carve_out(
    frame: list[float],
    hole: list[float],
    keep: list[list[float]] | None = None,
) -> list[float]:
    """The part of ``frame`` left after cutting ``hole`` away on one side.

    A Docling picture that spans a drawing and the key beside it is one
    item; the key is its own region. Cutting on one side keeps the box a
    box: the part left of the hole, right of it, above it or below it.
    Among the parts that still hold every box in ``keep`` (the drawing's
    own labels) the largest wins; if none does, the largest part overall.
    """
    parts = [
        [frame[0], frame[1], hole[0], frame[3]],
        [hole[2], frame[1], frame[2], frame[3]],
        [frame[0], frame[1], frame[2], hole[1]],
        [frame[0], hole[3], frame[2], frame[3]],
    ]
    parts = [part for part in parts if part[2] - part[0] > 0 and part[3] - part[1] > 0]
    if not parts:
        return frame

    def area(part: list[float]) -> float:
        return (part[2] - part[0]) * (part[3] - part[1])

    holding = [part for part in parts if all(mostly_inside(box, part) for box in keep or [])]
    return max(holding or parts, key=area)


def picture_frames(
    regions: list[dict[str, Any]],
    own_boxes: dict[int, list[list[float]]] | None = None,
) -> dict[int, list[float]]:
    """For each picture region, its box with sibling regions carved out.

    Returns ``{position: new bbox}`` for the regions whose box changes. A
    sibling counts when it sits mostly inside the picture and is not a
    picture itself; one that covers nearly the whole picture is left alone,
    since then the two are the same thing seen twice. ``own_boxes`` maps a
    region's position to the boxes of its own labels, which a cut keeps.
    """
    changed: dict[int, list[float]] = {}
    for pos, region in enumerate(regions):
        if region.get("kind") not in PICTURE_KINDS:
            continue
        original = _bbox(region)
        if not original:
            continue
        frame = list(original)
        frame_area = (frame[2] - frame[0]) * (frame[3] - frame[1])
        for other_pos, other in enumerate(regions):
            if other_pos == pos or other.get("kind") in PICTURE_KINDS:
                continue
            hole = _bbox(other)
            if not hole or not mostly_inside(hole, frame):
                continue
            if frame_area > 0 and overlap_area(hole, frame) >= 0.9 * frame_area:
                continue
            keep = [box for box in (own_boxes or {}).get(pos, []) if not mostly_inside(box, hole)]
            frame = carve_out(frame, hole, keep)
        if frame != original:
            changed[pos] = frame
    return changed


#: Labels that make up the text block under a heading inside a picture.
_KEY_TEXT_LABELS = frozenset({"text", "list_item", "paragraph", "caption"})


def headed_blocks_in(
    frame: list[float],
    items: list[tuple[str, dict[str, Any]]],
    *,
    min_entries: int = 2,
) -> list[dict[str, Any]]:
    """Headed text blocks a picture's frame takes in: a key beside a drawing.

    Docling can draw one picture round a dimension drawing and the letter
    key next to it. Whether the key then got a region of its own depended on
    how the model happened to draw the page. Here it does not: a heading
    inside the frame with at least ``min_entries`` text items under it, in
    its column, is a block of its own. ``items`` are ``(candidate id,
    item)`` pairs for the page. Returns ``{"heading", "title", "members",
    "bbox"}`` per block; the caller makes them regions and cuts the picture.
    """
    blocks: list[dict[str, Any]] = []
    taken: set[str] = set()
    for hid, heading in items:
        if heading.get("label") != "section_header":
            continue
        hbox = _bbox(heading)
        if not hbox or not mostly_inside(hbox, frame):
            continue
        members = [
            mid for mid, item in items
            if mid not in taken
            and item.get("label") in _KEY_TEXT_LABELS
            and (box := _bbox(item))
            and mostly_inside(box, frame)
            and box[1] >= hbox[1] - PAGE_TOLERANCE
            and box[0] >= hbox[0] - PAGE_TOLERANCE
        ]
        if len(members) < min_entries:
            continue
        boxes = [hbox] + [b for mid, item in items if mid in members and (b := _bbox(item))]
        bbox = union_bbox(boxes)
        if not bbox:
            continue
        taken.update(members)
        blocks.append({
            "heading": hid,
            "title": " ".join(str(heading.get("text") or "").split()),
            "members": [hid, *members],
            "bbox": bbox,
        })
    return blocks


def adopt_table(named: list[dict[str, Any]], tables: list[dict[str, Any]]) -> int | None:
    """The page table a block region means, when it did not name one.

    A model naming a table by its heading and some cell texts can pick
    texts that also stand in another table ("PX-5" heads several). The
    heading decides: the table right under a named heading is the block.
    Without one, the table that holds most (over half) of the named items. Returns a
    position in ``tables``, or None.
    """
    boxes = [(pos, b) for pos, t in enumerate(tables) if (b := _bbox(t))]
    if not boxes:
        return None
    under = heading_table(named, tables)
    if under is not None:
        return under
    counts = {
        pos: sum(1 for item in named if mostly_inside(_bbox(item), box))
        for pos, box in boxes
    }
    best = max(counts, key=lambda pos: counts[pos])
    # Most of what was named must sit in the table; a text block that
    # brushes a table below it is not that table.
    return best if counts[best] * 2 > len(named) else None


def heading_table(named: list[dict[str, Any]], tables: list[dict[str, Any]]) -> int | None:
    """The table right under a named heading, as a position in ``tables``."""
    boxes = [(pos, b) for pos, t in enumerate(tables) if (b := _bbox(t))]
    for item in named:
        heading = _bbox(item)
        if item.get("label") == "section_header" and heading:
            under = [(pos, b) for pos, b in boxes if _heads(heading, b)]
            if under:
                return min(under, key=lambda entry: entry[1][1] - heading[3])[0]
    return None


def needs_adoption(named: list[dict[str, Any]], tables: list[dict[str, Any]]) -> bool:
    """A block region names no table, or names a table other than the one
    under its own heading. Either way the heading's table is the block:
    the heading is what the region was titled after."""
    named_tables = [item for item in named if item.get("label") == "table"]
    if not named_tables:
        return True
    under = heading_table(named, tables)
    if under is None:
        return False
    return not any(_bbox(t) == _bbox(tables[under]) for t in named_tables)


def outside_tables(named: list[dict[str, Any]], tables: list[dict[str, Any]]) -> list[int]:
    """Positions of the named items not inside any page table. A block with
    no table of its own does not hold another block's cells."""
    boxes = [b for t in tables if (b := _bbox(t))]
    return [
        pos for pos, item in enumerate(named)
        if not any(mostly_inside(_bbox(item), box) for box in boxes)
    ]


def settle_shared_tables(
    regions: list[dict[str, Any]],
    member: Any,
    tables: dict[str, dict[str, Any]],
    headings: dict[str, dict[str, Any]],
) -> dict[int, list[str]]:
    """One table, one block: a table goes to the block of the heading above it.

    ``member(id)`` returns the item for a member id or None; ``tables`` and
    ``headings`` are the page's table and section-header items by id. A
    block holds a table when it names it, or when its box holds the table
    and it names no items. When several blocks hold one table, the page's
    heading nearest above the table decides: the block that names it, or is
    titled with its text. The others give up the table and what is inside
    it. Returns ``{position: remaining member ids}`` for the blocks that
    lose something. For the path with no repair round; the harness path
    asks instead.
    """
    holders: dict[str, list[int]] = {}
    for pos, region in enumerate(regions):
        if region.get("kind") not in BLOCK_KINDS:
            continue
        named = region.get("member_item_ids") or []
        held = {mid for mid in named if mid in tables}
        if not named and (box := _bbox(region)):
            held = {tid for tid, t in tables.items() if mostly_inside(_bbox(t), box)}
        for tid in held:
            holders.setdefault(tid, []).append(pos)

    def text(value: Any) -> str:
        return " ".join(str(value or "").split()).casefold()

    changed: dict[int, list[str]] = {}
    for table_id, owners in holders.items():
        if len(owners) < 2:
            continue
        table = _bbox(tables[table_id]) or []
        above = [
            (table[1] - b[3], hid, h) for hid, h in headings.items()
            if (b := _bbox(h)) and b[3] <= table[1] + PAGE_TOLERANCE
            and min(b[2], table[2]) - max(b[0], table[0]) > 0
        ]
        winner = None
        if above:
            _, hid, heading = min(above, key=lambda entry: entry[0])
            for pos in owners:
                region = regions[pos]
                if hid in (region.get("member_item_ids") or []) or (
                    text(region.get("title")) and text(region.get("title")) == text(heading.get("text"))
                ):
                    winner = pos
                    break
        if winner is None:
            continue
        for pos in owners:
            if pos == winner:
                continue
            current = changed.get(pos, list(regions[pos].get("member_item_ids") or []))
            changed[pos] = [
                mid for mid in current
                if mid != table_id and not mostly_inside(_bbox(member(mid) or {}), table)
            ]
    return changed


def keep_in_table(named: list[dict[str, Any]], table: list[float]) -> list[int]:
    """Positions of the named items that belong to ``table``'s block: inside
    it, or its heading."""
    return [
        pos for pos, item in enumerate(named)
        if mostly_inside(_bbox(item), table)
        or (item.get("label") == "section_header" and (b := _bbox(item)) and _heads(b, table))
    ]


def mostly_inside(bbox: list[float] | None, frame: list[float]) -> bool:
    """At least half of ``bbox`` lies in ``frame`` (a point: inside it)."""
    if not bbox:
        return False
    left, top, right, bottom = bbox
    area = max(right - left, 0.0) * max(bottom - top, 0.0)
    if area <= 0:
        return frame[0] <= left <= frame[2] and frame[1] <= top <= frame[3]
    return overlap_area(bbox, frame) >= 0.5 * area


def overlap_area(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return width * height


def _heads(heading: list[float], table: list[float]) -> bool:
    """``heading`` sits just above ``table`` and overlaps it sideways."""
    gap = table[1] - heading[3]
    sideways = min(heading[2], table[2]) - max(heading[0], table[0])
    return -PAGE_TOLERANCE <= gap <= HEADING_GAP and sideways > 0


def _bbox(item: dict[str, Any]) -> list[float] | None:
    raw = item.get("bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        left, top, right, bottom = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    top, bottom = sorted((top, bottom))
    left, right = sorted((left, right))
    return [left, top, right, bottom]
