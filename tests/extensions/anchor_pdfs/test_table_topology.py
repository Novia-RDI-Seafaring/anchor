"""Table semantics must survive the real adapter/normalization/gold seams."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from anchor.extensions.anchor_pdfs.core.gold_ingest import GoldIngest
from anchor.extensions.anchor_pdfs.core.ingest.region_resolution import resolve_regions
from anchor.extensions.anchor_pdfs.core.pointed_extraction import fill_shape
from anchor.extensions.anchor_pdfs.core.silver import build_page_candidates, normalize_items
from anchor.extensions.anchor_pdfs.core.table_topology import topology_status, validated_pairs
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import _flatten


def _cell(row, col, text, bbox, **flags):
    """A minimal raw Docling cell, before ANCHOR has interpreted topology."""
    row_span = flags.pop("row_span", 1)
    col_span = flags.pop("col_span", 1)
    return SimpleNamespace(
        start_row_offset_idx=row,
        end_row_offset_idx=row + row_span,
        start_col_offset_idx=col,
        end_col_offset_idx=col + col_span,
        row_span=row_span,
        col_span=col_span,
        text=text,
        bbox=SimpleNamespace(l=bbox[0], t=bbox[1], r=bbox[2], b=bbox[3], coord_origin="TOPLEFT"),
        column_header=flags.get("column_header", False),
        row_header=flags.get("row_header", False),
        row_section=flags.get("row_section", False),
    )


def _doc(cells, rows, cols):
    return SimpleNamespace(
        pages={1: SimpleNamespace(size=SimpleNamespace(width=600, height=800))},
        texts=[],
        pictures=[],
        tables=[
            SimpleNamespace(
                prov=[
                    SimpleNamespace(
                        page_no=1,
                        bbox=SimpleNamespace(l=0, t=0, r=500, b=180, coord_origin="TOPLEFT"),
                    )
                ],
                data=SimpleNamespace(table_cells=cells, num_rows=rows, num_cols=cols),
            )
        ],
    )


def _shifted_table():
    # Redistributable synthetic equivalent of the LKH failure. The value
    # column has a missing heading slot, a false header flag, and displaced
    # indexes. The last row is already correct, so a global shift cannot work.
    return _doc(
        [
            _cell(0, 0, "Operating limits", [10, 10, 130, 18]),
            _cell(1, 0, "Series A pressure:", [10, 30, 140, 38]),
            _cell(0, 1, "500 kPa", [250, 30, 300, 38], column_header=True),
            _cell(2, 0, "Series B pressure:", [10, 50, 140, 58]),
            _cell(1, 1, "300 kPa", [250, 50, 300, 58]),
            _cell(3, 0, "Consumption", [10, 70, 140, 78]),
            _cell(3, 1, "0.5 l/min", [250, 70, 310, 78]),
        ],
        4,
        2,
    )


def _gold(doc, path):
    silver = normalize_items(_flatten(doc))
    if path == "keyed":
        regions = GoldIngest._snap_regions(
            silver,
            1,
            [
                {
                    "id": "limits",
                    "kind": "table",
                    "title": "Limits",
                    "page": 1,
                    "bbox": [0, 0, 500, 180],
                }
            ],
        )
    else:
        candidates = build_page_candidates(silver)[1]
        regions, errors = resolve_regions(
            page=1,
            candidates=candidates,
            regions=[
                {
                    "id": "limits",
                    "kind": "table",
                    "title": "Limits",
                    "member_item_ids": [candidates[0]["id"]],
                }
            ],
        )
        assert not errors
    return silver, regions


@pytest.mark.parametrize("path", ["keyed", "harness"])
def test_shifted_value_indexes_are_reconciled_before_gold_and_extraction(path):
    silver, regions = _gold(_shifted_table(), path)
    data, refs, unfilled = fill_shape(
        {"Series A pressure": "quantity", "Series B pressure": "quantity"},
        regions,
        slug="synthetic",
    )
    assert data == {"Series A pressure": "500 kPa", "Series B pressure": "300 kPa"}
    assert unfilled == []
    assert refs["/Series A pressure"]["bbox"] == [250, 30, 300, 38]
    assert refs["/Series B pressure"]["bbox"] == [250, 50, 300, 58]
    assert (
        refs["/Series A pressure"]["detail"]["table_topology"]["association_basis"]
        == "explicit_label_value"
    )
    assert (
        refs["/Series B pressure"]["detail"]["table_topology"]["association_basis"]
        == "validated_row"
    )
    assert all(ref["page"] == 1 and ref["region_id"] == "limits" for ref in refs.values())
    assert silver["items"][0]["table_topology"]["status"] == "reconciled"
    assert regions[0]["table_topology"] == silver["items"][0]["table_topology"]


def test_unvalidated_old_gold_does_not_create_an_association():
    # Old cells, including apparently ordinary ones, lack an upstream verdict.
    legacy = _flatten(_shifted_table())["items"][0]
    data, refs, unfilled = fill_shape({"Series A pressure": "quantity"}, [legacy], slug="old")
    assert data == {"Series A pressure": None}
    assert refs == {}
    assert unfilled == ["/Series A pressure"]


def test_preserves_extractor_structure_and_normalization_is_idempotent():
    raw = _flatten(_shifted_table())
    value = raw["items"][0]["cells"][2]
    assert (value["row"], value["row_end"], value["row_span"], value["column_header"]) == (
        0,
        1,
        1,
        True,
    )
    original = deepcopy(raw)
    silver = normalize_items(raw)
    assert raw == original
    assert normalize_items(silver) == silver
    assert silver["items"][0]["cells"] == silver["tables"][0]["cells"]
    value = silver["items"][0]["cells"][2]
    assert (value["row"], value["row_end"], value["column_header"]) == (1, 2, True)
    assert value["source_structure"]["row"] == 0
    assert value["source_structure"]["column_header"] is True
    assert value["bbox"] == original["items"][0]["cells"][2]["bbox"]


@pytest.mark.parametrize("path", ["keyed", "harness"])
def test_ordinary_table_and_headers(path):
    doc = _doc(
        [
            _cell(0, 0, "Parameter", [10, 10, 120, 18], column_header=True),
            _cell(0, 1, "Value", [250, 10, 310, 18], column_header=True),
            _cell(1, 0, "Pressure", [10, 30, 120, 38], row_header=True),
            _cell(1, 1, "500 kPa", [250, 30, 310, 38]),
        ],
        2,
        2,
    )
    silver, regions = _gold(doc, path)
    data, refs, unfilled = fill_shape(
        {"Parameter": "string", "Pressure": "quantity"}, regions, slug="x"
    )
    assert data == {"Parameter": None, "Pressure": "500 kPa"}
    assert unfilled == ["/Parameter"]
    assert refs["/Pressure"]["bbox"] == [250, 30, 310, 38]
    assert topology_status(silver["items"][0])["status"] == "valid"


@pytest.mark.parametrize("path", ["keyed", "harness"])
def test_full_width_merged_header_preserves_spans(path):
    doc = _doc(
        [
            _cell(0, 0, "Limits", [10, 10, 300, 18], col_span=2, column_header=True),
            _cell(1, 0, "Pressure", [10, 30, 120, 38]),
            _cell(1, 1, "500 kPa", [250, 30, 310, 38]),
        ],
        2,
        2,
    )
    silver, regions = _gold(doc, path)
    assert regions[0]["cells"][0]["col_span"] == 2
    assert regions[0]["cells"][0]["col_end"] == 2
    assert fill_shape({"Limits": "string", "Pressure": "string"}, regions, slug="x")[0] == {
        "Limits": None,
        "Pressure": "500 kPa",
    }
    assert topology_status(silver["items"][0])["status"] == "valid"


def test_column_spanning_value_is_one_cell_not_two_values():
    doc = _doc(
        [
            _cell(0, 0, "Pressure", [10, 10, 120, 18]),
            _cell(0, 1, "500 kPa", [200, 10, 400, 18], col_span=2),
        ],
        1,
        3,
    )
    _, regions = _gold(doc, "harness")
    data, refs, _ = fill_shape({"Pressure": "quantity"}, regions, slug="x")
    assert data == {"Pressure": "500 kPa"}
    assert refs["/Pressure"]["bbox"] == [200, 10, 400, 18]
    assert regions[0]["cells"][1]["col_span"] == 2


@pytest.mark.parametrize("merged_column", [0, 1])
def test_row_span_preserved_but_scalar_shape_abstains(merged_column):
    # Row-spanning labels/values are retained, not copied into fake cells.
    doc = _doc(
        [
            _cell(
                0,
                merged_column,
                "Shared",
                [10 + 240 * merged_column, 16, 100 + 240 * merged_column, 33],
                row_span=2,
            ),
            _cell(
                0,
                1 - merged_column,
                "A",
                [10 + 240 * (1 - merged_column), 10, 100 + 240 * (1 - merged_column), 18],
            ),
            _cell(
                1,
                1 - merged_column,
                "B",
                [10 + 240 * (1 - merged_column), 30, 100 + 240 * (1 - merged_column), 38],
            ),
        ],
        2,
        2,
    )
    _, regions = _gold(doc, "harness")
    assert topology_status(regions[0])["status"] == "valid"
    assert regions[0]["cells"][0]["row_span"] == 2
    assert validated_pairs(regions[0]) == []
    assert (
        fill_shape({"Shared": "string", "A": "string", "B": "string"}, regions, slug="x")[1] == {}
    )


def test_multicolumn_scalar_query_does_not_choose_first_value():
    doc = _doc(
        [
            _cell(0, 0, "Pressure", [10, 10, 120, 18]),
            _cell(0, 1, "500 kPa", [200, 10, 260, 18]),
            _cell(0, 2, "300 kPa", [350, 10, 410, 18]),
        ],
        1,
        3,
    )
    silver, regions = _gold(doc, "harness")
    assert topology_status(regions[0])["status"] == "valid"
    assert fill_shape({"Pressure": "string"}, regions, slug="x")[0] == {"Pressure": None}
    candidates = build_page_candidates(silver)[1]
    sliced, errors = resolve_regions(
        page=1,
        candidates=candidates,
        regions=[
            {
                "id": "slice",
                "kind": "table",
                "title": "Subset",
                "table_slice": {
                    "candidate_id": candidates[0]["id"],
                    "rows": [0],
                    "columns": [0, 1],
                },
            }
        ],
    )
    assert not errors
    # Slicing cannot manufacture a pair that the original table did not prove.
    assert validated_pairs(sliced[0]) == []


def test_wrapped_labels_and_duplicate_unit_values_keep_physical_identity():
    doc = _doc(
        [
            _cell(0, 0, "Operating\npressure A", [10, 10, 140, 28]),
            _cell(0, 1, "500 kPa", [250, 15, 310, 23]),
            _cell(1, 0, "Operating\npressure B", [10, 40, 140, 58]),
            _cell(1, 1, "500 kPa", [250, 45, 310, 53]),
        ],
        2,
        2,
    )
    _, regions = _gold(doc, "keyed")
    data, refs, missing = fill_shape(
        {"Operating pressure A": "string", "Operating pressure B": "string"}, regions, slug="x"
    )
    assert not missing
    assert set(data.values()) == {"500 kPa"}
    assert refs["/Operating pressure A"]["bbox"] == [250, 15, 310, 23]
    assert refs["/Operating pressure B"]["bbox"] == [250, 45, 310, 53]
    assert refs["/Operating pressure A"]["detail"]["table_topology"]["key_bbox"] == [
        10,
        10,
        140,
        28,
    ]


def test_equal_key_and_value_at_distinct_sources_remains_ambiguous():
    doc = _doc(
        [
            _cell(0, 0, "Pressure", [10, 10, 120, 18]),
            _cell(0, 1, "500 kPa", [250, 10, 310, 18]),
            _cell(1, 0, "Pressure", [10, 30, 120, 38]),
            _cell(1, 1, "500 kPa", [250, 30, 310, 38]),
        ],
        2,
        2,
    )
    _, regions = _gold(doc, "harness")
    assert len(validated_pairs(regions[0])) == 2
    assert fill_shape({"Pressure": "string"}, regions, slug="x")[0] == {"Pressure": None}


@pytest.mark.parametrize(
    "defect",
    [
        "two_rows",
        "no_overlap",
        "column_crossing",
        "span_collision",
        "missing_bbox",
        "conflicting_header",
    ],
)
def test_ambiguous_or_invalid_tables_abstain(defect):
    doc = _shifted_table()
    cells = doc.tables[0].data.table_cells
    if defect == "two_rows":
        cells[2].bbox.t, cells[2].bbox.b = 30, 58
    elif defect == "no_overlap":
        cells[2].bbox.t, cells[2].bbox.b = 39, 47
    elif defect == "column_crossing":
        cells[2].bbox.l = 100
    elif defect == "span_collision":
        cells[0].row_span, cells[0].end_row_offset_idx = 2, 2
    elif defect == "missing_bbox":
        cells[2].bbox = None
    else:
        cells[0].column_header = True
    _, regions = _gold(doc, "harness")
    assert topology_status(regions[0])["status"] in {"ambiguous", "invalid"}
    assert fill_shape({"Series A pressure": "string"}, regions, slug="x")[0] == {
        "Series A pressure": None
    }
    assert "unassociated" in regions[0]["content"]
    assert "| Series A pressure | 300 kPa |" not in regions[0]["content"]


def test_post_validation_edits_invalidate_cell_pair_proof():
    _, regions = _gold(_shifted_table(), "harness")
    regions[0]["cells"][2]["bbox"] = [250, 50, 300, 58]
    assert topology_status(regions[0])["status"] == "unvalidated"
    assert validated_pairs(regions[0]) == []


def test_coverage_and_span_aware_slice_preserve_certification():
    from anchor.extensions.anchor_pdfs.core.ingest.coverage import synthesize_coverage_regions

    silver = normalize_items(
        _flatten(
            _doc(
                [
                    _cell(0, 0, "Pressure", [10, 10, 120, 18]),
                    _cell(0, 1, "500 kPa", [200, 10, 400, 18], col_span=2),
                ],
                1,
                3,
            )
        )
    )
    candidates = build_page_candidates(silver)[1]
    regions = synthesize_coverage_regions(1, candidates, [])
    assert len(validated_pairs(regions[0])) == 1
    sliced, errors = resolve_regions(
        page=1,
        candidates=candidates,
        regions=[
            {
                "id": "slice",
                "kind": "table",
                "title": "Subset",
                "table_slice": {"candidate_id": candidates[0]["id"], "rows": [0], "columns": [2]},
            }
        ],
    )
    assert not errors
    assert len(sliced[0]["cells"]) == 1
    assert sliced[0]["cells"][0]["col_span"] == 2
    assert validated_pairs(sliced[0]) == []


@pytest.mark.parametrize("cells", [None, [None], [], [{"row": 0, "col": 1, "text": "500 kPa"}]])
async def test_value_refinement_preserves_unvalidated_or_malformed_old_gold(cells):
    from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs
    from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

    store = MemoryDocStore()
    await store.write_gold_region_file(
        "old", 1, [{"id": "limits", "kind": "table", "cells": cells}]
    )
    data = {
        "rows": [
            {
                "key": "Pressure",
                "value": "500 kPa",
                "source_ref": {
                    "slug": "old",
                    "page": 1,
                    "region_id": "limits",
                    "bbox": [10, 10, 100, 100],
                },
            }
        ]
    }
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_stale_pointed_extraction_reports_reingest_remedy():
    import json

    from anchor.extensions.anchor_pdfs.core.pointed_extraction import extract_pointed
    from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

    store = MemoryDocStore()
    await store.write_silver_artifact(
        "old", "index.json", json.dumps({"document": {"page_count": 1}})
    )
    await store.write_gold_region_file(
        "old", 1, [{**_flatten(_shifted_table())["items"][0], "id": "limits"}]
    )
    await store.mark_gold_complete("old", {"mode": "harness"})
    result = await extract_pointed(
        store=store, slug="old", select=None, shape={"Series A pressure": "quantity"}
    )
    assert result["data"] == {"Series A pressure": None}
    assert result["table_warnings"][0]["status"] == "unvalidated"
    assert "re-ingest" in result["table_warnings"][0]["reason"]


def test_invalid_span_metadata_is_inspectable_but_cannot_be_sliced():
    raw = _flatten(_shifted_table())
    raw["items"][0]["cells"][2]["row_end"] = None
    candidates = build_page_candidates(normalize_items(raw))[1]
    assert candidates[0]["table_topology"]["status"] == "invalid"
    regions, errors = resolve_regions(
        page=1,
        candidates=candidates,
        regions=[
            {
                "id": "slice",
                "kind": "table",
                "title": "Subset",
                "table_slice": {"candidate_id": candidates[0]["id"], "rows": [1]},
            }
        ],
    )
    assert regions == []
    assert errors[0]["field"] == "table_slice"


def test_rectangular_merged_cell_retains_both_spans_without_fabricated_pairs():
    doc = _doc(
        [
            _cell(0, 0, "Group", [10, 16, 250, 33], row_span=2, col_span=2),
            _cell(0, 2, "A", [350, 10, 410, 18]),
            _cell(1, 2, "B", [350, 30, 410, 38]),
        ],
        2,
        3,
    )
    _, regions = _gold(doc, "harness")
    assert topology_status(regions[0])["status"] == "valid"
    assert len(regions[0]["cells"]) == 3
    assert regions[0]["cells"][0]["row_span"] == regions[0]["cells"][0]["col_span"] == 2
    assert fill_shape({"Group": "string"}, regions, slug="x")[0] == {"Group": None}


def test_two_row_headers_do_not_form_a_key_value_pair():
    _, regions = _gold(
        _doc(
            [
                _cell(0, 0, "First category", [10, 10, 150, 18], row_header=True),
                _cell(0, 1, "Second category", [250, 10, 400, 18], row_header=True),
            ],
            1,
            2,
        ),
        "harness",
    )
    assert validated_pairs(regions[0]) == []


def test_displaced_genuine_partial_header_is_not_reclassified_as_data():
    doc = _doc(
        [
            _cell(0, 0, "Operating limits", [10, 10, 130, 18]),
            _cell(1, 0, "Parameter", [10, 30, 140, 38]),
            _cell(0, 1, "Model A", [250, 30, 310, 38], column_header=True),
            _cell(2, 0, "Pressure", [10, 50, 140, 58]),
            _cell(1, 1, "500 kPa", [250, 50, 310, 58]),
            _cell(3, 0, "Temperature", [10, 70, 140, 78]),
            _cell(3, 1, "80 C", [250, 70, 310, 78]),
        ],
        4,
        2,
    )
    _, regions = _gold(doc, "harness")
    assert topology_status(regions[0])["status"] == "ambiguous"
    assert fill_shape({"Parameter": "string"}, regions, slug="x")[0] == {"Parameter": None}
    assert regions[0]["cells"][2]["column_header"] is True


def test_lost_span_metadata_does_not_become_an_ordinary_single_row_cell():
    raw = _flatten(_shifted_table())
    for cell in raw["items"][0]["cells"]:
        cell.pop("row_span")
        cell.pop("col_span")
    table = normalize_items(raw)["items"][0]
    assert topology_status(table)["status"] == "ambiguous"
    assert "span provenance" in topology_status(table)["reason"]
    assert validated_pairs(table) == []


@pytest.mark.parametrize("text", [None, 42])
def test_invalid_non_text_cells_remain_inspectable(text):
    doc = _shifted_table()
    doc.tables[0].data.table_cells[2].text = text
    _, regions = _gold(doc, "harness")
    assert topology_status(regions[0])["status"] not in {"valid", "reconciled"}
    assert fill_shape({"Series A pressure": "string"}, regions, slug="x")[0] == {
        "Series A pressure": None,
    }
