"""Place each row's reference where its value is printed, on create and update."""
from dataclasses import dataclass, field
from typing import Any

from anchor.core.workspace.merge import deep_merge
from anchor.extensions.anchor_pdfs.core.cell_locate import locate_cell
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content
from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.core.value_provenance import resolve_spec_row_sources


@dataclass(frozen=True)
class PdfNodeDataPreparer:
    store: DocStore
    #: Reads a page's text and finds words on it, to place a ref's quotes.
    #: Without one, quotes are kept as written. Not part of the identity: the
    #: same store bound again is the same preparer.
    renderer: Any = field(default=None, compare=False)

    async def __call__(self, data: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        """Point each row's reference at where its value is printed.

        Quotes get their boxes, a quoted row its cell, and a row whose key and
        value form one printed pair in the cited table gets that cell. Nothing
        here judges a row: whether a reference is right is the reader's call.
        """
        intended = deep_merge(previous, data) if previous is not None else data
        # One write reads one version of each cited document, across passes.
        store = self.store
        for slug in _cited_slugs(intended):
            store = store.snapshot(slug)
        intended, quoted = await self._place_quotes(intended, store)
        intended, celled = await self._cells_from_quotes(intended, store)
        _, paired = await resolve_spec_row_sources(intended, store)
        intended, located = await self._locate_cells(intended, store, skip=set(paired))
        resolved, _ = await resolve_spec_row_sources(intended, store)
        if not isinstance(resolved.get("rows"), list):
            return data
        if resolved == intended and not located and not (quoted or celled):
            return data
        # Keep the caller's patch, including null deletion markers. Passing
        # the full merged state back as a patch would resurrect removed keys.
        return {**data, "rows": resolved["rows"]}

    async def _place_quotes(
        self, intended: dict[str, Any], store: DocStore,
    ) -> tuple[dict[str, Any], bool]:
        """Give each row's quotes their boxes, where the words are printed.

        Only quotes without boxes are placed, so a saved quote is not searched
        again on every later edit. A quote that cannot be placed keeps its
        ``problem`` and what the text there says, for the writer to fix.
        """
        rows = intended.get("rows")
        if self.renderer is None or not isinstance(rows, list):
            return intended, False
        out, quoted = list(rows), False
        for i, row in enumerate(rows):
            ref = row.get("source_ref") if isinstance(row, dict) else None
            quotes = ref.get("quotes") if isinstance(ref, dict) else None
            if not isinstance(quotes, list) or not isinstance(ref.get("slug"), str):
                continue
            if all(isinstance(m, dict) and (m.get("boxes") or m.get("problem")) for m in quotes):
                continue
            try:
                resolved = await resolve_source_ref(store, ref["slug"], ref, renderer=self.renderer)
            except Exception:  # noqa: BLE001 -- placing quotes never fails a write
                continue
            if resolved is not None and isinstance(resolved.get("quotes"), list):
                out[i] = {**row, "source_ref": {**ref, "quotes": resolved["quotes"]}}
                quoted = True
        return ({**intended, "rows": out} if quoted else intended), quoted

    async def _cells_from_quotes(
        self, intended: dict[str, Any], store: DocStore,
    ) -> tuple[dict[str, Any], bool]:
        """Cite the cell a row's quoted words are printed in.

        A row that cites a whole table but quotes words in it lights the whole
        table, when the line it means is right there: the cell holding the
        quote is where the value is, so the ref names it.
        """
        rows = intended.get("rows")
        if not isinstance(rows, list):
            return intended, False
        out, changed = list(rows), False
        for i, row in enumerate(rows):
            ref = row.get("source_ref") if isinstance(row, dict) else None
            if not isinstance(ref, dict) or ref.get("cell") or ref.get("item_id"):
                continue
            slug, region_id, page = ref.get("slug"), ref.get("region_id"), ref.get("page")
            boxes = [
                box for q in (ref.get("quotes") or []) if isinstance(q, dict)
                and q.get("page", page) == page for box in (q.get("boxes") or [])
            ]
            if not (isinstance(slug, str) and isinstance(region_id, str) and boxes):
                continue
            try:
                content = await get_region_content(store, slug, region_id)
            except Exception:  # noqa: BLE001 -- a nicer highlight never fails a write
                continue
            cell = _cell_holding(content.get("cells") if content else None, boxes[0])
            if cell is not None:
                out[i] = {**row, "source_ref": {**ref, "cell": cell}}
                changed = True
        return ({**intended, "rows": out} if changed else intended), changed

    async def _locate_cells(
        self, intended: dict[str, Any], store: DocStore,
        *, skip: set[int],
    ) -> tuple[dict[str, Any], bool]:
        """Give a row that cites a whole table the cell its value sits in.

        Only for a row that names no box of its own, in a table whose
        structure is valid, so a place someone drew is not reworked and rows
        and columns can be trusted. An older row gains its cell on the next
        write to its card.
        """
        rows = intended.get("rows")
        if not isinstance(rows, list):
            return intended, False
        out, located = list(rows), False
        for i, row in enumerate(rows):
            ref = row.get("source_ref") if isinstance(row, dict) else None
            if i in skip or not isinstance(ref, dict) or ref.get("cell") or ref.get("item_id"):
                continue
            # A box of the caller's own is a claim about the place; leave it.
            detail = ref.get("detail")
            if ref.get("bbox") is not None or (isinstance(detail, dict) and detail.get("cell_bbox")):
                continue
            slug, region_id = ref.get("slug"), ref.get("region_id")
            if not isinstance(slug, str) or not isinstance(region_id, str):
                continue
            try:
                content = await get_region_content(store, slug, region_id)
            except Exception:  # noqa: BLE001 -- locating is a courtesy, never a write failure
                continue
            if not content or content.get("page") != ref.get("page", content.get("page")):
                continue
            # Rows and columns are only trusted where the table's structure is.
            if (content.get("table_topology") or {}).get("status") != "valid":
                continue
            cell = locate_cell(content.get("cells"), row.get("key"), row.get("value"))
            if cell is not None:
                out[i] = {**row, "source_ref": {**ref, "page": content["page"], "cell": cell}}
                located = True
        return ({**intended, "rows": out} if located else intended), located


def _cited_slugs(data: dict[str, Any]) -> list[str]:
    refs = [data.get("source_ref")]
    rows = data.get("rows")
    refs += [r.get("source_ref") for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    slugs = [ref.get("slug") for ref in refs if isinstance(ref, dict)]
    slugs.append(data.get("source_doc_slug"))
    return sorted({s for s in slugs if isinstance(s, str) and s.strip()})


def _cell_holding(cells: Any, box: list[float]) -> dict[str, int] | None:
    """The one cell whose box holds the middle of ``box``."""
    if not isinstance(cells, list) or len(box) != 4:
        return None
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    found = [
        c for c in cells
        if isinstance(c, dict) and type(c.get("row")) is int and type(c.get("col")) is int
        and isinstance(c.get("bbox"), list) and len(c["bbox"]) == 4
        and c["bbox"][0] <= x <= c["bbox"][2] and c["bbox"][1] <= y <= c["bbox"][3]
    ]
    return {"row": found[0]["row"], "col": found[0]["col"]} if len(found) == 1 else None
