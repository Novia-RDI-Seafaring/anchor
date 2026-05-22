"""Smoke test that the index/render pipeline works on the 3 alfa-laval docs."""
import json
from pathlib import Path

import pytest

from src.ingestion.silver import build_index, build_pages_meta, render_pages_md

SILVER = Path(__file__).resolve().parents[1] / "data" / "silver"
TEST_SILVER = Path(__file__).resolve().parent / "test_data" / "full_pipeline" / "silver"

def get_silver_path(slug: str) -> Path:
    local_path = SILVER / slug / "docling.json"
    if local_path.exists():
        return SILVER / slug
    return TEST_SILVER / slug

DOCS = []
for slug in [
    "alfa-laval-lkh-centrifugal-pump",
    "alfa-laval-ese00698-lkh-manual-en-gb",
    "alfa-laval-lkh-performance-curves-product-leaflet-en",
]:
    if (SILVER / slug / "docling.json").exists() or (TEST_SILVER / slug / "docling.json").exists():
        DOCS.append(slug)


@pytest.mark.parametrize("slug", DOCS)
def test_doc_silver_exists(slug: str):
    docling = get_silver_path(slug) / "docling.json"
    assert docling.exists(), f"missing {docling}"


@pytest.mark.parametrize("slug", DOCS)
def test_index_has_outline_and_tables(slug: str):
    docling = json.loads((get_silver_path(slug) / "docling.json").read_text())
    index = build_index(docling, filename=f"{slug}.pdf")
    assert index["document"]["page_count"] > 0
    assert len(index["outline"]) > 0  # every doc has at least one heading
    # tables/figures may be zero for some docs, but the keys must exist
    assert "tables" in index and "figures" in index


@pytest.mark.parametrize("slug", DOCS)
def test_pages_meta_covers_all_pages(slug: str):
    docling = json.loads((get_silver_path(slug) / "docling.json").read_text())
    index = build_index(docling, filename=f"{slug}.pdf")
    meta = build_pages_meta(docling)
    assert meta["page_count"] == index["document"]["page_count"]
    # Every page in the index should appear in pages.meta
    expected_pages = {str(p) for p in range(1, meta["page_count"] + 1) if p > 0}
    # Some pages may be blank (no items) — meta only includes pages with items.
    assert set(meta["pages"].keys()).issubset(expected_pages)


@pytest.mark.parametrize("slug", DOCS)
def test_render_pages_md_produces_one_md_per_page_with_items(slug: str):
    docling = json.loads((get_silver_path(slug) / "docling.json").read_text())
    md_by_page = render_pages_md(docling)
    assert len(md_by_page) > 0
    # Every emitted page must have non-empty markdown
    for page_no, md in md_by_page.items():
        assert isinstance(page_no, int)
        assert md.strip(), f"page {page_no} of {slug} rendered empty"


def test_performance_curves_doc_mentions_lkh_models():
    """The performance curves leaflet should mention multiple LKH models."""
    slug = "alfa-laval-lkh-performance-curves-product-leaflet-en"
    docling_path = get_silver_path(slug) / "docling.json"
    if not docling_path.exists():
        pytest.skip(f"no local ingestion for {slug}")
    docling = json.loads(docling_path.read_text())
    md_by_page = render_pages_md(docling)
    full = "\n".join(md_by_page.values())
    for model in ["LKH-5", "LKH-10", "LKH-90"]:
        assert model in full, f"{model} missing from performance curves md"


def test_lkh_manual_doc_long_outline():
    """The LKH manual is a long doc — outline should have many entries."""
    slug = "alfa-laval-ese00698-lkh-manual-en-gb"
    docling_path = get_silver_path(slug) / "docling.json"
    if not docling_path.exists():
        pytest.skip(f"no local ingestion for {slug}")
    docling = json.loads(docling_path.read_text())
    index = build_index(docling, filename="x.pdf")
    assert index["document"]["page_count"] >= 20
    assert len(index["outline"]) >= 20
