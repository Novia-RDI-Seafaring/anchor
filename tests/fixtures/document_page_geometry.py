"""Generate the frontend contract fixture through the real silver producer."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pymupdf

from anchor.extensions.anchor_pdfs.core.silver import build_pages_meta, normalize_items
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer

PAGE_SIZES = [(600, 800), (800, 600), (420, 595)]


def source_boxes(width: int, height: int) -> dict[str, list[int]]:
    return {
        "review": [60, 100, 240, 150],
        "top-left": [12, 16, 24, 26],
        "bottom-right": [width - 30, height - 40, width - 10, height - 20],
        "table": [35, 200, width - 35, height - 65],
    }


def write_pdf(path: Path) -> None:
    with pymupdf.open() as pdf:
        for width, height in PAGE_SIZES:
            page = pdf.new_page(width=width, height=height)
            for label, box in source_boxes(width, height).items():
                page.draw_rect(pymupdf.Rect(box), color=(0.1, 0.2, 0.8), fill=(0.8, 0.9, 1))
                page.insert_text((box[0], box[1] - 3), label, fontsize=8)
        pdf.save(path)


async def produce(path: Path) -> dict:
    renderer = PymupdfPdfRenderer()
    sizes = await renderer.page_sizes(path)
    items = [{"label": "text", "page": page, "text": label, "bbox": bbox}
             for page, (width, height) in enumerate(PAGE_SIZES, 1)
             for label, bbox in source_boxes(width, height).items()]
    docling = normalize_items({"bbox_origin": "top-left", "items": items,
                               "pages": {p: {"width": w, "height": h} for p, (w, h) in sizes.items()}})
    store = MemoryDocStore()
    await store.write_silver_artifact("geometry", "index.json", json.dumps({
        "document": {"filename": "geometry.pdf", "title": "Geometry", "page_count": len(sizes)},
        "outline": [],
    }))
    await store.write_silver_artifact("geometry", "pages.meta.json", json.dumps(build_pages_meta(docling)))
    for page, (width, height) in enumerate(PAGE_SIZES, 1):
        await store.write_gold_region_file("geometry", page, [
            {"id": label, "kind": "text", "title": label, "page": page,
             "bbox": bbox, "coord_origin": "top-left"}
            for label, bbox in source_boxes(width, height).items()
        ])
    await store.mark_gold_complete("geometry", {"region_count": len(items)})
    rasters = {}
    for dpi in (72, 150, 300):
        pngs = await renderer.render_pages(path, dpi=dpi)
        rasters[str(dpi)] = {}
        for page, png in pngs.items():
            pixmap = pymupdf.Pixmap(png)
            rasters[str(dpi)][str(page)] = {"width": pixmap.width, "height": pixmap.height}
    # HTTP serialization turns page keys into strings without changing the producer schema.
    return json.loads(json.dumps({"gold_map": await store.get_gold_map("geometry"), "rasters": rasters,
            "boxes": {str(page): source_boxes(w, h) for page, (w, h) in enumerate(PAGE_SIZES, 1)}}))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "geometry.pdf"
        write_pdf(path)
        payload = asyncio.run(produce(path))
    Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
