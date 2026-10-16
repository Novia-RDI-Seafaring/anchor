"""The keyed gold path grounds a model's boxes with the same care as the
harness path, but corrects in place: there is no repair round to ask for.

Pixels become points, a diagram is its picture, a spec block is one table
and its heading, and a stray number in ``entities`` does not cost the
region.
"""

from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.gold_ingest import GoldIngest

A4 = {"width": 595.276, "height": 841.89}


def _item(label: str, bbox: list[float], text: str = "", page: int = 2) -> dict:
    return {"page": page, "label": label, "bbox": bbox, "text": text}


# Page 2 of the Norrhavn sheet, reduced: three key/value blocks in one column.
PAGE_TWO = {
    "pages": {"2": A4},
    "items": [
        _item("section_header", [44, 64, 120, 80], "Materials"),          # 0
        _item("table", [44, 91, 288, 199]),                                 # 1
        _item("text", [50, 100, 120, 110], "Rotary seal face"),             # 2
        _item("section_header", [44, 210, 120, 222], "Motor sizes"),        # 3
        _item("table", [45, 222, 288, 255]),                                # 4
        _item("text", [50, 230, 80, 240], "50 Hz"),                         # 5
        _item("section_header", [44, 265, 160, 277], "Min/max motor speed"),  # 6
        _item("table", [44, 278, 288, 327]),                                # 7
    ],
}


def _block(title: str, bbox: list[float], kind: str = "spec_block", **extra) -> dict:
    return {"id": title.lower().replace(" ", "-"), "kind": kind, "title": title, "bbox": bbox, **extra}


def test_a_spec_block_that_spans_three_tables_keeps_the_one_it_is_about():
    (region,) = GoldIngest._snap_regions(
        PAGE_TWO, 2, [_block("Materials", [44, 64, 288, 330])], dpi=150,
    )
    assert region["bbox"] == [44, 64, 288, 199]
    assert region["member_item_ids"] == ["p2-i0", "p2-i1", "p2-i2"]
    assert "50 Hz" not in region.get("content", "")


def test_the_block_chosen_is_the_table_the_box_overlaps_most():
    (region,) = GoldIngest._snap_regions(
        PAGE_TWO, 2, [_block("Motor sizes", [44, 205, 288, 330])], dpi=150,
    )
    assert region["member_item_ids"] == ["p2-i3", "p2-i4", "p2-i5"]
    assert region["bbox"] == [44, 210, 288, 255]


def test_a_box_in_raster_pixels_is_scaled_before_snapping():
    # The Materials block, as 150 dpi pixels of the page image.
    px = [v * 150 / 72 for v in (44, 64, 288, 199)]
    (region,) = GoldIngest._snap_regions(PAGE_TWO, 2, [_block("Materials", px)], dpi=150)
    assert region["member_item_ids"] == ["p2-i0", "p2-i1", "p2-i2"]
    assert "geometry_note" not in region


def test_a_box_outside_page_and_raster_is_kept_with_a_note():
    (region,) = GoldIngest._snap_regions(
        PAGE_TWO, 2, [_block("Nowhere", [0, 0, 9000, 9000])], dpi=150,
    )
    assert "outside the page" in region["geometry_note"]


DRAWING_PAGE = {
    "pages": {"3": A4},
    "items": [
        _item("picture", [45, 63, 550, 219], page=3),                                   # 0
        _item("text", [170, 94, 175, 116], "C", page=3),                                 # 1
        _item("section_header", [45, 215, 176, 243], "Pump specific measures", page=3),  # 2
        _item("table", [42, 245, 553, 388], page=3),                                     # 3
        _item("text", [45, 251, 52, 276], "A", page=3),                                  # 4
    ],
}


def test_a_diagram_is_clipped_to_its_picture():
    (region,) = GoldIngest._snap_regions(
        DRAWING_PAGE, 3, [_block("Front view", [42, 63, 553, 426], kind="diagram")], dpi=150,
    )
    assert region["member_item_ids"] == ["p3-i0", "p3-i1"]
    assert region["bbox"] == [45, 63, 550, 219]


def test_entities_and_tags_are_made_strings_instead_of_sinking_the_region():
    (region,) = GoldIngest._snap_regions(
        PAGE_TWO,
        2,
        [_block("Materials", [44, 64, 288, 199], entities=["EPDM", 316, {"name": "no"}, None], tags="seal")],
        dpi=150,
    )
    assert region["entities"] == ["EPDM", "316"]
    assert region["tags"] == ["seal"]


def test_named_items_ground_a_region_without_a_box():
    (region,) = GoldIngest._snap_regions(
        PAGE_TWO,
        2,
        [{"id": "motor-sizes", "kind": "spec_block", "title": "Motor sizes",
          "member_item_ids": ["p2-i3", "p2-i4", "p2-i5", "p2-i6", "p2-i7"]}],
        dpi=150,
    )
    # The run-on tail (next heading and table) is dropped: one table per block.
    assert region["member_item_ids"] == ["p2-i3", "p2-i4", "p2-i5"]
    assert region["bbox"] == [44, 210, 288, 255]


def test_unknown_named_items_fall_back_to_the_box():
    (region,) = GoldIngest._snap_regions(
        PAGE_TWO,
        2,
        [_block("Materials", [44, 64, 288, 199], member_item_ids=["p9-i9"])],
        dpi=150,
    )
    assert region["member_item_ids"] == ["p2-i0", "p2-i1", "p2-i2"]


def test_geometry_nested_under_its_own_key_is_lifted():
    nested = [
        {"id": "a", "kind": "spec_block", "title": "Motor sizes",
         "geometry": {"member_item_ids": ["p2-i3", "p2-i4", "p2-i5"]}},
        {"id": "b", "kind": "spec_block", "title": "Materials", "geometry": {"bbox": [44, 64, 288, 199]}},
    ]
    first, second = GoldIngest._snap_regions(PAGE_TWO, 2, nested, dpi=150)
    assert first["member_item_ids"] == ["p2-i3", "p2-i4", "p2-i5"]
    assert second["member_item_ids"] == ["p2-i0", "p2-i1", "p2-i2"]
    assert "geometry" not in first and "geometry" not in second


# A drawing and its letter key side by side: Docling boxes them as one
# picture, the key is its own block.
KEY_PAGE = {
    "pages": {"3": A4},
    "items": [
        _item("picture", [45, 58, 550, 219], page=3),                                  # 0
        _item("text", [170, 94, 175, 116], "C", page=3),                                # 1
        _item("section_header", [366, 60, 402, 72], "Letter key", page=3),              # 2
        _item("text", [366, 80, 546, 92], "A Suction flange face to discharge axis", page=3),  # 3
        _item("text", [366, 200, 546, 212], "N Overall length", page=3),                # 4
    ],
}


def test_a_picture_gives_up_the_part_a_sibling_region_sits_in():
    diagram, key = GoldIngest._snap_regions(
        KEY_PAGE,
        3,
        [
            {"id": "side", "kind": "diagram", "title": "Side view",
             "member_item_ids": ["p3-i0", "p3-i1", "p3-i2", "p3-i3", "p3-i4"]},
            {"id": "key", "kind": "spec_block", "title": "Letter key",
             "member_item_ids": ["p3-i2", "p3-i3", "p3-i4"]},
        ],
        dpi=150,
    )
    assert key["bbox"] == [366, 60, 546, 212]
    assert diagram["bbox"] == [45, 58, 366, 219]
    assert diagram["member_item_ids"] == ["p3-i0", "p3-i1"]
    assert "Letter key" not in diagram.get("content", "")


def test_a_drawing_gives_the_key_its_letters():
    # No picture item named this time: the drawing is its labels, and the
    # model took the key's letter column along.
    page = {
        "pages": {"3": A4},
        "items": [
            _item("text", [249.8, 58.2, 255.3, 80.3], "A", page=3),      # 0, on the drawing
            _item("text", [335.4, 81.9, 338.8, 103.9], "J", page=3),     # 1, on the drawing
            _item("text", [366.2, 86.5, 371.5, 108.6], "B", page=3),     # 2, in the key
            _item("text", [366.2, 112.0, 371.5, 134.0], "C", page=3),    # 3, in the key
            _item("section_header", [366, 60, 402, 72], "Letter key", page=3),  # 4
        ],
    }
    drawing, key = GoldIngest._snap_regions(
        page,
        3,
        [
            {"id": "side", "kind": "diagram", "title": "Side view", "member_item_ids": ["p3-i0", "p3-i1", "p3-i2", "p3-i3"]},
            {"id": "key", "kind": "spec_block", "title": "Letter key", "member_item_ids": ["p3-i4", "p3-i2", "p3-i3"]},
        ],
        dpi=150,
    )
    assert drawing["member_item_ids"] == ["p3-i0", "p3-i1"]
    assert drawing["bbox"] == [249.8, 58.2, 338.8, 103.9]
    assert key["member_item_ids"] == ["p3-i4", "p3-i2", "p3-i3"]


def test_two_views_in_one_drawing_are_one_region():
    # Page 3 of the Norrhavn sheet: one Docling picture spans the front view,
    # the side view and the letter key. The model names each view by its
    # labels; the PDF says it is one drawing, so it becomes one region.
    page = {
        "pages": {"3": A4},
        "items": [
            _item("picture", [45, 58, 550, 219], page=3),                             # 0
            _item("text", [46, 119, 62, 141], "D", page=3),                            # 1 front
            _item("text", [104, 174, 116, 201], "H", page=3),                          # 2 front
            _item("text", [249.8, 58.2, 255.3, 80.3], "A", page=3),                    # 3 side
            _item("text", [335, 82, 339, 104], "J", page=3),                           # 4 side
            _item("section_header", [366, 60, 402, 72], "Letter key", page=3),         # 5 key
            _item("text", [366, 200, 546, 219], "N Overall length", page=3),           # 6 key
        ],
    }
    drawing, key = GoldIngest._snap_regions(
        page,
        3,
        [
            {"id": "front", "kind": "diagram", "title": "Front view", "description": "Labels B, D.",
             "member_item_ids": ["p3-i1", "p3-i2"]},
            {"id": "side", "kind": "diagram", "title": "Side view", "description": "Labels A, J.",
             "member_item_ids": ["p3-i3", "p3-i4"]},
            {"id": "key", "kind": "spec_block", "title": "Letter key", "member_item_ids": ["p3-i5", "p3-i6"]},
        ],
        dpi=150,
    )
    assert drawing["id"] == "front"
    assert drawing["title"] == "Front view; Side view"
    assert drawing["description"] == "Labels B, D.\n\nLabels A, J."
    assert drawing["member_item_ids"] == ["p3-i1", "p3-i2", "p3-i3", "p3-i4"]
    # The whole drawing, up to where the key starts.
    assert drawing["bbox"] == [45, 58, 366, 219]
    assert key["bbox"] == [366, 60, 546, 219]


def test_a_table_named_by_heading_and_lookalike_cells_takes_the_table_under_its_heading():
    # "PX-5" heads two tables; the model took one from the wrong one.
    page = {
        "pages": {"3": A4},
        "items": [
            _item("section_header", [45, 215, 176, 243], "Pump specific measures (mm)", page=3),  # 0
            _item("table", [42, 245, 553, 388], page=3),                                          # 1
            _item("text", [111, 250, 131, 262], "PX-5", page=3),                                  # 2 in table 1
            _item("section_header", [45, 524, 117, 552], "Motor overview", page=3),               # 3
            _item("table", [44, 552, 553, 595], page=3),                                          # 4
            _item("text", [111, 556, 131, 568], "PX-5", page=3),                                  # 5 in table 4
        ],
    }
    (region,) = GoldIngest._snap_regions(
        page, 3,
        [{"id": "pump", "kind": "table", "title": "Pump specific measures (mm)",
          "member_item_ids": ["p3-i0", "p3-i2", "p3-i5"]}],
        dpi=150,
    )
    assert region["member_item_ids"] == ["p3-i0", "p3-i1", "p3-i2"]
    assert region["bbox"] == [42, 215, 553, 388]  # the table and its heading


def test_the_heading_wins_over_a_named_table_from_further_down():
    page = {
        "pages": {"3": A4},
        "items": [
            _item("section_header", [45, 215, 176, 243], "Pump specific measures (mm)", page=3),  # 0
            _item("table", [42, 245, 553, 388], page=3),                                          # 1
            _item("text", [111, 236, 131, 260], "PX-5", page=3),                                  # 2
            _item("section_header", [45, 399, 178, 426], "Motor specific measures (mm)", page=3), # 3
            _item("table", [42, 428, 553, 517], page=3),                                          # 4
            _item("page_footer", [45, 798, 226, 819], "Norrhavn PX series", page=3),              # 5
        ],
    }
    (region,) = GoldIngest._snap_regions(
        page, 3,
        [{"id": "pump", "kind": "table", "title": "Pump specific measures (mm)",
          "member_item_ids": ["p3-i0", "p3-i2", "p3-i5", "p3-i4"]}],
        dpi=150,
    )
    assert region["member_item_ids"] == ["p3-i0", "p3-i1", "p3-i2"]
    assert region["bbox"] == [42, 215, 553, 388]


def test_a_text_block_does_not_adopt_the_table_it_brushes():
    page = {
        "pages": {"2": A4},
        "items": [
            _item("section_header", [308, 139, 360, 151], "Warranty"),                       # 0
            _item("text", [308, 157, 550, 196], "Three years on PX pumps"),                  # 1
            _item("section_header", [308, 191, 350, 203], "Noise"),                          # 2
            _item("table", [306, 204, 550, 247]),                                            # 3
            _item("text", [310, 210, 400, 222], "Sound pressure"),                           # 4
        ],
    }
    (region,) = GoldIngest._snap_regions(
        page, 2,
        [{"id": "warranty", "kind": "spec_block", "title": "Warranty", "member_item_ids": ["p2-i0", "p2-i1", "p2-i4"]}],
        dpi=150,
    )
    assert "p2-i3" not in region["member_item_ids"]
    assert region["bbox"][3] < 204


def test_a_table_two_blocks_name_goes_to_the_nearer_heading():
    page = {
        "pages": {"2": A4},
        "items": [
            _item("section_header", [308, 139, 350, 167], "Warranty"),   # 0
            _item("text", [308, 157, 550, 196], "Three years"),           # 1
            _item("section_header", [308, 191, 333, 203], "Noise"),       # 2
            _item("table", [306, 204, 550, 247]),                         # 3
        ],
    }
    warranty, noise = GoldIngest._snap_regions(
        page, 2,
        [
            {"id": "w", "kind": "spec_block", "title": "Warranty", "member_item_ids": ["p2-i0", "p2-i3"]},
            {"id": "n", "kind": "table", "title": "Noise", "member_item_ids": ["p2-i2", "p2-i3"]},
        ],
        dpi=150,
    )
    assert "p2-i3" in noise["member_item_ids"]
    assert warranty["member_item_ids"] == ["p2-i0"]
    assert warranty["bbox"][3] < 204


def test_a_block_given_only_a_box_still_wins_its_table_by_its_heading():
    page = {
        "pages": {"2": A4},
        "items": [
            _item("section_header", [308, 139, 350, 167], "Warranty"),   # 0
            _item("text", [308, 157, 550, 196], "Three years"),           # 1
            _item("section_header", [308, 191, 333, 203], "Noise"),       # 2
            _item("table", [306, 204, 550, 247]),                         # 3
        ],
    }
    warranty, noise = GoldIngest._snap_regions(
        page, 2,
        [
            {"id": "w", "kind": "spec_block", "title": "Warranty", "member_item_ids": ["p2-i0", "p2-i3"]},
            {"id": "n", "kind": "table", "title": "Noise", "bbox": [306, 191, 550, 247]},
        ],
        dpi=150,
    )
    assert warranty["member_item_ids"] == ["p2-i0"]
