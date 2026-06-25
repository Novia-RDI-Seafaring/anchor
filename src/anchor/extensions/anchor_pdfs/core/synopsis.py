"""Compose an entity-scoped synopsis from gold-layer document data.

Given a document slug and an entity name (e.g. "LKH-5"), produce a
structured ``SynopsisData`` of facts filtered to that entity, plus
references to any region crops that illustrate it. The result is the
agent-facing interchange format — renderers in ``infra/synopsis_renderers``
turn it into PDF, Marp markdown, or anything else.

Core stays pure: this file does string parsing on already-fetched page
markdown and gold-region metadata. It does **not** open files, talk
HTTP, or render any output format itself — those are all infra concerns
behind ``SynopsisRenderer`` ports.

The filter is conservative — it keeps every row that:
- Names the entity literally (``"LKH-5"`` in the row label or value), or
- Uses a model-range syntax that includes the entity
  (``"LKH-5 - 70"``, ``"LKH-5 to -60"``), or
- Is a generic property row whose label is in a documented allow-list
  (materials, motor speeds, flush parameters).

This works well for vendor leaflets shaped like the Alfa Laval LKH
datasheet. Other documents (manuals, P&IDs) need different filter
strategies; the seam is the ``EntityFilter`` callable.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore

# ── Result shapes ──────────────────────────────────────────────────────────


@dataclass
class SourceRef:
    """Page (+ optional bbox / region_id) the row was extracted from."""

    page: int
    region_id: str | None = None
    bbox: list[float] | None = None


@dataclass
class SynopsisRow:
    label: str
    value: str
    source_ref: SourceRef | None = None


@dataclass
class SynopsisSection:
    title: str
    rows: list[SynopsisRow] = field(default_factory=list)
    body: str | None = None
    source_ref: SourceRef | None = None


@dataclass
class SynopsisCrop:
    """A region image relevant to the entity (typically the performance chart)."""

    rel_path: str
    title: str
    description: str | None
    source_ref: SourceRef


@dataclass
class SynopsisData:
    slug: str
    entity: str
    title: str
    sections: list[SynopsisSection] = field(default_factory=list)
    crops: list[SynopsisCrop] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    operating_conditions: list[str] = field(default_factory=list)
    derived_facts: dict[str, str] = field(default_factory=dict)


# ── Filter ─────────────────────────────────────────────────────────────────


_GENERIC_KEEP = {
    "product wetted steel parts:", "other steel parts:",
    "inside surface finish:", "product wetted elastomers:",
    "rotary seal face:", "stationary seal face:",
    "temperature range:", "flush media:",
    "flush housing sterilization (pump not in operation):",
    "water pressure inlet:", "water consumption:",
    "50hz:", "60hz:",
    "2 poles: 0.75 - 45 kw:", "2 poles: 55 - 110 kw:",
    "4 poles: 0.75 - 75 kw:",
}

_TABLE_HEADER_DROP = {
    "max inlet pressure", "motor sizes", "temperature",
    "flushed shaft seal", "double mechanical shaft seal",
    "connections for flushed and double mechanical shaft seal",
    "materials", "min/max motor speed",
}


# Operating-point matcher ("50 Hz ... 2900 rpm"). All quantifiers are bounded
# so the pattern is linear-time on any input (no polynomial ReDoS): the digit
# runs are capped, and the gap between the Hz and rpm tokens is a length-capped
# negated class with no nested repetition that could match the same text two
# ways. Compiled once at import.
_OPERATING_POINT_RE = re.compile(r"(\d{1,6}\s{0,4}Hz[^.,;]{0,80}?\d{1,6}\s{0,4}rpm)")


def _entity_number(entity: str) -> int | None:
    m = re.search(r"-?(\d+)", entity)
    return int(m.group(1)) if m else None


def default_filter(text: str, entity: str) -> list[SynopsisRow]:
    """Default filter for vendor-leaflet markdown tables.

    Keeps rows that (a) literally mention the entity, (b) use a model
    range that includes the entity's number, or (c) are generic property
    rows in ``_GENERIC_KEEP``."""
    out: list[SynopsisRow] = []
    n = _entity_number(entity)
    ent_lower = entity.lower()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|") if c.strip()]
        if len(cells) < 2 or set("".join(cells)) <= {"-", " "}:
            continue
        label, *rest = cells
        value = " · ".join(rest)
        L = label.lower()
        if L in _TABLE_HEADER_DROP:
            continue
        keep = False
        if ent_lower in L:
            keep = True
        elif n is not None:
            if (m := re.match(r"lkh-?(\d+)\s*-\s*-?(\d+)", L)):
                lo, hi = int(m.group(1)), int(m.group(2))
                if lo <= n <= hi:
                    keep = True
        if not keep and L in _GENERIC_KEEP:
            keep = True
        if keep:
            out.append(SynopsisRow(label=label, value=value))
    return out


EntityFilter = Callable[[str, str], list[SynopsisRow]]


# ── Composer ───────────────────────────────────────────────────────────────


async def compose_synopsis(
    *,
    store: DocStore,
    slug: str,
    entity: str,
    filter_rows: EntityFilter = default_filter,
) -> SynopsisData:
    """Build a ``SynopsisData`` for ``entity`` from gold-layer data.

    Pulls page-text + gold regions + gold map via the ``DocStore`` port,
    filters rows down to those that apply to ``entity``, and picks any
    "chart" or "diagram" region as an illustrative crop.

    Caller decides what to do with the result — render to PDF, dump as
    JSON, post to a canvas, etc. Renderers live in
    ``anchor.extensions.anchor_pdfs.infra.synopsis_renderers``.
    """
    gold = await store.get_gold_map(slug)
    if gold is None:
        raise SynopsisError(f"no gold data for slug {slug!r}")

    title = (gold.get("document") or {}).get("title") or slug

    sections: list[SynopsisSection] = []
    page_count = (gold.get("document") or {}).get("page_count") or len(gold.get("pages_meta", {})) or 4
    for page in range(1, int(page_count) + 1):
        text = await store.get_page_text(slug, page)
        if not text:
            continue
        rows = filter_rows(text, entity)
        for r in rows:
            r.source_ref = SourceRef(page=page)
        if rows:
            sections.append(SynopsisSection(
                title=_page_section_title(text, page),
                rows=rows,
                source_ref=SourceRef(page=page),
            ))

    crops: list[SynopsisCrop] = []
    pages = gold.get("pages", {})
    for page_str, regions in (pages.items() if isinstance(pages, dict) else []):
        try:
            page_num = int(page_str)
        except (TypeError, ValueError):
            continue
        for r in regions:
            kind = r.get("kind", "")
            title_r = r.get("title", "")
            if kind in ("chart", "diagram", "graph"):
                rel = (r.get("crops") or {}).get("png") or (r.get("crops") or {}).get("svg")
                if not rel:
                    continue
                crops.append(SynopsisCrop(
                    rel_path=rel,
                    title=title_r or kind,
                    description=r.get("description"),
                    source_ref=SourceRef(
                        page=page_num,
                        region_id=r.get("id"),
                        bbox=r.get("bbox"),
                    ),
                ))

    operating_conditions, caveats, derived = _extract_extras(slug, entity, gold)

    return SynopsisData(
        slug=slug,
        entity=entity,
        title=f"{title} — {entity}",
        sections=sections,
        crops=crops,
        caveats=caveats,
        operating_conditions=operating_conditions,
        derived_facts=derived,
    )


def _page_section_title(text: str, page: int) -> str:
    for line in text.splitlines():
        L = line.strip()
        if L.startswith("## "):
            return L[3:].strip().title()
        if L.startswith("### "):
            return L[4:].strip().title()
    return f"Page {page}"


def _extract_extras(slug: str, entity: str, gold: dict[str, Any]) -> tuple[list[str], list[str], dict[str, str]]:
    """Best-effort: pull frequency / curve-letter / caveats from chart-region
    descriptions so callers don't have to re-derive them. Returns
    (operating_conditions, caveats, derived_facts).
    """
    operating: list[str] = []
    caveats: list[str] = []
    derived: dict[str, str] = {}
    pages = gold.get("pages", {})
    n = _entity_number(entity)
    for _page_key, regions in (pages.items() if isinstance(pages, dict) else []):
        for r in regions:
            desc = r.get("description") or ""
            if "Hz" in desc and "rpm" in desc and not operating:
                # Bounded quantifiers only: the digit runs and the gap between
                # the Hz and rpm tokens are length-capped so the match cannot
                # backtrack polynomially on adversarial input (e.g. "0Hz" with
                # a long run of zeros). Still captures normal operating-point
                # strings like "50 Hz -> 2900 rpm".
                m = re.search(_OPERATING_POINT_RE, desc)
                if m:
                    operating.append(m.group(1).strip())
            entities = r.get("entities") or []
            if n is not None and entity in entities and r.get("kind") == "chart":
                derived.setdefault("on_chart", f"entity {entity} appears on chart region {r.get('id')!r}")
    if any(s.title.lower().startswith("flow chart") for s in []):  # placeholder; full curve-letter lives in renderer
        pass
    return operating, caveats, derived


# ── Errors ─────────────────────────────────────────────────────────────────


class SynopsisError(ValueError):
    """Raised when a synopsis cannot be composed (unknown slug, no gold)."""


__all__ = [
    "SourceRef", "SynopsisRow", "SynopsisSection", "SynopsisCrop",
    "SynopsisData", "EntityFilter", "default_filter",
    "compose_synopsis", "SynopsisError",
]
