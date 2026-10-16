"""A key a picture's frame takes in becomes a region of its own.

Docling drew one picture round the Norrhavn dimension drawing and the
letter key beside it. When the model folded the key into the drawing, the
drawing region spanned both; when it drew the key separately, the drawing
was cut back. The split no longer depends on which the model did.
"""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.gold_ingest import GoldIngest
from anchor.extensions.anchor_pdfs.core.ingest.geometry import headed_blocks_in

PICTURE = [45, 64, 550, 220]


def _page3() -> dict:
    items = [
        {"label": "section_header", "text": "04 Dimensions", "bbox": [45, 46, 134, 55]},
        {"label": "picture", "text": "", "bbox": PICTURE},
        {"label": "text", "text": "C", "bbox": [170, 106, 175, 112]},
        {"label": "text", "text": "Front", "bbox": [99, 192, 116, 197]},
        {"label": "section_header", "text": "Letter key", "bbox": [366, 72, 402, 79]},
        {"label": "text", "text": "A Suction flange face to discharge axis", "bbox": [366, 86, 510, 93]},
        {"label": "text", "text": "B Shaft centre height above base", "bbox": [366, 98, 491, 105]},
        {"label": "list_item", "text": "N Overall length", "bbox": [366, 209, 546, 216]},
    ]
    return {"items": [{**it, "page": 3} for it in items]}


def test_a_heading_with_entries_inside_a_picture_is_a_block():
    items = [(f"p3-i{i}", it) for i, it in enumerate(_page3()["items"])]
    blocks = headed_blocks_in(PICTURE, items)
    assert len(blocks) == 1
    assert blocks[0]["title"] == "Letter key"
    assert blocks[0]["members"] == ["p3-i4", "p3-i5", "p3-i6", "p3-i7"]
    # The drawing's own labels, left of the heading, stay with the drawing.
    assert "p3-i2" not in blocks[0]["members"]


def test_a_lone_heading_is_not_a_block():
    items = [("p3-i0", {"label": "section_header", "text": "Side", "bbox": [300, 200, 320, 208]}),
             ("p3-i1", {"label": "text", "text": "N", "bbox": [303, 210, 309, 215]})]
    assert headed_blocks_in(PICTURE, items) == []


def test_the_drawing_is_cut_back_when_the_model_folded_the_key_into_it():
    snapped = GoldIngest._snap_regions(_page3(), 3, [
        {"id": "p3-r1", "kind": "diagram", "title": "Pump dimensions diagram and letter key", "bbox": PICTURE},
    ])
    by_kind = {r["kind"]: r for r in snapped}
    key = by_kind["spec_block"]
    assert key["title"] == "Letter key"
    assert key["split_from"] == "p3-r1"
    drawing = by_kind["diagram"]
    # The drawing ends where the key begins.
    assert drawing["bbox"][2] <= key["bbox"][0]
    assert "p3-i5" not in drawing["member_item_ids"]
