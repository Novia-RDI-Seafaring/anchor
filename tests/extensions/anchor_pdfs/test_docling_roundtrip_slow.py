"""Real-Docling round trip: the one test that proves bbox orientation (#281).

Runs the actual `DoclingPdfExtractor` on a PyMuPDF-generated PDF with text at
known positions, pushes the result through the ingest boundary normaliser,
and then asks PyMuPDF — an independent coordinate system — whether each
silver bbox really contains its own text. A mis-oriented bbox (the
pre-#281 mirror) would still satisfy the pure-function tests but fails here.

Local-only (`-m slow`): Docling loads layout models and takes tens of
seconds. It is excluded from CI by the default `-m 'not slow'` addopts.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from anchor.extensions.anchor_pdfs.core.silver import (
    BBOX_ORIGIN,
    build_pages_meta,
    flip_bbox_y,
    normalize_items,
    render_pages_md,
)
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import (
    _crop_region_sync,
    _locate_text_sync,
)

PAGE_W, PAGE_H = 595.0, 842.0
# (text, y in top-left points). Distinct tokens so locate_text is unambiguous,
# and all placed off the page's vertical centre so a box and its mirror image
# never overlap (the mirror check below relies on that).
LINES = [("ALPHAHEAD", 90.0), ("BETABODY", 300.0), ("GAMMAFOOT", 760.0)]


@pytest.fixture()
def known_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "known.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    for text, y in LINES:
        page.insert_text((72, y), f"{text} lorem ipsum dolor sit amet", fontsize=14)
    doc.save(path)
    doc.close()
    return path


@pytest.mark.slow
def test_docling_bboxes_contain_their_own_text_in_top_left_space(known_pdf: Path):
    import asyncio

    docling = asyncio.run(DoclingPdfExtractor(device="cpu").extract(known_pdf))
    docling = normalize_items(docling)

    assert docling["coord_origin"] == BBOX_ORIGIN
    size = docling["pages"][1]
    assert size["width"] == pytest.approx(PAGE_W, abs=1)
    assert size["height"] == pytest.approx(PAGE_H, abs=1)

    found: dict[str, list[float]] = {}
    for item in docling["items"]:
        for token, _ in LINES:
            if token in (item.get("text") or "") and len(item.get("bbox") or []) == 4:
                found[token] = item["bbox"]
    assert set(found) == {t for t, _ in LINES}, f"docling did not find every line: {found}"

    for token, y in LINES:
        bbox = found[token]
        # Top-left: the box top sits just above the baseline we inserted at.
        assert bbox[1] < y <= bbox[3] + 2, (token, bbox, y)
        # Independent check: PyMuPDF locates the text INSIDE the docling box…
        assert _locate_text_sync(known_pdf, 1, token, bbox), (token, bbox)
        # …and NOT inside the mirror box the old convention would have produced.
        assert not _locate_text_sync(known_pdf, 1, token, flip_bbox_y(bbox, PAGE_H)), token
        # And a crop with the box is a real, non-empty image.
        assert len(_crop_region_sync(known_pdf, 1, bbox, "png", 72)) > 500

    # Reading order follows the page (top-left: smaller y first).
    md = render_pages_md(docling)[1]
    assert md.index("ALPHAHEAD") < md.index("BETABODY") < md.index("GAMMAFOOT")
    meta = build_pages_meta(docling)
    assert meta["bbox_origin"] == BBOX_ORIGIN
    assert meta["pages"]["1"]["page_size"] == pytest.approx([PAGE_W, PAGE_H], abs=1)
