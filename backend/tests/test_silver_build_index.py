"""Tests for silver.build_index — deterministic docling -> index.json."""
from typing import Any

from src.ingestion.silver import build_index


def _item(
    label: str,
    page: int,
    text: str = "",
    bbox: list[float] | None = None,
    cells: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    it: dict[str, Any] = {"label": label, "page": page, "text": text, "bbox": bbox or [0, 0, 1, 1]}
    if cells is not None:
        it["cells"] = cells
    return it


def test_empty_docling_returns_zero_pages():
    out = build_index({"items": []}, filename="x.pdf")
    assert out["document"]["page_count"] == 0
    assert out["outline"] == []
    assert out["tables"] == []
    assert out["figures"] == []


def test_missing_items_key_is_safe():
    out = build_index({}, filename="x.pdf")
    assert out["document"]["page_count"] == 0


def test_outline_picks_up_section_headers_and_titles():
    docling = {"items": [
        _item("title", 1, "Sample Pump"),
        _item("section_header", 2, "Technical data"),
        _item("section_header", 2, "Max inlet pressure"),
    ]}
    out = build_index(docling, filename="x.pdf")
    titles = [o["title"] for o in out["outline"]]
    assert titles == ["Sample Pump", "Technical data", "Max inlet pressure"]
    assert out["outline"][0]["level"] == 1


def test_resolved_title_falls_back_to_first_header():
    docling = {"items": [_item("title", 1, "Doc Title")]}
    out = build_index(docling, filename="x.pdf")
    assert out["document"]["title"] == "Doc Title"


def test_explicit_title_wins_over_first_header():
    docling = {"items": [_item("title", 1, "Header")]}
    out = build_index(docling, filename="x.pdf", title="Explicit")
    assert out["document"]["title"] == "Explicit"


def test_page_count_is_max_page():
    docling = {"items": [
        _item("section_header", 1, "A"),
        _item("section_header", 5, "B"),
    ]}
    assert build_index(docling)["document"]["page_count"] == 5


def test_table_summarized_with_header_and_first_column():
    cells = [
        {"row": 0, "col": 0, "text": "Model"},
        {"row": 0, "col": 1, "text": "kPa"},
        {"row": 1, "col": 0, "text": "PUMP-5"},
        {"row": 1, "col": 1, "text": "400"},
        {"row": 2, "col": 0, "text": "PUMP-10"},
        {"row": 2, "col": 1, "text": "500"},
    ]
    docling = {"items": [
        _item("section_header", 2, "Max inlet pressure"),
        _item("table", 2, cells=cells),
    ]}
    out = build_index(docling)
    assert len(out["tables"]) == 1
    t = out["tables"][0]
    assert t["id"] == "t1"
    assert t["page"] == 2
    assert t["caption"] == "Max inlet pressure"
    assert t["header_row"] == ["Model", "kPa"]
    assert t["first_column_values"] == ["PUMP-5", "PUMP-10"]
    assert t["shape"] == {"rows": 3, "cols": 2}


def test_picture_uses_last_header_on_page_as_caption():
    docling = {"items": [
        _item("section_header", 3, "Dimensions"),
        _item("picture", 3),
    ]}
    out = build_index(docling)
    assert out["figures"] == [{"page": 3, "bbox": [0, 0, 1, 1], "caption": "Dimensions"}]


def test_items_without_page_are_skipped():
    docling = {"items": [
        {"label": "section_header", "text": "no page"},
        _item("section_header", 1, "ok"),
    ]}
    out = build_index(docling)
    assert [o["title"] for o in out["outline"]] == ["ok"]


def test_bbox_cleaned_to_floats():
    docling = {"items": [_item("section_header", 1, "h", bbox=[1, 2, 3, 4])]}
    out = build_index(docling)
    assert out["outline"][0]["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_invalid_bbox_becomes_empty_list():
    docling = {"items": [{"label": "section_header", "page": 1, "text": "h", "bbox": "bad"}]}
    out = build_index(docling)
    assert out["outline"][0]["bbox"] == []
