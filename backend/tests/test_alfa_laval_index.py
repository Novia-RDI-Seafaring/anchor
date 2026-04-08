"""End-to-end-ish test: build_index against the real alfa-laval docling.json.

Pins the things the agent actually relies on for that doc — it's our
canonical reference document and regressions here would silently break
the LKH workflow on the canvas.
"""
import json
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.silver import build_index

SILVER = Path(__file__).resolve().parents[1] / "data" / "silver" / "alfa-laval-lkh-centrifugal-pump"

Index = dict[str, Any]
Table = dict[str, Any]


@pytest.fixture(scope="module")
def index() -> Index:
    docling = json.loads((SILVER / "docling.json").read_text())
    return build_index(docling, filename="alfa-laval-lkh-centrifugal-pump.pdf")


def test_document_meta(index: Index):
    assert index["document"]["filename"] == "alfa-laval-lkh-centrifugal-pump.pdf"
    assert index["document"]["page_count"] == 4


def test_outline_has_key_sections(index: Index):
    titles = [o["title"] for o in index["outline"]]
    for needed in [
        "TECHNICAL DATA",
        "OPERATING DATA",
        "Motor",
        "Dimensions",
        "Pump specific measures (mm)",
        "Motor specific measures (mm)",
        "Motor overview",
        "Connections (mm)",
        "Flow chart",
        "Ordering",
    ]:
        assert needed in titles, f"missing outline entry: {needed}"


def test_outline_levels_promote_all_caps_headers(index: Index):
    by_title = {o["title"]: o for o in index["outline"]}
    assert by_title["TECHNICAL DATA"]["level"] == 1
    assert by_title["OPERATING DATA"]["level"] == 1
    assert by_title["Motor"]["level"] == 2


def _table(index: Index, caption_substr: str, header_substr: str) -> Table:
    for t in index["tables"]:
        if caption_substr in t["caption"] and any(header_substr in h for h in t["header_row"]):
            return t
    raise AssertionError(f"no table with caption~{caption_substr!r} header~{header_substr!r}")


def test_max_inlet_pressure_table_lists_models(index: Index):
    t = _table(index, "OPERATING DATA", "Max inlet pressure")
    assert t["page"] == 2
    # first column should expose model names so the agent sees this is per-model
    joined = " ".join(t["first_column_values"])
    assert "LKH-5" in joined
    assert "LKH-85" in joined or "LKH-90" in joined


def test_pump_specific_measures_has_all_models_in_header(index: Index):
    t = _table(index, "Pump specific measures", "Pump Model")
    assert t["page"] == 3
    for model in ["LKH-5", "LKH-10", "LKH-25", "LKH-50", "LKH-90"]:
        assert model in t["header_row"]
    assert t["shape"]["cols"] == 14  # Pump Model + 13 models


def test_motor_specific_measures_has_iec_frames(index: Index):
    t = _table(index, "Motor specific measures", "Motor IEC")
    assert t["page"] == 3
    for frame in ["IEC80", "IEC132", "IEC280"]:
        assert frame in t["header_row"]


def test_connections_table_present_with_models(index: Index):
    t = _table(index, "Connections", "Pump Model")
    assert t["page"] == 3
    joined = " ".join(t["header_row"])
    assert "LKH-5" in joined and "LKH-85" in joined


def test_figures_include_dimensions_and_flow_chart(index: Index):
    captions = [f["caption"] for f in index["figures"]]
    assert "Dimensions" in captions
    assert "Flow chart" in captions


def test_every_table_has_bbox_and_page(index: Index):
    assert index["tables"], "expected at least one table"
    for t in index["tables"]:
        assert isinstance(t["page"], int) and t["page"] >= 1
        assert len(t["bbox"]) == 4
        assert all(isinstance(v, float) for v in t["bbox"])
