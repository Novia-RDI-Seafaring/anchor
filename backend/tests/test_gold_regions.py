"""Tests for gold region cropping + extractor scaffolding."""
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.gold import (
    PageRegions,
    Region,
    RegionCrop,
    crop_region_pdf,
    crop_region_png,
    crop_region_svg,
    extract_page_regions,
)

TESTS_DIR = Path(__file__).resolve().parent
PDF = TESTS_DIR / "alfa-laval-lkh-centrifugal-pump.pdf"

pytestmark = pytest.mark.skipif(not PDF.exists(), reason="alfa-laval pdf missing from tests/")


# ── Cropping (deterministic, no LLM) ─────────────────────────────────────────


def test_crop_region_png_writes_file(tmp_path: Path):
    out = tmp_path / "crop.png"
    bbox = [56.7, 723.4, 187.7, 698.3]  # "Alfa Laval LKH" header on p1
    written = crop_region_png(PDF, page=1, bbox=bbox, out_path=out, dpi=72)
    assert written == out
    assert out.exists()
    assert out.stat().st_size > 0


def test_crop_region_svg_writes_file(tmp_path: Path):
    out = tmp_path / "crop.svg"
    written = crop_region_svg(PDF, page=1, bbox=[56.7, 723.4, 187.7, 698.3], out_path=out)
    assert written.exists()
    content = out.read_text()
    assert content.startswith("<") and "svg" in content[:200]


def test_crop_region_pdf_writes_single_page(tmp_path: Path):
    out = tmp_path / "crop.pdf"
    crop_region_pdf(PDF, page=2, bbox=[55.3, 762.3, 553.0, 687.7], out_path=out)
    assert out.exists()
    import pymupdf
    with pymupdf.open(out) as d:
        assert d.page_count == 1


# ── Extractor with mocked client (no LLM call) ───────────────────────────────


class _MockClient:
    """Returns canned regions so we can exercise snap+crop deterministically."""

    def __init__(self, regions: list[dict[str, Any]]):
        self._regions = regions
        self.calls = 0

    def extract_page(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls += 1
        return self._regions


def test_extract_page_regions_invokes_client_and_snaps(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        {"label": "section_header", "page": 1, "bbox": [10, 100, 30, 80], "text": "Header"},
        {"label": "text", "page": 1, "bbox": [10, 75, 30, 60], "text": "Body"},
        {"label": "text", "page": 2, "bbox": [0, 0, 1, 1], "text": "wrong page"},
    ]}
    client = _MockClient([
        {
            "id": "p1-r1-test",
            "kind": "text",
            "title": "Test region",
            "description": "Desc",
            "bbox": [5, 110, 35, 50],  # encloses both p1 items
            "tags": ["narrative"],
            "entities": [],
        }
    ])

    # Extractor crops PNG by default. Patch crop_region_png and crop_region_svg
    # to a no-op so we don't need a real PDF for the snap test.
    import src.ingestion.gold as gold

    monkeypatched = []

    def fake_crop(pdf_path, page, bbox, out_path, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        monkeypatched.append((page, tuple(bbox)))
        return out_path

    original_png = gold.crop_region_png
    original_svg = gold.crop_region_svg
    gold.crop_region_png = fake_crop  # type: ignore[assignment]
    gold.crop_region_svg = fake_crop  # type: ignore[assignment]
    try:
        result = extract_page_regions(
            docling,
            page=1,
            page_image=tmp_path / "page1.png",
            pdf_path=tmp_path / "fake.pdf",
            out_dir=tmp_path / "gold",
            client=client,
        )
    finally:
        gold.crop_region_png = original_png  # type: ignore[assignment]
        gold.crop_region_svg = original_svg  # type: ignore[assignment]

    assert client.calls == 1
    assert isinstance(result, PageRegions)
    assert len(result.regions) == 1
    region = result.regions[0]
    # Snapped to the union of items 0 and 1: [10, 100, 30, 60]
    assert region.bbox == [10, 100, 30, 60]
    assert region.source_refs[0].item_indices == [0, 1]
    assert region.crops is not None
    assert region.crops.png.endswith("p1-r1-test.png")
    assert (tmp_path / "gold" / "1" / "p1-r1-test.png").exists()


def test_extract_page_regions_chart_kind_emits_svg(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        {"label": "picture", "page": 1, "bbox": [10, 100, 50, 50], "text": ""},
    ]}
    client = _MockClient([
        {
            "id": "p1-r1-curve",
            "kind": "chart",
            "title": "H/Q curve",
            "description": "Performance curve",
            "bbox": [5, 110, 55, 40],
            "tags": ["chart", "performance_curve"],
        }
    ])

    import src.ingestion.gold as gold

    def stub(pdf_path, page, bbox, out_path, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        return out_path

    orig_png = gold.crop_region_png
    orig_svg = gold.crop_region_svg
    gold.crop_region_png = stub  # type: ignore[assignment]
    gold.crop_region_svg = stub  # type: ignore[assignment]
    try:
        result = extract_page_regions(
            docling,
            page=1,
            page_image=tmp_path / "p.png",
            pdf_path=tmp_path / "fake.pdf",
            out_dir=tmp_path / "gold",
            client=client,
        )
    finally:
        gold.crop_region_png = orig_png  # type: ignore[assignment]
        gold.crop_region_svg = orig_svg  # type: ignore[assignment]

    region = result.regions[0]
    assert region.crops is not None
    assert region.crops.svg is not None
    assert region.crops.svg.endswith(".svg")


def test_extract_page_regions_default_client_raises(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 0, 1, 1], "text": "x"},
    ]}
    with pytest.raises(RuntimeError, match="No RegionExtractorClient"):
        extract_page_regions(
            docling,
            page=1,
            page_image=tmp_path / "p.png",
            pdf_path=tmp_path / "fake.pdf",
            out_dir=tmp_path / "gold",
        )


def test_region_serializes_round_trip():
    r = Region(
        id="p1-r1",
        page=1,
        bbox=[0, 100, 50, 0],
        kind="chart",
        title="t",
        description="d",
        tags=["chart", "performance_curve", "mentions:lkh-5"],
        crops=RegionCrop(png="p1-r1.png", svg="p1-r1.svg"),
    )
    dumped = r.model_dump()
    rebuilt = Region.model_validate(dumped)
    assert rebuilt.tags == r.tags
    assert rebuilt.crops is not None and rebuilt.crops.svg == "p1-r1.svg"
