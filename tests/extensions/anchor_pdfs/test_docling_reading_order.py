"""Docling tree order reaches the persisted silver artifacts together."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.core.silver import (
    build_page_candidates,
    build_pages_meta,
    normalize_items,
    render_pages_md,
)
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import _flatten
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import FakePdfExtractor, FakePdfRenderer, FakePolisher


@pytest.fixture()
def ordered_document():
    from docling_core.types.doc import (
        BoundingBox,
        CoordOrigin,
        DocItemLabel,
        DoclingDocument,
        GroupLabel,
        TableCell,
        TableData,
    )
    from docling_core.types.doc.document import ProvenanceItem

    doc = DoclingDocument(name="reading-order")
    section = doc.add_group(label=GroupLabel.SECTION, name="Section")

    def prov(bbox, text=""):
        return ProvenanceItem(
            page_no=1, charspan=(0, len(text)),
            bbox=BoundingBox(l=bbox[0], t=bbox[1], r=bbox[2], b=bbox[3],
                             coord_origin=CoordOrigin.TOPLEFT),
        )

    doc.add_text(label=DocItemLabel.TEXT, text="paragraph A", parent=section,
                 prov=prov([10, 10, 100, 20], "paragraph A"))
    table_prov = prov([10, 100, 100, 150])
    doc.add_table(parent=section, prov=table_prov, data=TableData(
        num_rows=1, num_cols=1,
        table_cells=[TableCell(text="table", start_row_offset_idx=0, end_row_offset_idx=1,
                              start_col_offset_idx=0, end_col_offset_idx=1,
                              bbox=table_prov.bbox)],
    ))
    doc.add_text(label=DocItemLabel.TEXT, text="paragraph B", parent=section,
                 prov=prov([10, 160, 100, 170], "paragraph B"))
    # The right column starts above B; geometric sorting would interleave it.
    doc.add_picture(parent=section, prov=prov([200, 10, 300, 60]))
    doc.add_text(label=DocItemLabel.TEXT, text="paragraph C", parent=section,
                 prov=prov([200, 70, 300, 90], "paragraph C"))
    return doc


def _names(items):
    return [item.get("text") or item["label"] for item in items]


def _assert_markdown_order(markdown):
    tokens = ["paragraph A", "| table |", "paragraph B", "_[figure:", "paragraph C"]
    positions = [markdown.index(token) for token in tokens]
    assert positions == sorted(positions)


def test_flatten_interleaves_tree_order_before_assigning_candidate_ids(ordered_document):
    silver = normalize_items(_flatten(ordered_document))
    candidates = build_page_candidates(silver)[1]

    expected = ["paragraph A", "table", "paragraph B", "picture", "paragraph C"]
    assert _names(silver["items"]) == expected
    assert _names(candidates) == expected
    assert [candidate["id"] for candidate in candidates] == [f"p1-i{i}" for i in range(5)]
    assert [candidate["reading_order"] for candidate in candidates] == [
        item["reading_order"] for item in silver["items"]
    ]
    assert build_pages_meta(silver)["pages"]["1"]["item_ids"] == [
        candidate["id"] for candidate in candidates
    ]
    _assert_markdown_order(render_pages_md(silver)[1])


async def test_reading_order_survives_silver_persistence(ordered_document, tmp_path):
    store = FsDocStore(tmp_path)
    ingest = IngestService(
        store, MemoryEventBus(), extractor=FakePdfExtractor(_flatten(ordered_document)),
        renderer=FakePdfRenderer(page_count=1), polisher=FakePolisher(),
    )
    await ingest.ingest_pdf(b"%PDF-fake", "ordered.pdf", regions=False)

    candidates = await store.get_page_candidates("ordered", 1)
    meta = await store.get_pages_meta("ordered")
    raw = (tmp_path / "silver" / "ordered" / "pages" / "1.raw.md").read_text(encoding="utf-8")
    assert _names(candidates) == ["paragraph A", "table", "paragraph B", "picture", "paragraph C"]
    assert meta["pages"]["1"]["item_ids"] == [candidate["id"] for candidate in candidates]
    assert [candidate["reading_order"] for candidate in candidates] == sorted(
        candidate["reading_order"] for candidate in candidates
    )
    _assert_markdown_order(raw)


def test_legacy_item_ids_are_not_reassigned_when_projecting_order_metadata(ordered_document):
    silver = _flatten(ordered_document)
    # Older extraction output kept the separate texts/tables/pictures buckets.
    items = silver["items"]
    silver["items"] = [item for item in items if item["label"] == "text"] + [
        item for item in items if item["label"] != "text"
    ]
    original = deepcopy(silver)
    candidates = build_page_candidates(normalize_items(silver))[1]
    assert _names(candidates) == ["paragraph A", "paragraph B", "paragraph C", "table", "picture"]
    assert [candidate["id"] for candidate in candidates] == [f"p1-i{i}" for i in range(5)]
    assert [candidate["reading_order"] for candidate in candidates] == [
        item["reading_order"] for item in silver["items"]
    ]
    assert build_pages_meta(silver)["pages"]["1"]["item_ids"] == [
        candidate["id"] for candidate in candidates
    ]
    _assert_markdown_order(render_pages_md(silver)[1])
    assert silver == original


def test_extractor_without_ordered_traversal_keeps_legacy_collection_order(ordered_document):
    legacy = SimpleNamespace(texts=ordered_document.texts, tables=ordered_document.tables,
                             pictures=ordered_document.pictures, pages={})
    silver = _flatten(legacy)
    candidates = build_page_candidates(silver)[1]
    assert _names(candidates) == ["paragraph A", "paragraph B", "paragraph C", "table", "picture"]
    assert all("reading_order" not in candidate for candidate in candidates)
