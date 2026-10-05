"""source_ref resolution (#242 P2b): cell > item > region > bbox.

Deterministic core over a MemoryDocStore — no model, no network.
"""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

REGION_BBOX = [50.0, 40.0, 550.0, 200.0]
CELL_BBOX = [280.0, 120.0, 340.0, 132.0]
ITEM_BBOX = [50.0, 40.0, 550.0, 60.0]


def _store(*, region_cells_have_bbox: bool = True) -> MemoryDocStore:
    store = MemoryDocStore()

    cells = [
        {"row": 0, "col": 0, "text": "Flow"},
        {"row": 0, "col": 1, "text": "35 m3/h"},
    ]
    if region_cells_have_bbox:
        cells[1]["bbox"] = CELL_BBOX

    async def seed() -> None:
        await store.write_silver_artifact(
            "lkh",
            "pages/2.candidates.json",
            json.dumps(
                [
                    {"id": "p2-i0", "label": "text", "bbox": ITEM_BBOX,
                     "text": "intro"},
                    {"id": "p2-i1", "label": "table", "bbox": REGION_BBOX,
                     "cells": [
                         {"row": 0, "col": 0, "text": "Flow"},
                         {"row": 0, "col": 1, "text": "35 m3/h",
                          "bbox": CELL_BBOX},
                     ]},
                ]
            ),
        )
        await store.write_gold_region_file(
            "lkh",
            2,
            [{"id": "r4", "kind": "table", "title": "Specs",
              "bbox": REGION_BBOX, "cells": cells,
              "member_item_ids": ["p2-i1"]}],
        )

    asyncio.run(seed())
    return store


def _resolve(store, ref):
    return asyncio.run(resolve_source_ref(store, "lkh", ref))


def test_legacy_region_ref_resolves_as_before():
    # Golden: a pre-P2b ref answers with the region bbox, nothing else.
    out = _resolve(_store(), {"page": 2, "region_id": "r4", "bbox": REGION_BBOX})
    assert out == {
        "slug": "lkh", "page": 2, "bbox": REGION_BBOX,
        "precision": "region", "region_id": "r4",
    }


def test_bare_bbox_ref_resolves_with_bbox_precision():
    out = _resolve(_store(), {"page": 2, "bbox": ITEM_BBOX})
    assert out["precision"] == "bbox"
    assert out["bbox"] == ITEM_BBOX


def test_cell_resolves_from_region_cells():
    out = _resolve(
        _store(), {"page": 2, "region_id": "r4", "cell": {"row": 0, "col": 1}}
    )
    assert out["precision"] == "cell"
    assert out["bbox"] == CELL_BBOX
    assert out["cell"] == {"row": 0, "col": 1}


def test_cell_falls_back_to_silver_geometry():
    # Region cells stored without bboxes: the silver table (#270) answers.
    out = _resolve(
        _store(region_cells_have_bbox=False),
        {"page": 2, "region_id": "r4", "cell": {"row": 0, "col": 1}},
    )
    assert out["precision"] == "cell"
    assert out["bbox"] == CELL_BBOX


def test_cell_without_stored_bbox_falls_through_to_region():
    # (0,0) has no bbox anywhere; the region layer answers instead.
    out = _resolve(
        _store(region_cells_have_bbox=False),
        {"page": 2, "region_id": "r4", "cell": {"row": 0, "col": 0}},
    )
    assert out["precision"] == "region"
    assert out["bbox"] == REGION_BBOX


def test_item_id_resolves_and_supplies_page():
    # No page in the ref: parsed from the item id.
    out = _resolve(_store(), {"item_id": "p2-i0"})
    assert out == {
        "slug": "lkh", "page": 2, "bbox": ITEM_BBOX,
        "precision": "item", "item_id": "p2-i0",
    }


def test_unknown_item_falls_through_to_region():
    out = _resolve(_store(), {"page": 2, "region_id": "r4", "item_id": "p2-i9"})
    assert out["precision"] == "region"


def test_unresolvable_ref_returns_none():
    assert _resolve(_store(), {}) is None
    assert _resolve(_store(), {"page": 9, "region_id": "r99"}) is None


class TestManyPlaces:
    """One claim, evidenced in more than one spot.

    A dimension letter in a drawing and the value under it in a table are the
    same fact seen twice. Neither is "the" place, so the ref keeps its own
    selectors as the primary -- that is where a viewer scrolls -- and names
    the rest under ``also``.
    """

    def test_resolves_every_place_on_its_own_terms(self) -> None:
        out = asyncio.run(
            resolve_source_ref(
                _store(),
                "lkh",
                {
                    "page": 2,
                    "region_id": "r4",
                    "cell": {"row": 0, "col": 1},
                    "also": [{"page": 2, "region_id": "r4", "item_id": "p2-i0"}],
                },
            )
        )
        assert out is not None
        # The primary answers exactly as it did before `also` existed.
        assert out["precision"] == "cell"
        assert out["bbox"] == CELL_BBOX
        # And the extra place carries its OWN precision, not the primary's.
        assert [a["precision"] for a in out["also"]] == ["item"]
        assert out["also"][0]["bbox"] == ITEM_BBOX

    def test_accepts_the_compact_form_a_url_can_carry(self) -> None:
        out = asyncio.run(
            resolve_source_ref(
                _store(), "lkh", {"page": 2, "region_id": "r4", "also": ["p2/r4/item:p2-i0"]}
            )
        )
        assert out is not None
        assert out["also"][0]["bbox"] == ITEM_BBOX

    def test_a_ref_without_extras_answers_exactly_as_before(self) -> None:
        out = asyncio.run(
            resolve_source_ref(_store(), "lkh", {"page": 2, "region_id": "r4"})
        )
        assert out is not None
        assert "also" not in out

    def test_one_bad_extra_does_not_cost_the_good_ones(self) -> None:
        # A highlight that never appears is worse than a partial one, and the
        # reader cannot tell the difference between "unresolvable" and "broken".
        out = asyncio.run(
            resolve_source_ref(
                _store(),
                "lkh",
                {
                    "page": 2,
                    "region_id": "r4",
                    "also": ["not-a-place", {"page": 2, "region_id": "r4", "item_id": "p2-i0"}],
                },
            )
        )
        assert out is not None
        assert len(out["also"]) == 1

    def test_an_unresolvable_primary_still_fails_the_whole_answer(self) -> None:
        # The primary is the place the caller navigates to. Without it there
        # is nowhere to go, extras or not.
        out = asyncio.run(
            resolve_source_ref(_store(), "lkh", {"also": ["p2/r4"]})
        )
        assert out is None

    def test_places_do_not_nest(self) -> None:
        out = asyncio.run(
            resolve_source_ref(
                _store(),
                "lkh",
                {
                    "page": 2,
                    "region_id": "r4",
                    "also": [
                        {"page": 2, "region_id": "r4", "item_id": "p2-i0",
                         "also": [{"page": 2, "region_id": "r4"}]}
                    ],
                },
            )
        )
        assert out is not None
        assert "also" not in out["also"][0]

    def test_caps_how_many_places_one_ref_may_name(self) -> None:
        # A highlight the reader cannot count at a glance is not evidence.
        from anchor.extensions.anchor_pdfs.core.source_ref_resolve import MAX_ALSO

        out = asyncio.run(
            resolve_source_ref(
                _store(),
                "lkh",
                {"page": 2, "region_id": "r4", "also": ["p2/r4/item:p2-i0"] * (MAX_ALSO + 5)},
            )
        )
        assert out is not None
        assert len(out["also"]) == MAX_ALSO


class TestCompactPlaceGrammar:
    """The form a place takes when it has to survive a URL.

    Agents write whole ref objects through MCP and the CLI. An ``anchor:``
    link in a Markdown card and an ``also=`` query parameter have no room
    for nested objects, so a place collapses to one readable token.
    """

    def test_reads_the_shapes_a_reference_actually_takes(self) -> None:
        from anchor.extensions.anchor_pdfs.core.source_ref_resolve import parse_place

        assert parse_place("p3") == {"page": 3}
        assert parse_place("p3/r4") == {"page": 3, "region_id": "r4"}
        assert parse_place("p3/r1/item:p3-i6") == {
            "page": 3, "region_id": "r1", "item_id": "p3-i6",
        }
        assert parse_place("p3/r2/cell:1,2") == {
            "page": 3, "region_id": "r2", "cell": {"row": 1, "col": 2},
        }

    def test_refuses_what_it_cannot_read_instead_of_guessing(self) -> None:
        from anchor.extensions.anchor_pdfs.core.source_ref_resolve import parse_place

        for bad in ["", "   ", "r4", "3/r4", "p3/r2/cell:x,y", "p3/r2/cell:1",
                    "p3/r1/unknown:x", "pages/3"]:
            assert parse_place(bad) is None, bad


class TestStrokePlaces:
    """A place that is a stroke rather than a box.

    A dimension on an engineering drawing is a span between two witness lines.
    Boxing it would cover the part of the drawing the span is measuring, so a
    place can name the stroke the draughtsman already drew instead.
    """

    def test_answers_with_the_stroke_and_the_bounds_it_occupies(self) -> None:
        out = asyncio.run(
            resolve_source_ref(
                _store(), "lkh", {"page": 2, "line": [103.2, 93.3, 117.3, 93.3]}
            )
        )
        assert out is not None
        assert out["precision"] == "line"
        assert out["line"] == [103.2, 93.3, 117.3, 93.3]
        # Bounds are there for callers that only understand boxes.
        assert out["bbox"] == [103.2, 93.3, 117.3, 93.3]

    def test_carries_a_stroke_alongside_the_places_it_explains(self) -> None:
        # One reference: the value in the table, the callout naming it, and
        # the dimension it measures.
        out = asyncio.run(
            resolve_source_ref(
                _store(),
                "lkh",
                {
                    "page": 2,
                    "region_id": "r4",
                    "cell": {"row": 0, "col": 1},
                    "also": ["p2/r4/item:p2-i0", "p2/line:10,20,30,20"],
                },
            )
        )
        assert out is not None
        assert [a["precision"] for a in out["also"]] == ["item", "line"]
        assert out["also"][1]["line"] == [10.0, 20.0, 30.0, 20.0]

    def test_takes_a_stroke_of_more_than_two_points(self) -> None:
        out = asyncio.run(
            resolve_source_ref(_store(), "lkh", {"page": 2, "line": [0, 0, 10, 0, 10, 10]})
        )
        assert out is not None
        assert out["line"] == [0.0, 0.0, 10.0, 0.0, 10.0, 10.0]

    def test_refuses_an_odd_or_too_short_run_of_coordinates(self) -> None:
        from anchor.extensions.anchor_pdfs.core.source_ref_resolve import parse_place

        assert parse_place("p3/line:1,2") is None
        assert parse_place("p3/line:1,2,3") is None
        assert parse_place("p3/line:a,b,c,d") is None
        assert parse_place("p3/line:103.2,93.3,117.3,93.3") == {
            "page": 3, "line": [103.2, 93.3, 117.3, 93.3],
        }
