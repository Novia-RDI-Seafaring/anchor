"""`list_entities` — what a document is about.

An agent reported a four-page leaflet as "the only pump in the corpus" after
checking one model. The leaflet names thirteen, and the gold layer knew all
thirteen; nothing in the read surface would tell it so.
"""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.entities import list_entities
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore


class FakeStore:
    """Only `get_regions` matters here."""

    def __init__(self, pages):
        self._pages = pages

    async def get_regions(self, slug, page=None):
        return {"slug": slug, "pages": self._pages}


PAGES = {
    1: [
        {"id": "r1", "entities": ["LKH-5", "LKH-10"]},
        {"id": "r2", "entities": ["LKH-5"]},
    ],
    2: [
        {"id": "r1", "entities": ["LKH-5", "LKH-90"]},
        {"id": "r2", "entities": []},
    ],
}


def _run(pages=PAGES, slug="lkh"):
    return asyncio.run(list_entities(FakeStore(pages), slug))


def test_counts_every_mention():
    out = _run()
    counts = {e["name"]: e["count"] for e in out["entities"]}
    assert counts == {"LKH-5": 3, "LKH-10": 1, "LKH-90": 1}
    assert out["entity_count"] == 3
    assert out["slug"] == "lkh"


def test_sorted_by_frequency_then_name_for_a_stable_order():
    names = [e["name"] for e in _run()["entities"]]
    assert names == ["LKH-5", "LKH-10", "LKH-90"]


def test_records_where_each_entity_appears():
    by_name = {e["name"]: e for e in _run()["entities"]}
    assert by_name["LKH-5"]["pages"] == [1, 2]
    assert by_name["LKH-5"]["region_ids"] == ["p1/r1", "p1/r2", "p2/r1"]
    assert by_name["LKH-90"]["pages"] == [2]


def test_a_document_with_no_gold_reports_zero_rather_than_failing():
    # Silver-only is a normal state, not an error.
    out = _run(pages={})
    assert out["entity_count"] == 0
    assert out["entities"] == []


def test_junk_entries_are_ignored():
    out = _run(pages={1: [{"id": "r1", "entities": ["", "  ", None, 7, "Real"]}]})
    assert [e["name"] for e in out["entities"]] == ["Real"]


def test_malformed_regions_do_not_crash():
    out = _run(pages={1: [None, "nope", {"id": "r1"}], 2: None})
    assert out["entity_count"] == 0


def test_string_page_keys_from_json_are_handled():
    out = _run(pages={"1": [{"id": "r1", "entities": ["X"]}]})
    assert out["entities"][0]["pages"] == [1]


def test_nothing_is_truncated_or_ranked_away():
    # A "top N covers" preview would have to break the tie between a real
    # model and a letter from a code legend, both named once. Return all.
    pages = {1: [{"id": f"r{i}", "entities": [f"E{i}"]} for i in range(30)]}
    assert _run(pages=pages)["entity_count"] == 30


def test_reaches_mcp_http_and_cli():
    from anchor.adapters.operation_descriptors import DOCUMENT_OPERATION_DESCRIPTORS

    op = next(
        o for o in DOCUMENT_OPERATION_DESCRIPTORS if o.id == "document.list_entities"
    )
    assert op.mcp_tool == "list_entities"
    assert op.http.path == "/api/documents/{slug}/entities"
    assert op.cli_command == ("entities",)


def test_the_mcp_tool_is_advertised_by_default():
    from anchor.adapters.mcp.tiering import CORE_NAMES

    # A count an agent cannot act on is a tease; this is the acting-on tool.
    assert "list_entities" in CORE_NAMES


def test_mcp_handler_returns_the_payload():
    from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    store: MemoryDocStore = services.doc_store

    async def run():
        await store.write_gold_region_file(
            "lkh", 1, [{"id": "r1", "entities": ["LKH-5"], "bbox": [0, 0, 1, 1]}]
        )
        return json.loads(
            await call_tool(services.ingest, store, "list_entities", {"slug": "lkh"})
        )

    out = asyncio.run(run())
    assert out["slug"] == "lkh"
    assert [e["name"] for e in out["entities"]] == ["LKH-5"]
