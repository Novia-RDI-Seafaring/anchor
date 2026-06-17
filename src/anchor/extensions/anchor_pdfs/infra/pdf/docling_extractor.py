"""PdfExtractor implementation backed by Docling.

Lazy-imports docling so tests that don't touch this module never pay the
import cost. Output shape matches the dict consumed by `core/ingest/silver.py`.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

# Accelerators that errored this process; once a backend has fallen back we
# skip straight to CPU for the rest of the run instead of re-attempting a
# doomed device per document.
_FELL_BACK: set[str] = set()

_QUIETED = False


class _DropBelow(logging.Filter):
    """Drop log records under ``level`` regardless of the logger's own level.

    RapidOCR rebuilds its logger and calls ``setLevel(INFO)`` every time docling
    constructs it (mid-``convert``), so a one-shot ``setLevel`` is overwritten.
    A filter sticks: ``Logger.__init__`` never clears filters, and the filter is
    consulted before handlers, so INFO records are dropped however the level is
    later reset.
    """

    def __init__(self, level: int) -> None:
        super().__init__()
        self._level = level

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        return record.levelno >= self._level


def _quiet_dependency_logs() -> None:
    """Tame third-party ingest chatter so the output reads as ANCHOR working.

    docling and RapidOCR log a wall of INFO lines (model paths, "Using CPU
    device") plus a "RapidOCR returned empty result!" warning for born-digital
    pages with nothing to OCR. That noise looks like the tool is hand-rolling
    OCR — it misleads users *and* agents. Quiet it by default; restore the full
    stream with ``ANCHOR_LOG_LEVEL=DEBUG``.
    """
    global _QUIETED
    import os

    if _QUIETED or os.environ.get("ANCHOR_LOG_LEVEL", "").upper() == "DEBUG":
        return
    # docling uses standard module loggers that don't fight back; a level is enough.
    logging.getLogger("docling").setLevel(logging.WARNING)
    # The empty-result warning fires per born-digital page — noise, not an error.
    logging.getLogger("docling.models.stages.ocr.rapid_ocr_model").setLevel(logging.ERROR)
    # RapidOCR re-asserts INFO whenever docling rebuilds its logger, so a filter
    # (not just a level) is what holds. Force its log module to import first so
    # the logger + its own handler exist, then attach the filter.
    for module in ("rapidocr.utils.log", "rapidocr"):
        try:
            __import__(module)
            break
        except Exception:  # noqa: BLE001 - rapidocr optional / layout varies
            continue
    rapid = logging.getLogger("RapidOCR")
    rapid.setLevel(logging.ERROR)
    rapid.addFilter(_DropBelow(logging.ERROR))
    # The "Loading weights" tqdm bars come from huggingface model loads.
    try:
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
    except Exception:  # noqa: BLE001 - best effort; absent in some installs
        pass
    _QUIETED = True


class DoclingPdfExtractor:
    def __init__(self, device: str = "auto") -> None:
        self._device = device

    async def extract(self, pdf_path: Path) -> dict[str, Any]:
        return await asyncio.to_thread(_extract_sync, pdf_path, self._device)


def _resolve_device(requested: str) -> str:
    """Resolve "auto" to the best *usable* accelerator: CUDA, else CPU.

    Auto deliberately does NOT pick MPS. Docling's layout model (rt_detr_v2)
    builds a float64 positional embedding for every page, and MPS cannot hold
    float64 — so MPS fails for *every* document on Apple Silicon, noisily and
    after a wasted model load. CPU is the right auto choice there. Explicit
    `mps` is still honored (with the CPU fallback below) for anyone who wants
    to try a future fixed docling/torch. A non-"auto" value is returned as-is;
    any torch probe failure falls back to CPU so selection never blocks.
    """
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001 - torch missing / probe error -> CPU
        return "cpu"
    return "cpu"


def _is_accelerator_error(exc: Exception) -> bool:
    """True for failures that a CPU retry is likely to recover from."""
    msg = str(exc).lower()
    return any(s in msg for s in ("mps", "float64", "cuda", "out of memory", "cublas"))


def _extract_sync(pdf_path: Path, device: str = "auto") -> dict[str, Any]:
    # Prefer a GPU when asked ("auto" picks the best one), but never let an
    # accelerator failure break ingestion: docling's MPS path raises "Cannot
    # convert a MPS Tensor to float64" on Apple Silicon, and a CPU retry
    # recovers from it. The same fallback covers CUDA OOM and similar.
    _quiet_dependency_logs()
    candidate = _resolve_device((device or "auto").lower())
    if candidate != "cpu" and candidate in _FELL_BACK:
        candidate = "cpu"
    try:
        return _convert(pdf_path, candidate)
    except Exception as exc:  # noqa: BLE001 - inspect, then retry on CPU or re-raise
        if candidate != "cpu" and _is_accelerator_error(exc):
            _FELL_BACK.add(candidate)
            print(
                f"Warning: docling {candidate} backend failed ({exc}); retrying on CPU.",
                file=sys.stderr,
            )
            return _convert(pdf_path, "cpu")
        raise


def _convert(pdf_path: Path, device: str) -> dict[str, Any]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    accel_device = {
        "cpu": AcceleratorDevice.CPU,
        "cuda": AcceleratorDevice.CUDA,
        "mps": AcceleratorDevice.MPS,
    }.get(device, AcceleratorDevice.CPU)

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = AcceleratorOptions(device=accel_device)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(pdf_path))
    return _flatten(result.document)


def _flatten(doc: Any) -> dict[str, Any]:
    """Mirrors the v1 anchor_ingest.bronze._flatten_docling logic."""
    items: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    page_heights = _page_heights(doc)

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
                cell_data = {
                    "row": getattr(cell, "start_row_offset_idx", None),
                    "col": getattr(cell, "start_col_offset_idx", None),
                    "text": getattr(cell, "text", ""),
                }
                cell_bbox = _bbox_from_cell(cell, page_heights.get(page))
                if cell_bbox:
                    cell_data["bbox"] = cell_bbox
                cells.append(cell_data)
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


def _bbox_from_cell(cell: Any, page_height: float | None) -> list[float]:
    bb = getattr(cell, "bbox", None)
    if bb is None:
        return []
    if page_height is not None and hasattr(bb, "to_bottom_left_origin"):
        bb = bb.to_bottom_left_origin(page_height)
    elif "BOTTOMLEFT" not in str(getattr(bb, "coord_origin", "")).upper():
        return []
    return [float(bb.l), float(bb.t), float(bb.r), float(bb.b)]


def _page_heights(doc: Any) -> dict[int, float]:
    pages = getattr(doc, "pages", None)
    if not isinstance(pages, dict):
        return {}
    out: dict[int, float] = {}
    for page_no, page in pages.items():
        size = getattr(page, "size", None)
        height = getattr(size, "height", None)
        if isinstance(page_no, int) and isinstance(height, (int, float)):
            out[page_no] = float(height)
    return out
