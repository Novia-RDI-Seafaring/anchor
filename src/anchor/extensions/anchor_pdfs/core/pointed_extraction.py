"""Pointed extraction (anchor#132).

Pull a chosen set of gold regions / entities out of a document into a
caller-defined JSON shape, with every filled leaf grounded to its source
cell (page / region_id / bbox / quote).

Design
======
This is the deterministic core of pointed extraction:

1. **Selection** (``resolve_selection``) turns a ``select`` request
   (``regions`` ids, ``pages``, and/or ``entity``) into the concrete set of
   gold regions to read from. ``entity`` reuses the ``compose_synopsis``
   scoping so an entity-scoped extraction stays consistent with the rest of
   the synopsis surface.

2. **Filling** (``fill_shape``) walks the caller's ``shape`` (by-example or a
   JSON Schema) leaf by leaf. Each leaf maps to a *label* (the last JSON
   Pointer segment, humanised). The label is matched against the key cells of
   the selected regions' ``cells`` tables; the value cell on the same row is
   the answer. The match is deterministic — no model call — and every filled
   leaf carries a ``source_ref`` ``{page, region_id, bbox, quote}`` keyed by
   its JSON Pointer.

3. **unfilled** lists every shape leaf the source did not cover. Values are
   never invented: a leaf is either filled from a real cell (with provenance)
   or reported as unfilled.

The cell-matching mechanics (normalise text, find the value cell on the same
table row as the label cell) mirror ``value_provenance.py`` so a pointed
extraction is grounded the same way value-level grounding (#145) is.

Stays pure core: only the ``DocStore`` port is touched; no I/O library, no
HTTP, no model. Fuzzy LLM-assisted mapping (for labels that do not match a
cell key literally) is a documented follow-up — the seam is the
``unfilled`` list, which a later pass can try to fill.
"""
from __future__ import annotations

import re
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.synopsis import (
    EntityFilter,
    compose_synopsis,
    default_filter,
)

_LEAF_TYPES = {"string", "number", "quantity", "bool", "boolean", "int", "integer", "float"}


class PointedExtractionError(ValueError):
    """Raised when a pointed extraction cannot run (unknown slug, no gold)."""


# ── Selection ──────────────────────────────────────────────────────────────


def _parse_region_token(token: str) -> tuple[int | None, str]:
    """Parse a ``select.regions`` token into ``(page, region_id)``.

    Accepts ``"p2/r4"`` (page 2, region r4), ``"2/r4"``, or a bare ``"r4"``
    (region id only, any page). Returns ``(None, region_id)`` when no page is
    encoded.
    """
    token = token.strip()
    if "/" in token:
        page_part, region_part = token.split("/", 1)
        page_part = page_part.lstrip("pP")
        try:
            page = int(page_part)
        except ValueError:
            page = None
        return page, region_part.strip()
    return None, token


async def resolve_selection(
    *,
    store: DocStore,
    slug: str,
    select: dict[str, Any] | None,
    filter_rows: EntityFilter = default_filter,
) -> list[dict[str, Any]]:
    """Resolve a ``select`` request to a de-duplicated list of gold regions.

    Each returned region dict is annotated with a resolved ``page`` (so
    downstream provenance always has a page even when the stored region omits
    it). Regions are unioned across the ``regions`` / ``pages`` / ``entity``
    selectors; an empty / absent ``select`` selects every gold region.
    """
    gold = await store.get_gold_map(slug)
    if gold is None:
        raise PointedExtractionError(f"no gold data for slug {slug!r}")

    pages_map = gold.get("pages") if isinstance(gold.get("pages"), dict) else {}
    # Flatten gold into (page, region) pairs once; every selector filters this.
    all_regions: list[tuple[int, dict[str, Any]]] = []
    for page_key, regions in pages_map.items():
        try:
            page = int(page_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(regions, list):
            continue
        for r in regions:
            if isinstance(r, dict):
                all_regions.append((page, r))

    select = select or {}
    region_tokens = select.get("regions") or []
    pages = select.get("pages") or []
    entity = select.get("entity")

    no_selector = not region_tokens and not pages and not entity

    # Build a normalised page set + region-id set from the explicit selectors.
    want_pages: set[int] = {int(p) for p in pages if isinstance(p, (int, float))}
    want_region_ids: set[str] = set()
    want_page_region: set[tuple[int, str]] = set()
    for token in region_tokens:
        if not isinstance(token, str):
            continue
        page, region_id = _parse_region_token(token)
        if page is None:
            want_region_ids.add(region_id)
        else:
            want_page_region.add((page, region_id))

    # Entity scoping reuses compose_synopsis: the pages it surfaces for the
    # entity become an additional page filter, and any region whose cells /
    # entities literally name the entity is selected directly.
    entity_pages: set[int] = set()
    if entity:
        synopsis = await compose_synopsis(
            store=store, slug=slug, entity=entity, filter_rows=filter_rows,
        )
        for section in synopsis.sections:
            if section.source_ref is not None:
                entity_pages.add(section.source_ref.page)
        for crop in synopsis.crops:
            entity_pages.add(crop.source_ref.page)

    selected: list[dict[str, Any]] = []
    seen: set[tuple[int, str | None]] = set()

    def _take(page: int, region: dict[str, Any]) -> None:
        key = (page, region.get("id"))
        if key in seen:
            return
        seen.add(key)
        annotated = dict(region)
        annotated.setdefault("page", page)
        selected.append(annotated)

    for page, region in all_regions:
        rid = region.get("id")
        keep = no_selector
        if not keep and rid in want_region_ids:
            keep = True
        if not keep and rid is not None and (page, rid) in want_page_region:
            keep = True
        if not keep and page in want_pages:
            keep = True
        if not keep and entity:
            if page in entity_pages:
                keep = True
            elif _region_names_entity(region, entity):
                keep = True
        if keep:
            _take(page, region)

    return selected


def _region_names_entity(region: dict[str, Any], entity: str) -> bool:
    ent = entity.strip().lower()
    if not ent:
        return False
    entities = region.get("entities")
    if isinstance(entities, list) and any(
        isinstance(e, str) and e.strip().lower() == ent for e in entities
    ):
        return True
    for field in ("title", "description"):
        value = region.get(field)
        if isinstance(value, str) and ent in value.lower():
            return True
    cells = region.get("cells")
    if isinstance(cells, list):
        for cell in cells:
            if isinstance(cell, dict) and ent in _norm(cell.get("text")):
                return True
    return False


# ── Shape walking ──────────────────────────────────────────────────────────


def normalise_shape(shape: Any) -> Any:
    """Reduce a ``shape`` (by-example or JSON Schema) to a by-example tree.

    A by-example shape is returned untouched. A JSON Schema (a dict with a
    ``type``/``properties``/``items`` vocabulary) is converted to the
    equivalent by-example skeleton so the rest of the pipeline only ever sees
    one shape language.
    """
    if _looks_like_json_schema(shape):
        return _schema_to_example(shape)
    return shape


def _looks_like_json_schema(shape: Any) -> bool:
    if not isinstance(shape, dict):
        return False
    if "properties" in shape and isinstance(shape.get("properties"), dict):
        return True
    t = shape.get("type")
    if isinstance(t, str) and t in {"object", "array", "string", "number", "integer", "boolean"}:
        # A leaf written as {"type": "string"} or a schema container.
        return True
    return False


def _schema_to_example(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        return {k: _schema_to_example(v) for k, v in props.items()}
    if t == "array" or "items" in schema:
        items = schema.get("items")
        return [_schema_to_example(items)] if items is not None else []
    # Map JSON Schema scalar types onto the by-example leaf vocabulary. A
    # ``format: quantity`` (or an explicit quantity hint) maps to "quantity".
    if schema.get("format") == "quantity":
        return "quantity"
    return {
        "string": "string",
        "number": "number",
        "integer": "number",
        "boolean": "bool",
    }.get(t if isinstance(t, str) else "", "string")


def _is_leaf(node: Any) -> bool:
    return isinstance(node, str) and node.strip().lower() in _LEAF_TYPES


# ── Filling ────────────────────────────────────────────────────────────────


def fill_shape(
    shape: Any,
    regions: list[dict[str, Any]],
    *,
    slug: str,
) -> tuple[Any, dict[str, dict[str, Any]], list[str]]:
    """Fill ``shape`` from the selected ``regions`` deterministically.

    Returns ``(data, provenance, unfilled)``:

    - ``data``  matches the shape; filled leaves carry their matched value,
      unmatched leaves are ``None`` (scalars) or ``[]`` (arrays).
    - ``provenance`` maps each filled leaf's JSON Pointer to its
      ``source_ref`` ``{page, region_id, bbox, quote}`` (slug included).
    - ``unfilled`` lists the JSON Pointer of every leaf (or empty array) the
      source did not cover.

    A value is only ever taken from a real gold cell; nothing is guessed.
    """
    shape = normalise_shape(shape)
    provenance: dict[str, dict[str, Any]] = {}
    unfilled: list[str] = []
    index = _CellIndex(regions, slug=slug)
    data = _fill_node(shape, "", index, provenance, unfilled, label_hint=None)
    return data, provenance, unfilled


def _fill_node(
    node: Any,
    pointer: str,
    index: _CellIndex,
    provenance: dict[str, dict[str, Any]],
    unfilled: list[str],
    *,
    label_hint: str | None,
) -> Any:
    if _is_leaf(node):
        label = label_hint or _label_from_pointer(pointer)
        match = index.lookup(label)
        if match is None:
            unfilled.append(pointer or "/")
            return None
        value, source_ref = match
        provenance[pointer or "/"] = source_ref
        return _coerce_leaf(value, node)

    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, child in node.items():
            child_pointer = f"{pointer}/{_escape_token(key)}"
            out[key] = _fill_node(
                child, child_pointer, index, provenance, unfilled, label_hint=key,
            )
        return out

    if isinstance(node, list):
        # Arrays of objects: we have no deterministic row-grouping signal in
        # the general case, so report the array pointer as unfilled rather
        # than fabricate rows. (Row-aware array filling is a documented
        # follow-up — see module docstring.)
        unfilled.append(pointer or "/")
        return []

    # Unknown leaf vocabulary: treat as a string leaf.
    label = label_hint or _label_from_pointer(pointer)
    match = index.lookup(label)
    if match is None:
        unfilled.append(pointer or "/")
        return None
    value, source_ref = match
    provenance[pointer or "/"] = source_ref
    return value


def _coerce_leaf(value: str, leaf_type: Any) -> Any:
    t = leaf_type.strip().lower() if isinstance(leaf_type, str) else "string"
    raw = value.strip()
    if t in {"number", "int", "integer", "float"}:
        num = _parse_number(raw)
        return num if num is not None else raw
    if t in {"bool", "boolean"}:
        low = raw.lower()
        if low in {"true", "yes", "y", "1"}:
            return True
        if low in {"false", "no", "n", "0"}:
            return False
        return raw
    # "string" and "quantity" both keep the verbatim cell text (a quantity
    # like "600 kPa" must keep its unit).
    return raw


def _parse_number(text: str) -> float | int | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", text)
    if not m:
        return None
    token = m.group(0).replace(",", ".")
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return None


# ── Cell index ─────────────────────────────────────────────────────────────


class _CellIndex:
    """Label -> (value, source_ref) lookup over the selected regions' cells.

    Builds, once, the set of (key cell, value cell) pairs from every region's
    ``cells`` table: for each row, the first cell is treated as the key and a
    following cell on the same row as the value. ``lookup`` then matches a
    humanised shape label against the normalised key text.
    """

    def __init__(self, regions: list[dict[str, Any]], *, slug: str) -> None:
        self._slug = slug
        # label_norm -> list of candidate (value, source_ref)
        self._by_label: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for region in regions:
            self._index_region(region)

    def _index_region(self, region: dict[str, Any]) -> None:
        cells = region.get("cells")
        if not isinstance(cells, list):
            return
        page = region.get("page")
        region_id = region.get("id")
        rows: dict[int, list[dict[str, Any]]] = {}
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            row_no = cell.get("row")
            if not isinstance(row_no, int):
                continue
            rows.setdefault(row_no, []).append(cell)
        for row_cells in rows.values():
            ordered = sorted(
                row_cells,
                key=lambda c: c.get("col") if isinstance(c.get("col"), int) else 0,
            )
            if len(ordered) < 2:
                continue
            key_cell = ordered[0]
            key_norm = _norm(key_cell.get("text"))
            if not key_norm:
                continue
            for value_cell in ordered[1:]:
                value_text = value_cell.get("text")
                if not isinstance(value_text, str) or not value_text.strip():
                    continue
                source_ref: dict[str, Any] = {
                    "slug": self._slug,
                    "quote": value_text.strip(),
                }
                if isinstance(page, int):
                    source_ref["page"] = page
                if region_id is not None:
                    source_ref["region_id"] = region_id
                bbox = _clean_bbox(value_cell.get("bbox"))
                if bbox:
                    source_ref["bbox"] = bbox
                self._by_label.setdefault(key_norm, []).append(
                    (value_text.strip(), source_ref)
                )
                # Only the first value cell on a row is the canonical answer.
                break

    def lookup(self, label: str) -> tuple[str, dict[str, Any]] | None:
        label_norm = _norm(label)
        if not label_norm:
            return None
        candidates = self._by_label.get(label_norm)
        if candidates is None:
            # Tolerate trailing punctuation on the stored key ("model:" etc.).
            for stored_key, stored in self._by_label.items():
                if stored_key.rstrip(":").strip() == label_norm:
                    candidates = stored
                    break
        if not candidates:
            return None
        # Deterministic: a label that resolves to exactly one value is filled;
        # an ambiguous label (the same key in several selected regions with
        # differing values) is left unfilled rather than guessed.
        first_value = candidates[0][0]
        if all(v == first_value for v, _ in candidates):
            return candidates[0]
        return None


# ── Text + bbox helpers (mirror value_provenance) ──────────────────────────


def _label_from_pointer(pointer: str) -> str:
    if not pointer:
        return ""
    last = pointer.rsplit("/", 1)[-1]
    last = _unescape_token(last)
    return last.replace("_", " ").replace("-", " ")


def _escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _norm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _clean_bbox(bbox: Any) -> list[float]:
    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
        return [float(v) for v in bbox]
    return []


# ── Top-level orchestration ────────────────────────────────────────────────


async def extract_pointed(
    *,
    store: DocStore,
    slug: str,
    select: dict[str, Any] | None,
    shape: Any,
    filter_rows: EntityFilter = default_filter,
) -> dict[str, Any]:
    """Run a pointed extraction end to end.

    Resolves ``select`` to gold regions, fills ``shape`` from their cells, and
    returns the issue#132 response envelope::

        {doc_slug, data, provenance, unfilled}

    Every filled leaf in ``data`` has a ``provenance`` entry; every leaf the
    source did not cover is listed in ``unfilled``. Raises
    ``PointedExtractionError`` for an unknown slug / missing gold layer.
    """
    regions = await resolve_selection(
        store=store, slug=slug, select=select, filter_rows=filter_rows,
    )
    data, provenance, unfilled = fill_shape(shape, regions, slug=slug)
    return {
        "doc_slug": slug,
        "data": data,
        "provenance": provenance,
        "unfilled": unfilled,
    }


__all__ = [
    "PointedExtractionError",
    "resolve_selection",
    "normalise_shape",
    "fill_shape",
    "extract_pointed",
]
