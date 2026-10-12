"""Region resolution guards against member lists that run past their block.

A harness that names "the Materials block" as every item from its heading
down to the next few headings gets a page back for repair; a diagram that
names the table under the picture is clipped to the picture; an
``approx_bbox`` in raster pixels is scaled to points, and one outside both
page and raster is refused.
"""

from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.ingest.region_resolution import resolve_regions


def _item(item_id: str, label: str, bbox: list[float], text: str = "") -> dict:
    return {"id": item_id, "label": label, "bbox": bbox, "text": text}


# Two key/value blocks in one column, as Docling sees them: a heading and a
# table each.
TWO_BLOCKS = [
    _item("p2-i1", "section_header", [44, 64, 120, 80], "Materials"),
    _item("p2-i27", "table", [44, 91, 288, 199]),
    _item("p2-i3", "section_header", [44, 210, 120, 222], "Motor sizes"),
    _item("p2-i28", "table", [45, 222, 288, 255]),
]


def _block(region_id: str, title: str, members: list[str]) -> dict:
    return {"id": region_id, "kind": "spec_block", "title": title, "member_item_ids": members}


def test_a_table_named_by_two_regions_sends_the_page_back():
    regions, errors = resolve_regions(
        [
            _block("materials", "Materials", ["p2-i1", "p2-i27", "p2-i3", "p2-i28"]),
            _block("motor", "Motor sizes", ["p2-i3", "p2-i28"]),
        ],
        page=2,
        candidates=TWO_BLOCKS,
    )
    assert regions == []
    shared = [e for e in errors if e["field"] == "member_item_ids" and "p2-i28" in e["message"]]
    assert {e["region_index"] for e in shared} == {0, 1}
    assert "materials, motor" in shared[0]["message"]
    # The table the first block owns alone is not complained about.
    assert not [e for e in errors if "p2-i27" in e["message"]]


def test_each_block_with_its_own_table_resolves_to_its_own_box():
    regions, errors = resolve_regions(
        [
            _block("materials", "Materials", ["p2-i1", "p2-i27"]),
            _block("motor", "Motor sizes", ["p2-i3", "p2-i28"]),
        ],
        page=2,
        candidates=TWO_BLOCKS,
    )
    assert errors == []
    assert [r["bbox"] for r in regions] == [[44, 64, 288, 199], [44, 210, 288, 255]]


DRAWING_PAGE = [
    _item("p3-i70", "picture", [45, 63, 550, 219]),
    _item("p3-i1", "text", [170, 94, 175, 116], "C"),
    _item("p3-i12", "text", [299, 212, 312, 226], "Side"),  # straddles the picture's edge
    _item("p3-i26", "section_header", [45, 215, 176, 243], "Pump specific measures (mm)"),
    _item("p3-i67", "table", [42, 245, 553, 388]),
    _item("p3-i32", "section_header", [45, 399, 178, 426], "Motor specific measures (mm)"),
]


def test_a_diagram_is_its_picture_and_the_labels_inside_it():
    regions, errors = resolve_regions(
        [{
            "id": "front",
            "kind": "diagram",
            "title": "Front view",
            "member_item_ids": ["p3-i70", "p3-i1", "p3-i12", "p3-i26", "p3-i67", "p3-i32"],
        }],
        page=3,
        candidates=DRAWING_PAGE,
    )
    assert errors == []
    (region,) = regions
    assert region["member_item_ids"] == ["p3-i70", "p3-i1", "p3-i12"]
    assert region["bbox"] == [45, 63, 550, 226]
    assert "Motor specific" not in region.get("content", "")


def test_a_diagram_without_a_picture_keeps_its_members():
    regions, errors = resolve_regions(
        [{"id": "sketch", "kind": "diagram", "title": "Sketch", "member_item_ids": ["p3-i1", "p3-i12"]}],
        page=3,
        candidates=DRAWING_PAGE,
    )
    assert errors == []
    assert regions[0]["member_item_ids"] == ["p3-i1", "p3-i12"]


A4 = [595.276, 841.89]


def test_an_approx_bbox_in_raster_pixels_is_scaled_to_points():
    regions, errors = resolve_regions(
        [{"id": "key", "kind": "spec_block", "title": "Letter key", "approx_bbox": [756, 52, 1146, 461]}],
        page=3,
        candidates=[],
        page_size=A4,
        dpi=150,
    )
    assert errors == []
    assert regions[0]["bbox"] == [362.88, 24.96, 550.08, 221.28]
    assert regions[0]["approx_bbox"] == [362.88, 24.96, 550.08, 221.28]


def test_an_approx_bbox_in_points_is_left_alone():
    regions, errors = resolve_regions(
        [{"id": "key", "kind": "spec_block", "title": "Letter key", "approx_bbox": [363, 60, 550, 235]}],
        page=3,
        candidates=[],
        page_size=A4,
        dpi=150,
    )
    assert errors == []
    assert regions[0]["bbox"] == [363, 60, 550, 235]


def test_an_approx_bbox_outside_page_and_raster_is_refused():
    regions, errors = resolve_regions(
        [{"id": "key", "kind": "spec_block", "title": "Letter key", "approx_bbox": [0, 0, 5000, 5000]}],
        page=3,
        candidates=[],
        page_size=A4,
        dpi=150,
    )
    assert regions == []
    assert errors[0]["field"] == "approx_bbox"
    assert "outside the page (595 x 842 pt)" in errors[0]["message"]


def test_without_a_page_size_pixels_pass_as_before():
    regions, errors = resolve_regions(
        [{"id": "key", "kind": "spec_block", "title": "Letter key", "approx_bbox": [756, 52, 1146, 461]}],
        page=3,
        candidates=[],
    )
    assert errors == []
    assert regions[0]["bbox"] == [756, 52, 1146, 461]


KEY_PAGE = [
    _item("p3-i70", "picture", [45, 58, 550, 219]),
    _item("p3-i1", "text", [170, 94, 175, 116], "C"),
    _item("p3-i2", "text", [249.8, 58.2, 255.3, 80.3], "A"),  # above the key's top edge
    _item("p3-i13", "section_header", [366, 60, 402, 72], "Letter key"),
    _item("p3-i14", "text", [366, 80, 546, 92], "A Suction flange face to discharge axis"),
]


def test_a_picture_gives_up_the_part_a_sibling_region_sits_in():
    regions, errors = resolve_regions(
        [
            {"id": "side", "kind": "diagram", "title": "Side view",
             "member_item_ids": ["p3-i70", "p3-i1", "p3-i2", "p3-i13", "p3-i14"]},
            {"id": "key", "kind": "spec_block", "title": "Letter key", "member_item_ids": ["p3-i13", "p3-i14"]},
        ],
        page=3,
        candidates=KEY_PAGE,
    )
    assert errors == []
    diagram, key = regions
    assert key["bbox"] == [366, 60, 546, 92]
    assert diagram["bbox"] == [45, 58, 366, 219]
    assert diagram["member_item_ids"] == ["p3-i70", "p3-i1", "p3-i2"]


def test_a_drawing_gives_the_key_its_letters():
    candidates = [
        _item("p3-i0", "text", [249.8, 58.2, 255.3, 80.3], "A"),
        _item("p3-i2", "text", [366.2, 86.5, 371.5, 108.6], "B"),
        _item("p3-i13", "section_header", [366, 60, 402, 72], "Letter key"),
    ]
    regions, errors = resolve_regions(
        [
            {"id": "side", "kind": "diagram", "title": "Side view", "member_item_ids": ["p3-i0", "p3-i2"]},
            {"id": "key", "kind": "spec_block", "title": "Letter key", "member_item_ids": ["p3-i13", "p3-i2"]},
        ],
        page=3,
        candidates=candidates,
    )
    assert errors == []
    drawing, key = regions
    assert drawing["member_item_ids"] == ["p3-i0"]
    assert drawing["bbox"] == [249.8, 58.2, 255.3, 80.3]
    assert key["member_item_ids"] == ["p3-i13", "p3-i2"]


def test_two_views_in_one_drawing_are_one_region():
    candidates = [
        _item("p3-i70", "picture", [45, 58, 550, 219]),
        _item("p3-i1", "text", [46, 119, 62, 141], "D"),
        _item("p3-i3", "text", [249.8, 58.2, 255.3, 80.3], "A"),
    ]
    regions, errors = resolve_regions(
        [
            {"id": "front", "kind": "diagram", "title": "Front view", "member_item_ids": ["p3-i1"]},
            {"id": "side", "kind": "diagram", "title": "Side view", "member_item_ids": ["p3-i3"]},
        ],
        page=3,
        candidates=candidates,
    )
    assert errors == []
    (drawing,) = regions
    assert drawing["title"] == "Front view; Side view"
    assert drawing["member_item_ids"] == ["p3-i1", "p3-i3"]
    assert drawing["bbox"] == [45, 58, 550, 219]


def test_a_table_named_by_heading_and_lookalike_cells_takes_the_table_under_its_heading():
    candidates = [
        _item("p3-i26", "section_header", [45, 215, 176, 243], "Pump specific measures (mm)"),
        _item("p3-i67", "table", [42, 245, 553, 388]),
        _item("p3-i27", "text", [111, 250, 131, 262], "PX-5"),
        _item("p3-i33", "section_header", [45, 524, 117, 552], "Motor overview"),
        _item("p3-i69", "table", [44, 552, 553, 595]),
        _item("p3-i60", "text", [111, 556, 131, 568], "PX-5"),
    ]
    regions, errors = resolve_regions(
        [{"id": "pump", "kind": "table", "title": "Pump specific measures (mm)",
          "member_item_ids": ["p3-i26", "p3-i27", "p3-i60"]}],
        page=3,
        candidates=candidates,
    )
    assert errors == []
    assert regions[0]["member_item_ids"] == ["p3-i67", "p3-i26", "p3-i27"]
    assert regions[0]["bbox"] == [42, 215, 553, 388]


def test_the_heading_wins_over_a_named_table_from_further_down():
    candidates = [
        _item("p3-i26", "section_header", [45, 215, 176, 243], "Pump specific measures (mm)"),
        _item("p3-i67", "table", [42, 245, 553, 388]),
        _item("p3-i27", "text", [111, 236, 131, 260], "PX-5"),
        _item("p3-i32", "section_header", [45, 399, 178, 426], "Motor specific measures (mm)"),
        _item("p3-i68", "table", [42, 428, 553, 517]),
    ]
    regions, errors = resolve_regions(
        [{"id": "pump", "kind": "table", "title": "Pump specific measures (mm)",
          "member_item_ids": ["p3-i26", "p3-i27", "p3-i68"]}],
        page=3,
        candidates=candidates,
    )
    assert errors == []
    assert regions[0]["member_item_ids"] == ["p3-i67", "p3-i26", "p3-i27"]
