"""Opt-in real PX-42 extraction and actual HTTP/MCP/CLI source workflows."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pymupdf
import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from typer.testing import CliRunner

from anchor.adapters.cli import documents as cli_documents
from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp.server import build_mcp_server
from anchor.extensions.anchor_pdfs.core.ingest.coverage import coverage_stats
from anchor.extensions.anchor_pdfs.core.pointed_extraction import extract_pointed
from anchor.extensions.anchor_pdfs.core.region_inspect import inspect_region
from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs
from tests.fixtures.documents.px42 import PDF, SHA256, SLUG, build_px42_runtime

pytestmark = pytest.mark.slow
QUERY = "maximum inlet pressure 600 kPa"
SHAPE = {"maximum_inlet_pressure": "string", "process_temperature_range": "string"}


@pytest.fixture(scope="module")
def px42_runtime(tmp_path_factory):
    with pytest.MonkeyPatch.context() as context:
        context.setenv("HF_HUB_OFFLINE", "1")
        context.setenv("TRANSFORMERS_OFFLINE", "1")
        runtime = build_px42_runtime(tmp_path_factory.mktemp("px42-real"))
        result = asyncio.run(runtime.ingest.ingest_pdf(PDF.read_bytes(), PDF.name, slug=SLUG, profile="text"))
        assert result["page_count"] == 4
        assert result["region_count"] == result["embedded_count"] > 0
        assert result["invalid_region_count"] == 0
        yield runtime


def _source_hit(runtime):
    hits = asyncio.run(runtime.ingest.search(QUERY, k=1))["hits"]
    assert hits[0]["slug"] == SLUG and hits[0]["page"] == 2
    return f"p2/{hits[0]['region_id']}"


def test_real_px42_source_identity_complete_coverage_and_stable_membership(px42_runtime):
    store = px42_runtime.doc_store
    index = asyncio.run(store.get_index(SLUG))
    assert index["document"]["source"] == {"slug": SLUG, "sha256": SHA256}
    assert index["document"]["page_count"] == 4
    assert index["document"]["title"] == "SYNTHETIC PX-42"
    source = asyncio.run(store.get_source_regions(SLUG))["pages"]
    assert set(source) == {1, 2, 3, 4}
    for page, regions in source.items():
        candidates = asyncio.run(store.get_page_candidates(SLUG, page))
        items = asyncio.run(store.get_page_items(SLUG, page))
        ids = [f"p{page}-i{i}" for i in range(len(items))]
        assert [item["id"] for item in items] == [candidate["id"] for candidate in candidates] == ids
        assert coverage_stats(candidates, regions)["uncovered_items"] == 0
        assert all(not {"content", "cells", "table_topology"}.intersection(region) for region in regions)
        assert all(set(region["member_item_ids"]).issubset(ids) for region in regions)
        assert asyncio.run(store.get_page_image_path(SLUG, page)).is_file()


def test_real_px42_operating_values_resolve_to_their_physical_source_cells(px42_runtime):
    store = px42_runtime.doc_store
    locator = _source_hit(px42_runtime)
    inspected = asyncio.run(inspect_region(store, SLUG, locator))
    assert "600 kPa (6 bar)" in inspected["content"]
    assert "-10 to 140 degrees C" in inspected["content"]
    extracted = asyncio.run(extract_pointed(store=store, slug=SLUG, select={"regions": [locator]}, shape=SHAPE))
    assert extracted["data"] == {"maximum_inlet_pressure": "600 kPa (6 bar)",
                                  "process_temperature_range": "-10 to 140 degrees C"}
    assert extracted["unfilled"] == []
    claim = {"rows": [{"key": "Maximum inlet pressure", "value": "600 kPa (6 bar)",
                       "source_ref": extracted["provenance"]["/maximum_inlet_pressure"]}]}
    ref = asyncio.run(enrich_spec_row_source_refs(claim, store))["rows"][0]["source_ref"]
    cell = next(cell for cell in inspected["cells"] if cell["text"] == "600 kPa (6 bar)")
    assert ref["cell"] == {"row": cell["row"], "col": cell["col"]}
    resolved = asyncio.run(resolve_source_ref(store, SLUG, ref))
    assert resolved["page"] == 2 and resolved["precision"] == "cell"
    assert resolved["bbox"] == cell["bbox"]
    assert resolved["bbox"] != inspected["bbox"]
    with pymupdf.open(PDF) as document:
        for field, expected in extracted["data"].items():
            source = extracted["provenance"]["/" + field]
            assert source["page"] == 2
            # Independent PDF glyph check. Two points allow differing font
            # leading while still excluding the adjacent key and table rows.
            glyph_box = pymupdf.Rect(source["bbox"]) + (-2, -2, 2, 2)
            actual = document[source["page"] - 1].get_textbox(glyph_box)
            assert " ".join(actual.split()) == expected
        physical = document[1].search_for("600 kPa (6 bar)")
        assert len(physical) == 1
        source_box = pymupdf.Rect(cell["bbox"])
        assert source_box.contains((physical[0].tl + physical[0].br) / 2)
        assert (source_box & physical[0]).get_area() / physical[0].get_area() > 0.75


def test_real_px42_multicolumn_performance_never_invents_scalar_pairings(px42_runtime):
    regions = asyncio.run(px42_runtime.doc_store.get_regions(SLUG, 3))["pages"][3]
    tables = [region for region in regions if region.get("cells")]
    assert len(tables) == 1
    table = tables[0]
    assert max(cell["col"] for cell in table["cells"]) == 4
    assert "1200" in table["content"] and "7.8" in table["content"]
    assert table["table_topology"]["pairs"] == []
    extracted = asyncio.run(extract_pointed(store=px42_runtime.doc_store, slug=SLUG,
        select={"regions": [f"p3/{table['id']}"]},
        shape={"Speed": "string", "Flow": "string", "Head": "string", "Efficiency": "string"}))
    assert all(value is None for value in extracted["data"].values())
    assert extracted["provenance"] == {}
    assert len(extracted["unfilled"]) == 4


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_real_px42_search_inspect_extract_and_cell_resolution_across_adapters(px42_runtime, transport, monkeypatch):
    runtime = px42_runtime
    server = build_mcp_server(bundle=runtime) if transport == "mcp" else None
    if transport == "cli":
        monkeypatch.setattr(cli_documents, "_build_real_services", lambda *_args, **_kwargs:
            (runtime.config, runtime.bus, runtime.workspace, runtime.ingest, runtime.doc_store))

    def invoke(operation, *, locator=None, ref=None):
        if transport == "http":
            with TestClient(build_app(runtime)) as client:
                if operation == "search":
                    response = client.get("/api/documents/_search", params={"q": QUERY, "k": 1})
                elif operation == "inspect":
                    response = client.get(f"/api/documents/{SLUG}/regions/{locator}")
                elif operation == "extract":
                    response = client.post(f"/api/documents/{SLUG}/extract", json={"select": {"regions": [locator]}, "shape": SHAPE})
                else:
                    response = client.get(f"/api/documents/{SLUG}/resolve-ref", params={
                        "page": ref["page"], "region_id": ref["region_id"], "row": ref["cell"]["row"], "col": ref["cell"]["col"]})
                assert response.status_code == 200, response.text
                return response.json()
        if transport == "mcp":
            async def call():
                names = {"search": "search_documents", "inspect": "inspect_region", "extract": "extract_pointed", "resolve": "resolve_source_ref"}
                arguments = {"query": QUERY, "k": 1} if operation == "search" else {"slug": SLUG}
                if operation == "inspect":
                    arguments["region_id"] = locator
                elif operation == "extract":
                    arguments.update({"select": {"regions": [locator]}, "shape": SHAPE})
                elif operation == "resolve":
                    arguments["ref"] = ref
                async with Client(server) as client:
                    result = await client.call_tool(names[operation], arguments)
                output = json.loads(result.content[0].text)
                assert "error" not in output, output
                return output
            return asyncio.run(call())
        shape = runtime.config.data_dir / "adapter-shape.json"
        shape.write_text(json.dumps(SHAPE), encoding="utf-8")
        args = {"search": ["search", QUERY, "--k", "1"],
                "inspect": ["inspect-region", SLUG, locator or ""],
                "extract": ["extract", SLUG, "--shape", str(shape), "--region", locator or ""],
                "resolve": ["resolve-ref", SLUG, "--ref", json.dumps(ref)]}[operation]
        result = CliRunner().invoke(cli_app, [*args, "--data-dir", str(runtime.config.data_dir)])
        assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
        return json.loads(result.stdout)

    hit = invoke("search")["hits"][0]
    assert hit["slug"] == SLUG and hit["page"] == 2
    locator = f"p2/{hit['region_id']}"
    inspected = invoke("inspect", locator=locator)
    assert "600 kPa (6 bar)" in inspected["content"]
    assert "-10 to 140 degrees C" in inspected["content"]
    extracted = invoke("extract", locator=locator)
    assert extracted["data"]["maximum_inlet_pressure"] == "600 kPa (6 bar)"
    assert extracted["data"]["process_temperature_range"] == "-10 to 140 degrees C"
    cell = next(cell for cell in inspected["cells"] if cell["text"] == "600 kPa (6 bar)")
    resolved = invoke("resolve", ref={"page": 2, "region_id": hit["region_id"], "cell": {"row": cell["row"], "col": cell["col"]}})
    assert resolved["page"] == 2 and resolved["precision"] == "cell"
    assert resolved["bbox"] == cell["bbox"]
    if transport == "http":
        with TestClient(build_app(runtime)) as client:
            assert hashlib.sha256(client.get(f"/api/documents/{SLUG}/pdf").content).hexdigest() == SHA256
