"""Migrate stored bboxes from bottom-left to the canonical top-left (#281).

Before #281 every silver/gold bbox (and every canvas ``source_ref`` copied
from one) was in Docling's bottom-left PDF user space. The convention is now
top-left (OIP ``pdf-page-bbox``). This module rewrites a project's stored
data once, idempotently:

- ``silver/<slug>/pages.meta.json`` gains ``bbox_origin: "top-left"`` (the
  stamp that marks a document migrated) and ``page_size`` per page;
- ``silver/<slug>/index.json`` outline / tables / figures bboxes and table
  cells, and ``pages/<n>.candidates.json`` bboxes + cells, are flipped;
- ``gold/<slug>/pages/<n>.regions.json`` bboxes, ``approx_bbox`` and cells
  are flipped;
- canvas nodes / edges whose ``source_ref`` (or spec ``rows[].source_ref``)
  points into a migrated document are flipped and stamped
  ``coord_origin: "top-left"``.

Page heights come from the PDF itself (``PdfRenderer.page_sizes``), falling
back to a ``page_size`` already recorded in pages.meta. A document whose
heights cannot be determined is skipped and reported, never half-flipped.

Pure orchestration over ports; no I/O of its own.
"""
from __future__ import annotations

import json
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer
from anchor.extensions.anchor_pdfs.core.silver import BBOX_ORIGIN, flip_bbox_y, union_bbox

_BBOX_KEYS = ("bbox", "approx_bbox", "approximate_bbox")


def needs_migration(pages_meta: dict[str, Any] | None) -> bool:
    """A document is legacy until its pages.meta carries the top-left stamp."""
    return not (isinstance(pages_meta, dict) and pages_meta.get("bbox_origin") == BBOX_ORIGIN)


def _flip_obj(obj: dict[str, Any], height: float) -> dict[str, Any]:
    """Flip every bbox-like key on ``obj`` and on its ``cells``."""
    out = dict(obj)
    for key in _BBOX_KEYS:
        value = out.get(key)
        if isinstance(value, list) and len(value) == 4:
            out[key] = flip_bbox_y([float(v) for v in value], height)
    cells = out.get("cells")
    if isinstance(cells, list):
        out["cells"] = [
            _flip_obj(c, height) if isinstance(c, dict) else c for c in cells
        ]
    return out


def flip_regions(regions: list[dict[str, Any]], height: float) -> list[dict[str, Any]]:
    return [_flip_obj(r, height) if isinstance(r, dict) else r for r in regions]


def flip_candidates(candidates: list[dict[str, Any]], height: float) -> list[dict[str, Any]]:
    return flip_regions(candidates, height)


def flip_index(index: dict[str, Any], heights: dict[int, float]) -> dict[str, Any]:
    out = dict(index)
    for key in ("outline", "tables", "figures"):
        entries = out.get(key)
        if not isinstance(entries, list):
            continue
        flipped = []
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("page"), int) and entry["page"] in heights:
                flipped.append(_flip_obj(entry, heights[entry["page"]]))
            else:
                flipped.append(entry)
        out[key] = flipped
    return out


def flip_pages_meta(
    meta: dict[str, Any], sizes: dict[int, tuple[float, float]]
) -> dict[str, Any]:
    out = dict(meta)
    pages = dict(meta.get("pages") or {})
    for key, entry in list(pages.items()):
        if not isinstance(entry, dict):
            continue
        page = int(key)
        size = sizes.get(page)
        new_entry = dict(entry)
        if size is not None:
            new_entry["page_size"] = [size[0], size[1]]
            union = entry.get("bbox_union")
            if isinstance(union, list) and len(union) == 4:
                new_entry["bbox_union"] = union_bbox([flip_bbox_y(union, size[1])])
        pages[key] = new_entry
    out["pages"] = pages
    out["bbox_origin"] = BBOX_ORIGIN
    return out


def flip_source_ref(ref: dict[str, Any], height: float) -> dict[str, Any]:
    """Flip one canvas ``source_ref`` and stamp it; already-stamped refs pass."""
    if ref.get("coord_origin") == BBOX_ORIGIN:
        return ref
    out = _flip_obj(ref, height)
    detail = out.get("detail")
    if isinstance(detail, dict) and isinstance(detail.get("cell_bbox"), list):
        detail = dict(detail)
        detail["cell_bbox"] = flip_bbox_y(detail["cell_bbox"], height)
        out["detail"] = detail
    out["coord_origin"] = BBOX_ORIGIN
    return out


async def _page_sizes_for(
    store: DocStore, renderer: PdfRenderer | None, slug: str, meta: dict[str, Any] | None
) -> dict[int, tuple[float, float]]:
    sizes: dict[int, tuple[float, float]] = {}
    if renderer is not None:
        path = await store.get_raw_pdf_path(slug)
        if path is not None and not str(path).startswith("memory://"):
            try:
                sizes = dict(await renderer.page_sizes(path))
            except Exception:  # noqa: BLE001 - fall back to recorded sizes below
                sizes = {}
    if not sizes and isinstance(meta, dict):
        for key, entry in (meta.get("pages") or {}).items():
            ps = entry.get("page_size") if isinstance(entry, dict) else None
            if isinstance(ps, list) and len(ps) == 2:
                sizes[int(key)] = (float(ps[0]), float(ps[1]))
    return sizes


async def migrate_document(
    store: DocStore, renderer: PdfRenderer | None, slug: str
) -> dict[str, Any]:
    """Flip one document's silver + gold to top-left. Idempotent."""
    meta = await store.get_pages_meta(slug)
    if not needs_migration(meta):
        return {"slug": slug, "status": "already_top_left"}
    sizes = await _page_sizes_for(store, renderer, slug, meta)
    if not sizes:
        return {"slug": slug, "status": "skipped", "reason": "page sizes unavailable"}
    heights = {p: s[1] for p, s in sizes.items()}

    index = await store.get_index(slug)
    if isinstance(index, dict):
        await store.write_silver_artifact(
            slug, "index.json", json.dumps(flip_index(index, heights), indent=2)
        )
    pages_done = 0
    for page in sorted(heights):
        candidates = await store.get_page_candidates(slug, page)
        if candidates is not None:
            await store.write_silver_artifact(
                slug,
                f"pages/{page}.candidates.json",
                json.dumps(flip_candidates(candidates, heights[page])),
            )
    gold = await store.get_regions(slug)
    for page, regions in (gold.get("pages") or {}).items():
        p = int(page)
        if p in heights and isinstance(regions, list):
            await store.write_gold_region_file(slug, p, flip_regions(regions, heights[p]))
            pages_done += 1
    # The stamp is written last: a crash before this point leaves the doc
    # detectably legacy (and the flip is re-run wholesale; it is not
    # idempotent per file, so partial state is never left stamped).
    base_meta = meta if isinstance(meta, dict) else {"pages": {}}
    await store.write_silver_artifact(
        slug, "pages.meta.json", json.dumps(flip_pages_meta(base_meta, sizes), indent=2)
    )
    return {"slug": slug, "status": "migrated", "gold_pages": pages_done, "pages": len(heights)}


def _heights_from_meta(meta: dict[str, Any] | None) -> dict[int, float]:
    out: dict[int, float] = {}
    if not isinstance(meta, dict):
        return out
    for key, entry in (meta.get("pages") or {}).items():
        ps = entry.get("page_size") if isinstance(entry, dict) else None
        if isinstance(ps, list) and len(ps) == 2:
            out[int(key)] = float(ps[1])
    return out


async def migrate_canvases(store: DocStore, workspace: Any) -> dict[str, Any]:
    """Flip unstamped canvas source_refs that point into migrated documents.

    ``workspace`` is the WorkspaceService (``list_workspaces`` / ``get_state``
    / ``update_node`` / ``update_edge``). Refs into unknown documents, or
    documents that are still legacy, are left alone."""
    heights_by_slug: dict[str, dict[int, float]] = {}

    async def heights_for(doc_slug: str | None) -> dict[int, float]:
        if not doc_slug:
            return {}
        if doc_slug not in heights_by_slug:
            meta = await store.get_pages_meta(doc_slug)
            heights_by_slug[doc_slug] = (
                _heights_from_meta(meta) if not needs_migration(meta) else {}
            )
        return heights_by_slug[doc_slug]

    async def convert(ref: Any, fallback_slug: str | None) -> dict[str, Any] | None:
        if not isinstance(ref, dict) or ref.get("coord_origin") == BBOX_ORIGIN:
            return None
        page = ref.get("page")
        if not isinstance(page, int):
            return None
        heights = await heights_for(ref.get("slug") or fallback_slug)
        if page not in heights:
            return None
        return flip_source_ref(ref, heights[page])

    nodes_updated = edges_updated = 0
    for ws in await workspace.list_workspaces():
        ws_slug = ws.get("slug") if isinstance(ws, dict) else None
        if not ws_slug:
            continue
        state = await workspace.get_state(ws_slug)
        for node in state.get("nodes") or []:
            data = node.get("data") if isinstance(node, dict) else None
            if not isinstance(data, dict):
                continue
            patch: dict[str, Any] = {}
            doc_slug = data.get("source_doc_slug") or data.get("slug")
            new_ref = await convert(data.get("source_ref"), doc_slug)
            if new_ref is not None:
                patch["source_ref"] = new_ref
            rows = data.get("rows")
            if isinstance(rows, list):
                new_rows = []
                changed = False
                for row in rows:
                    if isinstance(row, dict):
                        r = await convert(row.get("source_ref"), doc_slug)
                        if r is not None:
                            row = {**row, "source_ref": r}
                            changed = True
                    new_rows.append(row)
                if changed:
                    patch["rows"] = new_rows
            if patch:
                await workspace.update_node(ws_slug, node["id"], {"data": patch})
                nodes_updated += 1
        for edge in state.get("edges") or []:
            data = edge.get("data") if isinstance(edge, dict) else None
            if not isinstance(data, dict):
                continue
            target = next(
                (n for n in state.get("nodes") or [] if n.get("id") == edge.get("target")), None
            )
            tdata = (target or {}).get("data") or {}
            new_ref = await convert(data.get("source_ref"), tdata.get("slug"))
            if new_ref is not None:
                await workspace.update_edge(ws_slug, edge["id"], {"data": {"source_ref": new_ref}})
                edges_updated += 1
    return {"nodes_updated": nodes_updated, "edges_updated": edges_updated}


async def migrate_all(
    store: DocStore, renderer: PdfRenderer | None, workspace: Any | None = None
) -> dict[str, Any]:
    """Migrate every legacy document, then the canvases that cite them."""
    docs: list[dict[str, Any]] = []
    for doc in await store.list_documents():
        slug = doc.get("slug") if isinstance(doc, dict) else None
        if slug:
            docs.append(await migrate_document(store, renderer, slug))
    canvases = await migrate_canvases(store, workspace) if workspace is not None else {}
    migrated = [d["slug"] for d in docs if d.get("status") == "migrated"]
    skipped = [d for d in docs if d.get("status") == "skipped"]
    return {"documents": docs, "migrated": migrated, "skipped": skipped, "canvases": canvases}
