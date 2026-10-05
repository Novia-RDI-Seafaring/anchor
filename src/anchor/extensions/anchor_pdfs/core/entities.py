"""What a document is *about*: the entities named in its gold regions.

An agent's picture of the corpus comes from ``list_documents``, which returns
slug, title, page count and region count. None of that says what a document
covers. So a four-page leaflet describing thirteen pump models reads as one
document called "Alfa Laval LKH", and an agent that checks the smallest model
can reasonably conclude it is "the only pump in the corpus" -- as one did.

The extraction already knows better. Gold regions carry an ``entities`` list,
and that leaflet names all thirteen sizes. The knowledge was there and the
read surface offered no way to ask for it. This is the way to ask.

Deliberately no summarising here. A ranked top-N "covers" preview would have
to break ties between LKH-10 and a single letter from a pump-code legend,
both named four times, and any rule invented for that is a guess that
misleads exactly the way the current silence does. Callers get every entity
with its frequency and pages and can judge for themselves.
"""

from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore


async def list_entities(store: DocStore, slug: str) -> dict[str, Any]:
    """Every entity named in a document's gold regions, with where it appears.

    Returns ``{slug, entity_count, entities: [{name, count, pages, region_ids}]}``
    sorted by frequency, then by name so the order is stable. A document with
    no gold layer reports zero entities rather than failing: silver-only is a
    normal state, not an error.
    """
    regions = await store.get_regions(slug)
    pages = regions.get("pages") or {}

    found: dict[str, dict[str, Any]] = {}
    for page, items in sorted(pages.items(), key=lambda kv: _page_key(kv[0])):
        for region in items or []:
            if not isinstance(region, dict):
                continue
            for name in region.get("entities") or []:
                if not isinstance(name, str) or not name.strip():
                    continue
                entry = found.setdefault(
                    name, {"name": name, "count": 0, "pages": [], "region_ids": []}
                )
                entry["count"] += 1
                page_no = _page_key(page)
                if page_no not in entry["pages"]:
                    entry["pages"].append(page_no)
                rid = region.get("id")
                if isinstance(rid, str):
                    token = f"p{page_no}/{rid}"
                    if token not in entry["region_ids"]:
                        entry["region_ids"].append(token)

    entities = sorted(found.values(), key=lambda e: (-e["count"], e["name"]))
    return {"slug": slug, "entity_count": len(entities), "entities": entities}


def _page_key(page: Any) -> int:
    """Page numbers arrive as ints from the store and as strings from JSON."""
    try:
        return int(page)
    except (TypeError, ValueError):
        return 0
