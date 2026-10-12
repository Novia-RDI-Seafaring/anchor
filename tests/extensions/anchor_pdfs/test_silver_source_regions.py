"""Original chunks reconstruct from uncapped silver without duplicating it."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.pointed_extraction import extract_pointed
from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content, inspect_region
from anchor.extensions.anchor_pdfs.core.silver import build_page_candidates, build_page_items
from anchor.extensions.anchor_pdfs.core.source_identity import SourceIdentityError
from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.fakes import FakePdfExtractor

LONG_TEXT = "Original paragraph " * 450 + " SILVER-TAIL-98765"


@pytest.fixture(params=["fs", "memory"])
def store(request, tmp_path):
    return FsDocStore(tmp_path) if request.param == "fs" else MemoryDocStore()


class SemanticRegions:
    def __init__(self, description=""):
        self.description = description

    async def extract_page(self, *, page_no, docling_items, **kwargs):
        return [{"id": f"r{i}", "kind": "table" if item["label"] == "table" else "text",
                 "title": "Source evidence", "description": self.description,
                 "tags": ["hydraulics"], "entities": ["PUMP-X"],
                 "page": page_no, "bbox": item["bbox"]}
                for i, item in enumerate(docling_items, 1)]


def text_document(label="paragraph", text=LONG_TEXT):
    return {"items": [{"label": label, "page": 1, "text": text,
                       "bbox": [10, 20, 200, 80], "reading_order": 0,
                       "group_path": ["chapter"], "source_id": "#/texts/0"}]}


def table_document(columns=2):
    cells = []
    for row, (key, value, other) in enumerate([
        ("Pressure", "17 bar", "UNSELECTED-COLUMN"),
        ("Temperature", "80 C", "UNSELECTED-COLUMN"),
        ("Speed", "2900 rpm", "UNSELECTED-SUBTABLE"),
    ]):
        for col, text in enumerate((key, value, other)):
            if col >= columns:
                continue
            cells.append({"row": row, "col": col, "text": text,
                          "row_span": 1, "col_span": 1,
                          "bbox": [10 + col * 60, 20 + row * 20,
                                   60 + col * 60, 35 + row * 20]})
    return {"items": [{"label": "table", "page": 1, "text": "",
                       "bbox": [10, 20, 180, 75], "cells": cells}]}


async def ingest_lane(store, tmp_path, document, lane, *, description="", regions=None):
    service = pipeline(store, [["page"]], extractor=FakePdfExtractor(document),
                       region_extractor=SemanticRegions(description))
    if lane != "harness":
        await service.ingest_pdf(b"source", "doc.pdf", profile="text" if lane == "text" else "keyed")
        return service
    sessions = FsIngestSessionStore(tmp_path / "sessions")
    harness = IngestSessionService(store, sessions, service.bus, extractor=service.extractor,
                                   renderer=service.renderer, embedder=service.embedder,
                                   embed_model_id="test")
    order = await harness.ingest_begin(b"source", "doc.pdf")
    session_id = order["session_id"]
    submitted = regions if regions is not None else [{
        "id": "r1", "kind": "text", "title": "Source evidence", "description": description,
        "member_item_ids": ["p1-i0"], "tags": ["hydraulics"], "entities": ["PUMP-X"],
    }]
    verdict = await harness.ingest_submit_page(session_id, 1, regions=submitted)
    assert verdict["accepted"], verdict
    staged = json.loads(await sessions.read_text(session_id, "gold/pages/1.regions.json"))["regions"]
    assert all(not {"content", "cells", "table_topology"}.intersection(r) for r in staged)
    assert (await harness.ingest_finalize(session_id))["finalized"]
    return service


@pytest.mark.parametrize("lane", ["keyed", "text", "harness"])
async def test_all_ingest_lanes_store_metadata_and_reconstruct_uncapped_source(store, tmp_path, lane):
    service = await ingest_lane(store, tmp_path, text_document(), lane)
    source = (await store.get_source_regions("doc"))["pages"][1][0]
    assert not {"content", "cells", "table_topology"}.intersection(source)
    assert source["member_item_ids"] == ["p1-i0"]
    assert len((await store.get_page_candidates("doc", 1))[0]["text"]) == 800
    evidence = (await store.get_page_items("doc", 1))[0]
    assert evidence["text"] == LONG_TEXT
    assert evidence["source_id"] == "#/texts/0"
    assert evidence["group_path"] == ["chapter"]
    reader = FsDocStore(tmp_path) if isinstance(store, FsDocStore) else store
    assert (await inspect_region(reader, "doc", f"p1/{source['id']}"))["content"] == LONG_TEXT
    assert (await get_region_content(reader, "doc", source["id"]))["content"] == LONG_TEXT
    assert "SILVER-TAIL-98765" in (await store.get_embeddings("doc"))["vectors"][0]["text"]
    assert (await service.search("SILVER-TAIL-98765"))["hits"]


@pytest.mark.parametrize("label", ["caption", "code", "formula", "table"])
async def test_meaningful_labels_reconstruct_the_full_text(store, tmp_path, label):
    await ingest_lane(store, tmp_path, text_document(label), "text")
    source = (await store.get_source_regions("doc"))["pages"][1][0]
    assert (await get_region_content(store, "doc", source["id"]))["content"] == LONG_TEXT


def test_full_item_ids_match_preview_traversal_without_reading_order_renumbering():
    document = {"items": [
        {"label": "text", "page": 2, "text": LONG_TEXT, "reading_order": 3},
        {"label": "text", "page": 1, "text": "First page", "reading_order": 0},
        {"label": "caption", "page": 2, "text": "Earlier in reading order", "reading_order": 1},
    ]}
    before = deepcopy(document)
    items, candidates = build_page_items(document), build_page_candidates(document)
    assert [i["id"] for i in items[2]] == [c["id"] for c in candidates[2]] == ["p2-i0", "p2-i1"]
    assert items[2][0]["text"] == LONG_TEXT
    assert document == before


async def test_described_source_uses_metadata_but_producer_content_stays_searchable(store, tmp_path):
    service = await ingest_lane(store, tmp_path, text_document(), "keyed", description="Rated operating limits")
    text = (await store.get_embeddings("doc"))["vectors"][0]["text"]
    assert text == "Source evidence\n\nRated operating limits\n\nhydraulics\n\nPUMP-X"
    assert "SILVER-TAIL-98765" not in text
    await service.derive_region("doc", "p1/r1", {
        "id": "curve", "kind": "chart_series", "title": "Curve", "description": "Digitized curve",
        "content": "PRODUCER-TAIL-123", "series": [{"points": [[0, 17]]}],
    })
    await service.embed_document("doc")
    vectors = (await store.get_embeddings("doc"))["vectors"]
    assert "PRODUCER-TAIL-123" in next(v["text"] for v in vectors if v["region_id"] == "curve")
    assert (await inspect_region(store, "doc", "p1/curve"))["data"]["series"] == [{"points": [[0, 17]]}]


async def test_table_slice_cells_pointed_extraction_and_refs_use_exact_silver_subset(store, tmp_path):
    await ingest_lane(store, tmp_path, table_document(), "harness", regions=[{
        "id": "limits", "kind": "spec_block", "title": "Operating limits",
        "table_slice": {"candidate_id": "p1-i0", "rows": [0, 1], "columns": [0, 1]},
    }])
    raw = (await store.get_source_regions("doc"))["pages"][1][0]
    assert not {"content", "cells", "table_topology"}.intersection(raw)
    inspected = await inspect_region(store, "doc", "p1/limits")
    assert inspected["bbox"] == [10, 20, 120, 55]
    assert {(c["row"], c["col"]) for c in inspected["cells"]} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert "UNSELECTED" not in inspected["content"]
    assert "Speed" not in inspected["content"]
    extracted = await extract_pointed(store=store, slug="doc", shape={"Pressure": "string", "Speed": "string"},
                                      select={"regions": ["p1/limits"]})
    assert extracted["data"] == {"Pressure": "17 bar", "Speed": None}
    assert extracted["provenance"]["/Pressure"]["bbox"] == [70, 20, 120, 35]
    claim = {"rows": [{"key": "Pressure", "value": "17 bar",
                       "source_ref": {"slug": "doc", "page": 1, "region_id": "limits"}}]}
    enriched = await enrich_spec_row_source_refs(claim, store)
    ref = enriched["rows"][0]["source_ref"]
    assert ref["cell"] == {"row": 0, "col": 1}
    assert (await resolve_source_ref(store, "doc", ref))["bbox"] == [70, 20, 120, 35]


async def test_column_slice_preserves_uncertified_pair_status(store, tmp_path):
    await ingest_lane(store, tmp_path, table_document(columns=3), "harness", regions=[{
        "id": "limits", "kind": "spec_block", "title": "Operating limits",
        "table_slice": {"candidate_id": "p1-i0", "rows": [0, 1], "columns": [0, 1]},
    }])
    inspected = await inspect_region(store, "doc", "limits")
    assert "UNSELECTED-COLUMN" not in inspected["content"]
    assert inspected["table_topology"]["pairs"] == []
    extracted = await extract_pointed(store=store, slug="doc", shape={"Pressure": "string"},
                                      select={"regions": ["limits"]})
    assert extracted["data"]["Pressure"] is None


async def test_full_silver_overrides_stale_source_payload_without_rewriting_gold(store, tmp_path):
    await ingest_lane(store, tmp_path, table_document(), "keyed")
    raw = (await store.get_source_regions("doc"))["pages"][1]
    await store.write_gold_region_file("doc", 1, [{**raw[0], "content": "FORGED SOURCE",
                                                 "cells": [{"row": 0, "col": 1, "text": "fake"}]}])
    before = deepcopy(await store.get_source_regions("doc"))
    inspected = await inspect_region(store, "doc", "p1/r1")
    assert "FORGED SOURCE" not in inspected["content"]
    assert inspected["cells"][1]["text"] == "17 bar"
    assert await store.get_source_regions("doc") == before


async def test_legacy_source_and_derived_payloads_remain_authoritative_without_full_silver(store):
    await store.write_silver_artifact("doc", "index.json", json.dumps({"document": {"page_count": 1}}))
    await store.write_gold_region_file("doc", 1, [
        {"id": "source", "kind": "text", "content": "Legacy source text"},
        {"id": "legacy", "kind": "chart_series", "derived_from": "p1/source",
         "content": {"points": [[1, 17]]}, "cells": [{"text": "producer value"}]},
    ])
    assert (await get_region_content(store, "doc", "source"))["content"] == "Legacy source text"
    assert (await get_region_content(store, "doc", "legacy"))["content"] == {"points": [[1, 17]]}
    assert (await inspect_region(store, "doc", "legacy"))["cells"] == [{"text": "producer value"}]


@pytest.mark.parametrize("corruption", ["missing", "ids", "page"])
async def test_new_replacement_rejects_incomplete_full_silver_and_keeps_old_generation(store, tmp_path, corruption):
    await ingest_lane(store, tmp_path, text_document(text="OLD SOURCE"), "keyed")
    old = store.snapshot("doc")
    service = pipeline(store, [["page"]], extractor=FakePdfExtractor(text_document(text="NEW SOURCE")))
    sessions = FsIngestSessionStore(tmp_path / "replacement-sessions")
    harness = IngestSessionService(store, sessions, service.bus, extractor=service.extractor,
                                   renderer=service.renderer, embedder=service.embedder)
    order = await harness.ingest_begin(b"replacement", "doc.pdf", force=True)
    session = json.loads(await sessions.read_text(order["session_id"], "session.json"))
    candidate = store.replacement("doc", session["generation"])
    verdict = await harness.ingest_submit_page(order["session_id"], 1, regions=[{
        "id": "new", "kind": "text", "title": "New", "member_item_ids": ["p1-i0"],
    }])
    assert verdict["accepted"]
    if corruption == "missing":
        if isinstance(candidate, FsDocStore):
            (candidate._doc_dir(candidate.silver, "doc") / "pages/1.items.json").unlink()
        else:
            candidate._items.pop(("doc", 1))
    else:
        items = await candidate.get_page_items("doc", 1)
        items[0]["id" if corruption == "ids" else "page"] = "p1-i9" if corruption == "ids" else 2
        await candidate.write_silver_artifact("doc", "pages/1.items.json", json.dumps(items))
    with pytest.raises((SourceIdentityError, ValueError), match="silver"):
        await harness.ingest_finalize(order["session_id"])
    assert (await inspect_region(store, "doc", "r1"))["content"] == "OLD SOURCE"
    assert (await old.get_page_items("doc", 1))[0]["text"] == "OLD SOURCE"


async def test_pinned_full_items_and_region_content_survive_successful_replacement(store, tmp_path):
    await ingest_lane(store, tmp_path, text_document(text="OLD SOURCE"), "keyed")
    old = store.snapshot("doc")
    await pipeline(store, [["NEW SOURCE"]], region_extractor=SemanticRegions()).ingest_pdf(
        b"replacement", "doc.pdf", force=True,
    )
    assert (await inspect_region(store, "doc", "r1"))["content"] == "NEW SOURCE"
    assert (await inspect_region(old, "doc", "r1"))["content"] == "OLD SOURCE"
    assert (await old.get_page_items("doc", 1))[0]["text"] == "OLD SOURCE"
