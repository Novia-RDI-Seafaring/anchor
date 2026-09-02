"""Gold coverage invariant (#242 P1, closes #231) — pure-function tests.

Every meaningful silver candidate must end up in at least one gold chunk.
These exercise the reconciliation pass directly; the pipeline hookups are
covered in the session and keyed-ingest tests.
"""
from __future__ import annotations

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
