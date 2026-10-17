"""Gold coverage invariant (#242 P1, closes #231) — pure-function tests.

Every meaningful silver candidate must end up in at least one gold chunk.
These exercise the reconciliation pass directly; the pipeline hookups are
covered in the session and keyed-ingest tests.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from anchor.extensions.anchor_pdfs.core.gold_ingest import GoldIngest
from anchor.extensions.anchor_pdfs.core.ingest.coverage import (
    coverage_stats,
    covered_item_ids,
    synthesize_coverage_regions,
)
from anchor.extensions.anchor_pdfs.core.silver import build_page_candidates


def _cands(*items: tuple[str, str]) -> list[dict]:
    """(label, text) tuples -> page-1 candidates stacked down the page.

    Top-left PDF points (#281): item idx sits at y = 100 + 20*idx."""
    out = []
    for idx, (label, text) in enumerate(items):
        top = 100 + idx * 20
        cand = {"id": f"p1-i{idx}", "label": label, "text": text,
                "bbox": [0, top, 200, top + 15]}
        if label == "table":
            cand["cells"] = [
                {"row": 0, "col": 0, "text": "Flow", "bbox": [0, top, 90, top + 15]},
                {"row": 0, "col": 1, "text": "35 m3/h", "bbox": [100, top, 200, top + 15]},
            ]
            cand["cells_preview"] = {"shape": [1, 2], "header_row": ["Flow", "35 m3/h"]}
        out.append(cand)
    return out


def test_covered_ids_read_members_and_table_slice():
    regions = [
        {"id": "r1", "member_item_ids": ["p1-i0", "p1-i1"]},
        {"id": "r2", "table_slice": {"candidate_id": "p1-i5", "rows": [0]}},
    ]
    assert covered_item_ids(regions) == {"p1-i0", "p1-i1", "p1-i5"}


def test_uncovered_captionless_table_becomes_its_own_chunk():
    cands = _cands(("section_header", "Operating data"), ("table", ""))
    extra = synthesize_coverage_regions(1, cands, regions=[])
    assert len(extra) == 1
    region = extra[0]
    assert region["kind"] == "table"
    assert region["coverage_fallback"] is True
    assert region["member_item_ids"] == ["p1-i1"]
    # Heading supplies the title; description stays empty so the embedding
    # fallback renders the cells into the search text.
    assert region["title"] == "Operating data"
    assert region["description"] == ""
    assert region["cells"][1]["text"] == "35 m3/h"
    assert region["bbox"] == [0, 120, 200, 135]


def test_contiguous_uncovered_text_merges_into_one_chunk_under_heading():
    cands = _cands(
        ("section_header", "Benefits"),
        ("text", "Energy efficient pump."),
        ("list_item", "- Hygienic design."),
        ("text", "Long service life."),
    )
    extra = synthesize_coverage_regions(1, cands, regions=[])
    assert len(extra) == 1
    region = extra[0]
    assert region["kind"] == "text"
    assert region["title"] == "Benefits"
    # The uncovered heading joins the run; all three text items are members.
    assert region["member_item_ids"] == ["p1-i0", "p1-i1", "p1-i2", "p1-i3"]
    assert "Hygienic design" in region["content"]
    assert region["bbox"] == [0, 100, 200, 175]


def test_covered_items_split_runs_and_are_never_re_chunked():
    cands = _cands(
        ("text", "Alpha."), ("text", "Beta."), ("text", "Gamma."), ("text", "Delta."),
    )
    authored = [{"id": "r1", "kind": "text", "title": "Beta", "member_item_ids": ["p1-i1", "p1-i2"]}]
    extra = synthesize_coverage_regions(1, cands, authored)
    # Alpha and Delta are uncovered but not contiguous -> two chunks, ids
    # continuing after the authored r1.
    assert [r["member_item_ids"] for r in extra] == [["p1-i0"], ["p1-i3"]]
    assert [r["id"] for r in extra] == ["r2", "r3"]


def test_size_cap_bounds_a_run():
    cands = _cands(*[("text", "x" * 400) for _ in range(5)])
    extra = synthesize_coverage_regions(1, cands, regions=[], max_run_chars=1000)
    # 5 x 400 chars with a 1000-char cap -> runs of 2, 2, 1.
    assert [len(r["member_item_ids"]) for r in extra] == [2, 2, 1]


def test_page_furniture_and_bare_headings_are_not_required():
    cands = _cands(
        ("page_header", "Alfa Laval"), ("title", "LKH"), ("picture", ""), ("page_footer", "p. 3"),
    )
    assert synthesize_coverage_regions(1, cands, regions=[]) == []
    assert coverage_stats(cands, []) == {
        "meaningful_items": 0, "covered_items": 0, "uncovered_items": 0,
    }


def test_full_items_supply_uncapped_content():
    cands = _cands(("text", "short preview"))
    full = [{"label": "text", "text": "the full uncapped paragraph text", "page": 1,
             "bbox": [0, 700, 200, 685]}]
    extra = synthesize_coverage_regions(1, cands, regions=[], full_items=full)
    assert "full uncapped paragraph" in extra[0]["content"]


def test_coverage_stats_counts_meaningful_only():
    cands = _cands(("title", "Doc"), ("text", "a"), ("table", ""), ("text", "b"))
    authored = [{"id": "r1", "member_item_ids": ["p1-i1"]}]
    assert coverage_stats(cands, authored) == {
        "meaningful_items": 3, "covered_items": 1, "uncovered_items": 2,
    }


def test_keyed_snapper_records_member_item_ids_in_candidate_scheme():
    # Global docling indexes 0..3 span two pages; page-2 positions restart at
    # 0 so the recorded ids match build_page_candidates.
    docling = {"items": [
        {"label": "text", "text": "p1 a", "page": 1, "bbox": [0, 700, 100, 690]},
        {"label": "text", "text": "p2 a", "page": 2, "bbox": [0, 700, 100, 690]},
        {"label": "text", "text": "p2 b", "page": 2, "bbox": [0, 680, 100, 670]},
        {"label": "text", "text": "p2 c", "page": 2, "bbox": [0, 300, 100, 290]},
    ]}
    snapped = GoldIngest._snap_regions(docling, 2, [
        {"kind": "text", "title": "Top of p2", "bbox": [0, 710, 120, 660]},
    ])
    assert snapped[0]["member_item_ids"] == ["p2-i0", "p2-i1"]
    assert build_page_candidates(docling)[2][1]["id"] == "p2-i1"
    # And the coverage pass sees p2-i2 as the only gap on that page.
    extra = synthesize_coverage_regions(2, build_page_candidates(docling)[2], snapped)
    assert [r["member_item_ids"] for r in extra] == [["p2-i2"]]


def test_a_stray_header_cell_inside_a_table_is_covered_by_it():
    # Docling emitted the tables' last header cells again as loose text.
    # Each lies inside its table's region, so none needs a fallback chunk,
    # and they must not merge into one strip cutting across the tables.
    cands = [
        {"id": "p3-i61", "label": "text", "text": "PX-85", "bbox": [475, 555, 500, 566]},
        {"id": "p3-i62", "label": "text", "text": "PX-100", "bbox": [515, 247, 545, 258]},
        {"id": "p3-i63", "label": "text", "text": "IEC280", "bbox": [518, 430, 544, 440]},
    ]
    regions = [
        {"id": "p3-r3", "kind": "table", "bbox": [42, 245, 553, 388], "member_item_ids": ["p3-i25"]},
        {"id": "p3-r5", "kind": "table", "bbox": [42, 428, 553, 517], "member_item_ids": ["p3-i31"]},
        {"id": "p3-r7", "kind": "table", "bbox": [44, 552, 553, 595], "member_item_ids": ["p3-i69"]},
    ]
    assert synthesize_coverage_regions(3, cands, regions) == []
    assert coverage_stats(cands, regions)["uncovered_items"] == 0


def test_text_outside_any_table_still_gets_a_fallback_chunk():
    cands = [{"id": "p3-i70", "label": "text", "text": "Loose note", "bbox": [45, 620, 300, 632]}]
    regions = [{"id": "p3-r7", "kind": "table", "bbox": [44, 552, 553, 595], "member_item_ids": []}]
    extra = synthesize_coverage_regions(3, cands, regions)
    assert [r["member_item_ids"] for r in extra] == [["p3-i70"]]


def test_letters_on_a_drawing_are_covered_by_the_drawing():
    cands = [
        {"id": "p3-i11", "label": "text", "text": "C", "bbox": [170, 106, 175, 112]},
        {"id": "p3-i25", "label": "text", "text": "A Suction flange face", "bbox": [366, 86, 510, 93]},
    ]
    regions = [{"id": "p3-r1", "kind": "diagram", "bbox": [45, 64, 550, 220], "member_item_ids": ["p3-i0"]}]
    assert synthesize_coverage_regions(3, cands, regions) == []


def test_a_run_breaks_where_reading_order_jumps_across_the_page():
    # A footer line, then the masthead at the top of the page: next in
    # reading order, but not one chunk.
    cands = [
        {"id": "p1-i15", "label": "text", "text": "Fictional company notice", "bbox": [45, 767, 550, 787]},
        {"id": "p1-i17", "label": "text", "text": "N NORRHAVN", "bbox": [49, 48, 137, 58]},
        {"id": "p1-i18", "label": "text", "text": "Fluid Technology", "bbox": [68, 57, 120, 64]},
    ]
    extra = synthesize_coverage_regions(1, cands, regions=[])
    assert [r["member_item_ids"] for r in extra] == [["p1-i15"], ["p1-i17", "p1-i18"]]


def test_upward_jump_does_not_give_drawing_labels_a_later_heading():
    cands = [
        {"id": "p1-i0", "label": "section_header", "text": "Motor overview",
         "bbox": [45, 539, 117, 546]},
        {"id": "p1-i1", "label": "text", "text": "B", "bbox": [46, 145, 52, 151]},
        {"id": "p1-i2", "label": "text", "text": "A", "bbox": [250, 70, 256, 76]},
        {"id": "p1-i3", "label": "text", "text": "7", "bbox": [80, 210, 86, 216]},
    ]
    before = deepcopy(cands)
    extra = synthesize_coverage_regions(1, cands, regions=[])

    assert [r["title"] for r in extra] == ["B", "A", "7"]
    assert [r["content"] for r in extra] == ["B", "A", "7"]
    assert [r["member_item_ids"] for r in extra] == [["p1-i1"], ["p1-i2"], ["p1-i3"]]
    assert [r["bbox"] for r in extra] == [c["bbox"] for c in cands[1:]]
    assert coverage_stats(cands, extra)["uncovered_items"] == 0
    assert cands == before


@pytest.mark.parametrize("containment", [False, True], ids=["member", "bbox"])
def test_covered_upward_jump_clears_heading_before_the_next_fallback(containment):
    cands = [
        {"id": "p1-i0", "label": "section_header", "text": "Lower section",
         "bbox": [40, 500, 120, 510]},
        {"id": "p1-i1", "label": "text", "text": "Covered drawing label",
         "bbox": [40, 100, 120, 110]},
        {"id": "p1-i2", "label": "text", "text": "Loose note",
         "bbox": [40, 600, 200, 610]},
    ]
    authored = [{"id": "r1", "kind": "diagram", "title": "Existing diagram",
                 "member_item_ids": ["p1-i0"] if containment else ["p1-i0", "p1-i1"]}]
    if containment:
        authored[0]["bbox"] = [35, 95, 125, 115]
    before = deepcopy(authored)
    extra = synthesize_coverage_regions(1, cands, authored)

    assert len(extra) == 1
    assert extra[0]["id"] == "r2"
    assert extra[0]["title"] == "Loose note"
    assert extra[0]["member_item_ids"] == ["p1-i2"]
    assert extra[0]["bbox"] == cands[2]["bbox"]
    assert authored == before
    assert coverage_stats(cands, authored + extra)["uncovered_items"] == 0


def test_upward_table_fallback_keeps_its_cells_and_geometry():
    cands = _cands(("section_header", "Lower section"), ("table", ""))
    cands[0]["bbox"] = [0, 500, 200, 515]
    before = deepcopy(cands)
    extra = synthesize_coverage_regions(1, cands, regions=[])

    assert len(extra) == 1
    assert extra[0]["kind"] == "table"
    assert extra[0]["title"].startswith("Flow")
    assert extra[0]["member_item_ids"] == ["p1-i1"]
    assert extra[0]["bbox"] == cands[1]["bbox"]
    assert [(c["text"], c["bbox"]) for c in extra[0]["cells"]] == [
        (c["text"], c["bbox"]) for c in cands[1]["cells"]
    ]
    assert cands == before


def test_downward_gap_retains_heading_and_member_bbox_union():
    cands = _cands(("section_header", "Operating data"), ("text", "35 m3/h"))
    cands[1]["bbox"] = [20, 600, 180, 615]
    extra = synthesize_coverage_regions(1, cands, regions=[])

    assert extra[0]["title"] == "Operating data"
    assert extra[0]["member_item_ids"] == ["p1-i0", "p1-i1"]
    assert extra[0]["bbox"] == [0, 100, 200, 615]


def test_heading_without_geometry_retains_source_order_context():
    cands = _cands(("section_header", "Operating data"), ("text", "35 m3/h"))
    cands[0]["bbox"] = []
    extra = synthesize_coverage_regions(1, cands, regions=[])

    assert extra[0]["title"] == "Operating data"
    assert extra[0]["member_item_ids"] == ["p1-i0", "p1-i1"]
    assert extra[0]["bbox"] == cands[1]["bbox"]
