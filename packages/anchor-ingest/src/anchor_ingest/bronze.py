"""Bronze layer — raw PDF intake + first-step normalization to silver.

The bronze atom is the file as uploaded: no parsing, no transformation. The
only thing this module does is hand the PDF to docling and flatten the
result into the `{items, tables}` shape that silver consumes.

Heavy import: `docling.document_converter` is loaded lazily so importing
`bronze` itself stays cheap.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def pdf_to_silver(pdf_path: Path, silver_dir: Path) -> Path:
    """Run docling on a PDF and write `silver_dir/docling.json`.

    Returns the path to the written docling.json. Idempotent: re-running
    overwrites. The output is a flat `{items, tables}` dict in the same
    shape `silver.build_index` and `silver.render_pages_md` expect.
    """
    from docling.document_converter import DocumentConverter

    silver_dir.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    flat = _flatten_docling(result.document)
    out = silver_dir / "docling.json"
    out.write_text(json.dumps(flat, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _flatten_docling(doc: Any) -> dict[str, Any]:
    """Flatten a `DoclingDocument` into our flat-items silver format."""
    items: list[dict[str, Any]] = []

    for t in getattr(doc, "texts", []) or []:
        prov = (t.prov or [None])[0]
        if not prov:
            continue
        items.append({
            "type": type(t).__name__,
            "label": _label_str(t.label),
            "text": t.text or "",
            "page": prov.page_no,
            "bbox": [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b],
        })

    for tbl in getattr(doc, "tables", []) or []:
        prov = (tbl.prov or [None])[0]
        if not prov:
            continue
        cells: list[dict[str, Any]] = []
        td = getattr(tbl, "data", None)
        if td and getattr(td, "table_cells", None):
            for c in td.table_cells:
                cells.append({
                    "text": c.text or "",
                    "row": c.start_row_offset_idx,
                    "col": c.start_col_offset_idx,
                    "row_span": c.end_row_offset_idx - c.start_row_offset_idx,
                    "col_span": c.end_col_offset_idx - c.start_col_offset_idx,
                    "is_header": bool(
                        getattr(c, "column_header", False) or getattr(c, "row_header", False)
                    ),
                })
        items.append({
            "type": "TableItem",
            "label": "table",
            "text": "",
            "page": prov.page_no,
            "bbox": [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b],
            "cells": cells,
        })

    for p in getattr(doc, "pictures", []) or []:
        prov = (p.prov or [None])[0]
        if not prov:
            continue
        caption = ""
        if hasattr(p, "caption_text"):
            try:
                caption = p.caption_text(doc) or ""
            except Exception:
                caption = ""
        items.append({
            "type": "PictureItem",
            "label": "picture",
            "text": caption,
            "page": prov.page_no,
            "bbox": [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b],
        })

    items.sort(key=lambda i: (i["page"], -i["bbox"][1], i["bbox"][0]))
    return {"items": items, "tables": []}


def _label_str(label: Any) -> str:
    return label.value if hasattr(label, "value") else str(label)
