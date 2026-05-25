"""PdfExtractor implementation backed by Docling.

Lazy-imports docling so tests that don't touch this module never pay the
import cost. Output shape matches the dict consumed by `core/ingest/silver.py`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class DoclingPdfExtractor:
    async def extract(self, pdf_path: Path) -> dict[str, Any]:
        return await asyncio.to_thread(_extract_sync, pdf_path)


def _extract_sync(pdf_path: Path) -> dict[str, Any]:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    return _flatten(result.document)


def _flatten(doc: Any) -> dict[str, Any]:
    """Mirrors the v1 anchor_ingest.bronze._flatten_docling logic."""
    items: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []

    for it in getattr(doc, "texts", []) or []:
        prov = (it.prov or [None])[0] if hasattr(it, "prov") else None
        page = getattr(prov, "page_no", 0) if prov else 0
        bbox = _bbox_from_prov(prov)
        items.append({
            "label": getattr(it, "label", "text"),
            "text": getattr(it, "text", ""),
            "page": page,
            "bbox": bbox,
        })

    for tbl in getattr(doc, "tables", []) or []:
        prov = (tbl.prov or [None])[0] if hasattr(tbl, "prov") else None
        page = getattr(prov, "page_no", 0) if prov else 0
        bbox = _bbox_from_prov(prov)
        cells = []
        if hasattr(tbl, "data") and hasattr(tbl.data, "table_cells"):
            for cell in tbl.data.table_cells:
                cells.append({
                    "row": getattr(cell, "start_row_offset_idx", None),
                    "col": getattr(cell, "start_col_offset_idx", None),
                    "text": getattr(cell, "text", ""),
                })
        items.append({
            "label": "table",
            "text": "",
            "page": page,
            "bbox": bbox,
            "cells": cells,
        })
        tables.append({"page": page, "bbox": bbox, "cells": cells})

    for pic in getattr(doc, "pictures", []) or []:
        prov = (pic.prov or [None])[0] if hasattr(pic, "prov") else None
        page = getattr(prov, "page_no", 0) if prov else 0
        bbox = _bbox_from_prov(prov)
        items.append({"label": "picture", "text": "", "page": page, "bbox": bbox})

    return {"items": items, "tables": tables}


def _bbox_from_prov(prov: Any) -> list[float]:
    if prov is None or not hasattr(prov, "bbox") or prov.bbox is None:
        return []
    bb = prov.bbox
    return [float(bb.l), float(bb.t), float(bb.r), float(bb.b)]
