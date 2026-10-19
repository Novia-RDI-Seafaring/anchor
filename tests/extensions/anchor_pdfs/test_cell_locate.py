"""A row citing a whole table gets the cell its value sits in."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.cell_locate import locate_cell


def _cell(row, col, text, *, row_header=False, column_header=False):
    return {"row": row, "col": col, "text": text,
            "row_header": row_header, "column_header": column_header}


# The Norrhavn PX "range at a glance" table: one column per model.
RANGE = [
    _cell(0, 0, "Pump model", column_header=True),
    _cell(0, 1, "PX-5", column_header=True),
    _cell(0, 2, "PX-10", column_header=True),
    _cell(1, 0, "Max flow (m 3 /h)", row_header=True),
    _cell(1, 1, "12"),
    _cell(1, 2, "25"),
    _cell(2, 0, "Max head (m)", row_header=True),
    _cell(2, 1, "24"),
    _cell(2, 2, "40"),
]


def test_finds_the_value_in_the_keyed_row():
    assert locate_cell(RANGE, "Max flow", "12 m³/h") == {"row": 1, "col": 1}
    assert locate_cell(RANGE, "Max head", "24 m") == {"row": 2, "col": 1}


def test_a_key_no_row_header_names_finds_nothing():
    assert locate_cell(RANGE, "Max inlet pressure", "6 bar") is None


def test_a_value_not_in_the_row_finds_nothing():
    assert locate_cell(RANGE, "Max flow", "24 m³/h") is None


def test_two_matching_cells_find_nothing():
    cells = [*RANGE, _cell(1, 3, "12")]
    assert locate_cell(cells, "Max flow", "12 m³/h") is None


def test_bad_input_finds_nothing():
    assert locate_cell(None, "Max flow", "12") is None
    assert locate_cell(RANGE, "", "12") is None
    assert locate_cell(RANGE, "Max flow", "twelve") is None


def test_a_row_citing_the_table_is_given_its_cell_on_write():
    import asyncio

    from anchor.extensions.anchor_pdfs.core.node_data import PdfNodeDataPreparer
    from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

    async def run():
        store = MemoryDocStore()
        cells = [{**c, "cell_id": f"c{i}",
                  "bbox": [10 * c["col"], 10 * c["row"], 10 * c["col"] + 9, 10 * c["row"] + 9]}
                 for i, c in enumerate(RANGE)]
        from anchor.extensions.anchor_pdfs.core.table_topology import (
            TOPOLOGY_VERSION, _digest,
        )

        topology = {"version": TOPOLOGY_VERSION, "status": "valid", "reason": "test",
                    "pairs": [], "digest": _digest(cells, [])}
        await store.write_gold_region_file("px", 1, [{
            "id": "r7", "kind": "table", "page": 1, "bbox": [0, 0, 40, 40],
            "cells": cells, "table_topology": topology,
        }])
        prepare = PdfNodeDataPreparer(store)
        ref = {"slug": "px", "page": 1, "region_id": "r7"}
        data = {"rows": [
            {"key": "Max flow", "value": "12 m³/h", "source_ref": ref},
            {"key": "Max inlet pressure", "value": "6 bar", "source_ref": ref},
        ]}
        out = await prepare(data, None)
        assert out["rows"][0]["source_ref"]["cell"] == {"row": 1, "col": 1}
        assert "cell" not in out["rows"][1]["source_ref"]
        # Located, not verified: the evidence verdict is the check's alone.
        assert out["rows"][0].get("evidence", {}).get("status") != "verified"

    asyncio.run(run())
