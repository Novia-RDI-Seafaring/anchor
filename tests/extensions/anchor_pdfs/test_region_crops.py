"""Lazy gold region crops + DPI page images (core read-ops).

Gold promised crops at ``gold/<slug>/pages/<page>/<region_id>.png`` but the
pipeline never wrote them. ``region_crops.get_region_crop`` renders a missing
crop from the bronze PDF on first read and persists it at the canonical path;
``region_crops.get_page_image`` re-renders a page at an explicit DPI. These
tests drive the core functions against FsDocStore + FakePdfRenderer.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.upload_safety import UnsafeUploadError
from anchor.extensions.anchor_pdfs.core.region_crops import (
    CropUnavailable,
    get_page_image,
    get_region_crop,
    parse_crop_ref,
)
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.fixtures.fakes import FakePdfRenderer


@pytest.fixture()
def store(tmp_path):
    s = FsDocStore(tmp_path)
    (s.bronze / "demo.pdf").write_bytes(b"%PDF-fake")
    silver_dir = s.silver / "demo"
    (silver_dir / "pages").mkdir(parents=True)
    (silver_dir / "index.json").write_text(
        json.dumps({
            "document": {"filename": "demo.pdf", "title": "Demo", "page_count": 2},
            "outline": [],
        }),
        encoding="utf-8",
    )
    (silver_dir / "pages" / "1.png").write_bytes(b"silver-150dpi-png")
    asyncio.run(s.write_gold_region_file("demo", 1, [
        {"id": "r1", "kind": "chart", "title": "Pump curve", "page": 1,
         "bbox": [10.0, 195.0, 200.0, 215.0], "tags": [], "entities": []},
    ]))
    return s


@pytest.fixture()
def renderer():
    return FakePdfRenderer(page_count=2)


# -- Crop reference parsing ------------------------------------------------


def test_parse_crop_ref_accepts_all_documented_forms():
    assert parse_crop_ref("4/r1.png") == (4, "r1")
    assert parse_crop_ref("p4/r1") == (4, "r1")
    assert parse_crop_ref("p4/r1.png") == (4, "r1")
    assert parse_crop_ref("4/r1") == (4, "r1")
    assert parse_crop_ref("r1") == (None, "r1")
    assert parse_crop_ref("r1.png") == (None, "r1")


def test_parse_crop_ref_rejects_garbage_with_the_valid_form():
    for bad in ["", "x/y/../z.png", "4/", "notapage/r1.png", "4/..", "4/.."]:
        with pytest.raises(CropUnavailable) as exc:
            parse_crop_ref(bad)
        assert "<page>/<region_id>.png" in str(exc.value)


# -- Lazy generation -------------------------------------------------------


def test_missing_crop_is_rendered_and_persisted_at_canonical_path(store, renderer):
    path = asyncio.run(get_region_crop(store, renderer, "demo", "1/r1.png"))
    assert path == store.gold / "demo" / "pages" / "1" / "r1.png"
    assert path.read_bytes().startswith(b"CROP-1-")
    # Default DPI is 300 (silver's 150 is too coarse for chart tracing).
    assert renderer.crop_calls[-1]["dpi"] == 300
    # bbox is expanded by the 3pt margin around the stored [10,195,200,215].
    assert renderer.crop_calls[-1]["bbox"] == [7.0, 192.0, 203.0, 218.0]


def test_existing_crop_is_served_without_rerender(store, renderer):
    target = store.gold / "demo" / "pages" / "1" / "r1.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"already-on-disk")
    path = asyncio.run(get_region_crop(store, renderer, "demo", "1/r1.png"))
    assert path.read_bytes() == b"already-on-disk"
    assert renderer.crop_calls == []


def test_inspect_region_token_styles_resolve_to_the_same_crop(store, renderer):
    for ref in ["p1/r1", "1/r1", "r1", "r1.png"]:
        path = asyncio.run(get_region_crop(store, renderer, "demo", ref))
        assert path == store.gold / "demo" / "pages" / "1" / "r1.png"


def test_bare_region_id_finds_page_and_persists_canonically(store, renderer):
    path = asyncio.run(get_region_crop(store, renderer, "demo", "r1"))
    assert path == store.gold / "demo" / "pages" / "1" / "r1.png"
    assert path.exists()


def test_explicit_dpi_rerenders_and_overwrites_the_cache(store, renderer):
    first = asyncio.run(get_region_crop(store, renderer, "demo", "1/r1.png"))
    first.write_bytes(b"stale-300dpi")
    path = asyncio.run(get_region_crop(store, renderer, "demo", "1/r1.png", dpi=600))
    assert path == first
    assert path.read_bytes().startswith(b"CROP-1-")
    assert renderer.crop_calls[-1]["dpi"] == 600


def test_dpi_is_clamped_to_the_sane_cap(store, renderer):
    asyncio.run(get_region_crop(store, renderer, "demo", "1/r1.png", dpi=5000))
    assert renderer.crop_calls[-1]["dpi"] == 600
    asyncio.run(get_region_crop(store, renderer, "demo", "1/r1.png", dpi=10))
    assert renderer.crop_calls[-1]["dpi"] == 72


def test_margin_is_clamped_to_page_bounds(store, renderer):
    asyncio.run(store.write_gold_region_file("demo", 2, [
        {"id": "r9", "kind": "text", "title": "Edge", "page": 2,
         "bbox": [0.0, 0.0, 612.0, 20.0], "tags": [], "entities": []},
    ]))
    asyncio.run(get_region_crop(store, renderer, "demo", "2/r9.png"))
    # Page is 612x792: the margin must not push the clip outside it.
    assert renderer.crop_calls[-1]["bbox"] == [0.0, 0.0, 612.0, 23.0]


# -- Error surface ---------------------------------------------------------


def test_unknown_region_error_names_pages_and_valid_form(store, renderer):
    with pytest.raises(CropUnavailable) as exc:
        asyncio.run(get_region_crop(store, renderer, "demo", "1/r9.png"))
    msg = str(exc.value)
    assert "'r9' not found" in msg
    assert "pages with regions: 1" in msg
    assert "<page>/<region_id>.png" in msg


def test_wrong_page_error_points_at_the_right_page(store, renderer):
    with pytest.raises(CropUnavailable) as exc:
        asyncio.run(get_region_crop(store, renderer, "demo", "2/r1.png"))
    assert "on page 1" in str(exc.value)
    assert "1/r1.png" in str(exc.value)


def test_document_without_gold_says_so(store, renderer):
    with pytest.raises(CropUnavailable) as exc:
        asyncio.run(get_region_crop(store, renderer, "other-doc", "1/r1.png"))
    assert "no gold regions" in str(exc.value)


def test_region_without_bbox_is_a_clean_error(store, renderer):
    asyncio.run(store.write_gold_region_file("demo", 2, [
        {"id": "r7", "kind": "text", "title": "No box", "page": 2,
         "tags": [], "entities": []},
    ]))
    with pytest.raises(CropUnavailable) as exc:
        asyncio.run(get_region_crop(store, renderer, "demo", "2/r7.png"))
    assert "no bbox" in str(exc.value)


def test_memory_store_without_bronze_pdf_is_a_clean_error(renderer):
    mem = MemoryDocStore()
    asyncio.run(mem.write_gold_region_file("demo", 1, [
        {"id": "r1", "kind": "text", "title": "t", "page": 1,
         "bbox": [1, 2, 3, 4], "tags": [], "entities": []},
    ]))
    with pytest.raises(CropUnavailable) as exc:
        asyncio.run(get_region_crop(mem, renderer, "demo", "1/r1.png"))
    assert "bronze PDF not available" in str(exc.value)


# -- Traversal safety ------------------------------------------------------


def test_traversal_refs_read_and_write_nothing_outside_the_store(tmp_path, store, renderer):
    outside = store.data_dir.parent
    before = {p for p in outside.rglob("*")}
    for rel_path in [
        "../../escape.png",
        "../../../../etc/passwd",
        "..\\..\\windows.png",
        "/abs/path.png",
        "1/../../escape.png",
    ]:
        with pytest.raises(CropUnavailable):
            asyncio.run(get_region_crop(store, renderer, "demo", rel_path))
    assert renderer.crop_calls == []
    assert {p for p in outside.rglob("*")} == before


def test_write_crop_barrier_rejects_traversal(store):
    for slug, rel in [
        ("../evil", "1/r1.png"),
        ("demo", "../escape.png"),
        ("demo", "../../escape.png"),
        ("demo", "/abs/escape.png"),
    ]:
        with pytest.raises(UnsafeUploadError):
            asyncio.run(store.write_crop(slug, rel, b"png"))


# -- Page images at DPI ----------------------------------------------------


def test_page_image_without_dpi_serves_the_silver_png(store, renderer):
    path = asyncio.run(get_page_image(store, renderer, "demo", 1))
    assert path == store.silver / "demo" / "pages" / "1.png"
    assert renderer.crop_calls == []


def test_page_image_with_dpi_renders_full_page_and_caches_variant(store, renderer):
    path = asyncio.run(get_page_image(store, renderer, "demo", 1, dpi=600))
    assert path == store.silver / "demo" / "pages" / "1@600dpi.png"
    assert path.read_bytes().startswith(b"CROP-1-")
    call = renderer.crop_calls[-1]
    assert call["dpi"] == 600
    assert call["bbox"] == [0.0, 0.0, 612.0, 792.0]
    # Cached: a second read at the same DPI does not re-render.
    again = asyncio.run(get_page_image(store, renderer, "demo", 1, dpi=600))
    assert again == path
    assert len(renderer.crop_calls) == 1


def test_page_image_dpi_is_clamped(store, renderer):
    path = asyncio.run(get_page_image(store, renderer, "demo", 1, dpi=9999))
    assert path == store.silver / "demo" / "pages" / "1@600dpi.png"


def test_page_image_dpi_out_of_range_page_is_a_clean_error(store, renderer):
    with pytest.raises(CropUnavailable) as exc:
        asyncio.run(get_page_image(store, renderer, "demo", 99, dpi=300))
    assert "out of range" in str(exc.value)
