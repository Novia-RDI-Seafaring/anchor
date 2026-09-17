from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.fixtures.tables import canonical_regions


def _table(region_id="r1", *, page=1, entries=(("Temperature", "42"),), y=10):
    cells = []
    for index, (key, value) in enumerate(entries):
        top = y + index * 20
        cells.extend(
            [
                {"row": index, "col": 0, "text": key, "bbox": [10, top, 55, top + 10]},
                {"row": index, "col": 1, "text": value, "bbox": [60, top, 90, top + 10]},
            ]
        )
    return canonical_regions(
        [
            {
                "id": region_id,
                "kind": "table",
                "page": page,
                "bbox": [0, y, 100, y + len(entries) * 20],
                "cells": cells,
            }
        ],
        origin="top-left",
    )[0]


def _claim(*, key="Pressure", value="42", region_id="r1", **ref_fields):
    ref = {"slug": "doc", "page": 1, "coord_origin": "top-left", **ref_fields}
    if region_id is not None:
        ref["region_id"] = region_id
    return {"rows": [{"key": key, "value": value, "source_ref": ref}]}


async def test_missing_explicit_region_never_substitutes_another_fact():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table()])
    data = _claim(region_id="missing-r9", bbox=[200, 200, 250, 230])

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched == data
    assert enriched is data


@pytest.mark.parametrize(
    "key,value",
    [("Pressure", "42"), ("Temperature", "41"), ("Temperature", "Temperature"), (None, "42")],
)
async def test_refinement_requires_both_halves_of_the_certified_pair(key, value):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table()])
    data = _claim(key=key, value=value)

    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("region_id", ["pressure", None])
async def test_region_selection_is_unique_and_independent_of_source_order(reverse, region_id):
    store = MemoryDocStore()
    regions = [_table("temperature"), _table("pressure", entries=(("Pressure", "42"),), y=50)]
    await store.write_gold_region_file("doc", 1, regions[::-1] if reverse else regions)
    data = _claim(region_id=region_id)

    ref = (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"]

    assert ref["bbox"] == [60, 50, 90, 60]
    assert ref["region_id"] == "pressure"
    assert (ref["slug"], ref["page"]) == ("doc", 1)


@pytest.mark.parametrize("reverse", [False, True])
async def test_omitted_region_abstains_on_repeated_key_value_across_tables(reverse):
    store = MemoryDocStore()
    regions = [
        _table("a", entries=(("Pressure", "42"),)),
        _table("b", entries=(("Pressure", "42"),), y=50),
    ]
    await store.write_gold_region_file("doc", 1, regions[::-1] if reverse else regions)
    data = _claim(region_id=None)

    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("reverse", [False, True])
async def test_repeated_values_use_certified_key_not_cell_order(reverse):
    store = MemoryDocStore()
    table = _table(entries=(("Pressure", "42"), ("Temperature", "42"), ("Threshold", "42")))
    if reverse:
        # Re-certify the reordered extractor input at the real ingest seam.
        table = canonical_regions([{**table, "cells": table["cells"][::-1]}], origin="top-left")[0]
    await store.write_gold_region_file("doc", 1, [table])
    data = _claim(key="Temperature")
    ref = (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"]
    assert ref["bbox"] == [60, 30, 90, 40]


async def test_page_and_document_constrain_even_an_equal_key_value():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    await store.write_gold_region_file(
        "doc", 2, [_table(page=2, entries=(("Pressure", "42"),), y=50)]
    )
    await store.write_gold_region_file("other", 1, [_table(entries=(("Pressure", "42"),), y=90)])
    for slug, page, expected in [("doc", 1, 10), ("doc", 2, 50), ("other", 1, 90)]:
        data = _claim(slug=slug, page=page)
        ref = (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"]
        assert ref["bbox"] == [60, expected, 90, expected + 10]
        assert (ref["slug"], ref["page"]) == (slug, page)
    for fields in ({"page": 3}, {"slug": "absent"}):
        data = _claim(**fields)
        assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize(
    "field,invalid",
    [
        ("slug", None),
        ("slug", ""),
        ("page", None),
        ("page", True),
        ("page", "1"),
        ("page", 0),
        ("region_id", None),
        ("region_id", ""),
        ("region_id", 9),
        ("kind", "fmu-variable"),
    ],
)
async def test_explicit_invalid_scope_does_not_fall_through_to_node_defaults(field, invalid):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim()
    data["source_ref"] = {"slug": "doc", "page": 1, "region_id": "r1"}
    data["rows"][0]["source_ref"][field] = invalid
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("override", [{"slug": "other"}, {"page": 2}])
async def test_row_override_does_not_inherit_region_from_a_different_source_scope(override):
    store = MemoryDocStore()
    # The two valid matches make a missing row region ambiguous. Inheriting
    # the parent's r1 would silently select one of them in another source.
    for slug in ("doc", "other"):
        for page in (1, 2):
            await store.write_gold_region_file(
                slug,
                page,
                [
                    _table("r1", page=page, entries=(("Pressure", "42"),)),
                    _table("r2", page=page, entries=(("Pressure", "42"),), y=50),
                ],
            )
    data = _claim(region_id=None, **override)
    data["source_ref"] = {"slug": "doc", "page": 1, "region_id": "r1"}
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("source_ref", [None, "invalid", []])
async def test_explicit_cleared_or_malformed_row_ref_is_not_recreated(source_ref):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim()
    data["source_ref"] = {"slug": "doc", "page": 1, "region_id": "r1"}
    data["rows"][0]["source_ref"] = source_ref
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_absent_or_partial_row_ref_can_use_compatible_complete_node_scope():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    for ref in ({}, {"page": 1}):
        data = _claim()
        data["source_ref"] = {"slug": "doc", "page": 1, "region_id": "r1"}
        data["rows"][0]["source_ref"] = ref
        out = await enrich_spec_row_source_refs(data, store)
        assert out["rows"][0]["source_ref"]["bbox"] == [60, 10, 90, 20]
    data["rows"][0].pop("source_ref")
    assert (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"]["bbox"] == [
        60,
        10,
        90,
        20,
    ]


@pytest.mark.parametrize(
    "extra",
    [
        {"bbox": [200, 200, 250, 230]},
        {"bbox": [60, 10, 90, 20], "detail": {"cell_bbox": [200, 200, 250, 230]}},
        {"bbox": [0, 0, 100, 100], "coord_origin": None},
        {"bbox": [0, 0, 100, 100], "coord_origin": "unknown"},
        {"bbox": [0, 0, float("nan"), 100]},
        {"bbox": [90, 20, 60, 10]},
        {
            "detail": {
                "table_topology": {"digest": "stale", "key_cell_id": "c0", "value_cell_id": "c1"}
            }
        },
    ],
)
async def test_existing_geometry_and_pair_detail_cannot_be_silently_retargeted(extra):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim(**extra)
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("bbox", [[0, 0, 100, 100], [60, 10, 90, 20]])
async def test_compatible_coarse_or_precise_geometry_refines_in_the_same_region(bbox):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim(bbox=bbox, detail={"cell_bbox": bbox, "quote": "42", "match": {"occurrence": 1}})
    ref = (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"]
    assert ref["bbox"] == ref["detail"]["cell_bbox"] == [60, 10, 90, 20]
    assert ref["coord_origin"] == "top-left"
    assert ref["detail"]["quote"] == "42"
    assert ref["detail"]["match"] == {"occurrence": 1}


async def test_node_geometry_constrains_inherited_reference():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = {
        "source_ref": {
            "slug": "doc",
            "page": 1,
            "coord_origin": "top-left",
            "bbox": [200, 200, 250, 230],
        },
        "rows": [{"key": "Pressure", "value": "42"}],
    }
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_unknown_origin_geometry_cannot_borrow_node_origin():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim(bbox=[0, 0, 100, 100])
    data["rows"][0]["source_ref"].pop("coord_origin")
    data["source_ref"] = {"slug": "doc", "page": 1, "region_id": "r1", "coord_origin": "top-left"}
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("cells", [None, [], [None], [{"text": "42"}]])
async def test_unvalidated_or_malformed_gold_cannot_refine(cells):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [{"id": "r1", "cells": cells}])
    data = _claim()
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_ambiguous_g1_topology_remains_unusable():
    table = _table(entries=(("Pressure", "42"), ("Temperature", "41")))
    table["cells"][1]["bbox"] = [60, 10, 90, 40]
    table = canonical_regions([table], origin="top-left")[0]
    assert table["table_topology"]["status"] == "ambiguous"
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [table])
    data = _claim()
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_repeated_pair_within_a_table_is_not_disambiguated_by_first_bbox():
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc", 1, [_table(entries=(("Pressure", "42"), ("Pressure", "42")))]
    )
    data = _claim(bbox=[60, 10, 90, 20])
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"pages": None},
        {"pages": []},
        {"pages": {1: "invalid"}},
        {"slug": "other", "pages": {1: []}},
    ],
)
async def test_malformed_page_payload_is_a_safe_noop(payload, monkeypatch):
    store = MemoryDocStore()

    async def get_regions(slug, page):
        return payload

    monkeypatch.setattr(store, "get_regions", get_regions)
    data = _claim()
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("region_id", ["r1", None])
async def test_duplicate_explicit_identity_is_unresolved_without_repairing_ids(region_id):
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc", 1, [_table(entries=(("Pressure", "42"),)), _table(y=50)]
    )
    data = _claim(region_id=region_id)
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_matching_g1_proof_is_preserved_but_different_pair_proof_is_not_retargeted():
    from anchor.extensions.anchor_pdfs.core.pointed_extraction import fill_shape

    table = _table(entries=(("Pressure", "42"), ("Temperature", "42")))
    _, refs, _ = fill_shape({"Pressure": "string", "Temperature": "string"}, [table], slug="doc")
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [table])
    data = _claim(**refs["/Pressure"])
    assert (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"] == {
        **refs["/Pressure"], "cell": {"row": 0, "col": 1},
    }
    data["rows"][0]["source_ref"]["detail"] = refs["/Temperature"]["detail"]
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_omitted_region_does_not_reinterpret_bottom_left_geometry():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim(region_id=None, bbox=[0, 100, 100, 0], coord_origin="bottom-left")
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize(
    "field,bad",
    [
        ("key_text", "Temperature"),
        ("key_bbox", [200, 200, 250, 230]),
        ("row", 9),
        ("version", 999),
        ("association_basis", "value_only"),
    ],
)
async def test_g1_proof_details_must_agree_with_the_selected_pair(field, bad):
    from anchor.extensions.anchor_pdfs.core.pointed_extraction import fill_shape

    table = _table(entries=(("Pressure", "42"),))
    _, refs, _ = fill_shape({"Pressure": "string"}, [table], slug="doc")
    data = _claim(**refs["/Pressure"])
    data["rows"][0]["source_ref"]["detail"]["table_topology"][field] = bad
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [table])
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_explicit_stale_region_remains_unresolved_even_if_exact_pair_exists_elsewhere():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Pressure", "42"),))])
    data = _claim(region_id="missing-r9", bbox=[0, 0, 100, 100])
    assert await enrich_spec_row_source_refs(data, store) is data


@pytest.mark.parametrize("invalid_page", [2, "1", True])
async def test_region_page_metadata_must_agree_with_requested_page(invalid_page):
    store = MemoryDocStore()
    table = _table(entries=(("Pressure", "42"),))
    table["page"] = invalid_page
    await store.write_gold_region_file("doc", 1, [table])
    data = _claim()
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_unit_case_difference_is_a_value_mismatch():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Length", "42 mm"),))])
    data = _claim(key="Length", value="42 Mm")
    assert await enrich_spec_row_source_refs(data, store) is data


async def test_whitespace_and_key_case_normalization_preserve_value_case():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table(entries=(("Length", "42 mm"),))])
    data = _claim(key="  LENGTH ", value="42\nmm")
    ref = (await enrich_spec_row_source_refs(data, store))["rows"][0]["source_ref"]
    assert ref["bbox"] == [60, 10, 90, 20]


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_uses_matching_gold_cell_bbox():
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc",
        2,
        canonical_regions(
            [
                {
                    "id": "r1",
                    "kind": "table",
                    "title": "Data",
                    "page": 2,
                    "bbox": [0, 100, 200, 0],
                    "cells": [
                        {"row": 0, "col": 0, "text": "Field", "bbox": [10, 90, 60, 80]},
                        {"row": 0, "col": 1, "text": "Value", "bbox": [80, 90, 140, 80]},
                    ],
                }
            ]
        ),
    )
    data = {
        "rows": [
            {
                "key": "Field",
                "value": "Value",
                "source_ref": {
                    "slug": "doc",
                    "page": 2,
                    "region_id": "r1",
                    "bbox": [0, 100, 200, 0],
                    "coord_origin": "bottom-left",
                    "detail": {"cell_bbox": [10, 700, 30, 680]},
                    "approx_bbox": [0, 700, 200, 680],
                },
            }
        ],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"]["bbox"] == [80.0, 510.0, 140.0, 520.0]
    assert enriched["rows"][0]["source_ref"]["coord_origin"] == "top-left"
    assert enriched["rows"][0]["source_ref"]["detail"]["cell_bbox"] == [80.0, 510.0, 140.0, 520.0]
    assert enriched["rows"][0]["source_ref"]["approx_bbox"] is None
    assert enriched["rows"][0]["source_ref"]["cell"] == {"row": 0, "col": 1}


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_does_not_verify_an_unprinted_unit_suffix():
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc",
        1,
        canonical_regions(
            [
                {
                    "id": "r1",
                    "kind": "table",
                    "title": "Data",
                    "page": 1,
                    "bbox": [0, 100, 200, 0],
                    "cells": [
                        {"row": 0, "col": 0, "text": "Length", "bbox": [10, 90, 60, 80]},
                        {"row": 0, "col": 1, "text": "42", "bbox": [80, 90, 140, 80]},
                    ],
                }
            ]
        ),
    )
    data = {
        "source_doc_slug": "doc",
        "rows": [
            {
                "key": "Length",
                "value": "42 mm",
                "source_region_id": "r1",
                "source_ref": {"page": 1, "bbox": [0, 100, 200, 0]},
            }
        ],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched is data


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_uses_key_to_disambiguate_duplicate_values():
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc",
        1,
        canonical_regions(
            [
                {
                    "id": "r1",
                    "kind": "table",
                    "title": "Data",
                    "page": 1,
                    "bbox": [0, 100, 200, 0],
                    "cells": [
                        {"row": 0, "col": 0, "text": "First", "bbox": [10, 90, 60, 80]},
                        {"row": 0, "col": 1, "text": "Shared", "bbox": [80, 90, 140, 80]},
                        {"row": 1, "col": 0, "text": "Second", "bbox": [10, 70, 60, 60]},
                        {"row": 1, "col": 1, "text": "Shared", "bbox": [80, 70, 140, 60]},
                    ],
                }
            ]
        ),
    )
    data = {
        "source_doc_slug": "doc",
        "source_region_id": "r1",
        "rows": [
            {
                "key": "Second",
                "value": "Shared",
                "source_ref": {"page": 1},
            }
        ],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"] == {
        "coord_origin": "top-left",
        "slug": "doc",
        "page": 1,
        "region_id": "r1",
        "bbox": [80.0, 530.0, 140.0, 540.0],
        "cell": {"row": 1, "col": 1},
    }


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_accepts_row_level_region_id():
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc",
        1,
        canonical_regions(
            [
                {
                    "id": "r1",
                    "kind": "table",
                    "title": "Data",
                    "page": 1,
                    "bbox": [0, 100, 200, 0],
                    "cells": [
                        {"row": 0, "col": 0, "text": "Field", "bbox": [10, 90, 60, 80]},
                        {"row": 0, "col": 1, "text": "Result", "bbox": [80, 90, 140, 80]},
                    ],
                }
            ]
        ),
    )
    data = {
        "source_doc_slug": "doc",
        "rows": [
            {
                "key": "Field",
                "value": "Result",
                "source_region_id": "r1",
                "source_ref": {"page": 1, "bbox": [0, 500, 200, 600], "coord_origin": "top-left"},
            }
        ],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"] == {
        "coord_origin": "top-left",
        "slug": "doc",
        "page": 1,
        "region_id": "r1",
        "bbox": [80.0, 510.0, 140.0, 520.0],
        "cell": {"row": 0, "col": 1},
    }


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_leaves_ambiguous_values_unchanged():
    store = MemoryDocStore()
    await store.write_gold_region_file(
        "doc",
        1,
        canonical_regions(
            [
                {
                    "id": "r1",
                    "kind": "table",
                    "title": "Data",
                    "page": 1,
                    "bbox": [0, 100, 200, 0],
                    "cells": [
                        {"row": 0, "col": 0, "text": "Shared", "bbox": [10, 90, 60, 80]},
                        {"row": 1, "col": 0, "text": "Shared", "bbox": [10, 70, 60, 60]},
                    ],
                }
            ]
        ),
    )
    data = {
        "rows": [
            {
                "key": "Unknown",
                "value": "Shared",
                "source_ref": {
                    "slug": "doc",
                    "page": 1,
                    "region_id": "r1",
                    "bbox": [0, 100, 200, 0],
                },
            }
        ],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched is data


@pytest.mark.asyncio
async def test_recorded_cell_selector_round_trips_through_the_resolver():
    """Writer + resolver contract (#242 P2c): the `cell` the enrichment

    records is exactly what `resolve_source_ref` needs to re-answer with
    the same cell bbox at `precision == "cell"`.
    """
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 2, canonical_regions([{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 2,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Field", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "Value", "bbox": [80, 90, 140, 80]},
        ],
    }], origin="bottom-left", page_height=600))
    data = {
        "rows": [{
            "key": "Field",
            "value": "Value",
            "source_ref": {"slug": "doc", "page": 2, "region_id": "r1", "bbox": [0, 100, 200, 0], "coord_origin": "bottom-left"},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)
    ref = enriched["rows"][0]["source_ref"]
    assert ref["cell"] == {"row": 0, "col": 1}

    resolved = await resolve_source_ref(store, "doc", ref)
    assert resolved is not None
    assert resolved["precision"] == "cell"
    assert resolved["bbox"] == ref["bbox"] == [80.0, 510.0, 140.0, 520.0]


@pytest.mark.parametrize("cell", [{"row": 1, "col": 1}, {"row": 0, "col": 0}, "invalid"])
async def test_conflicting_navigation_cell_cannot_be_retargeted(cell):
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [_table()])
    data = _claim(key="Temperature", cell=cell)
    assert await enrich_spec_row_source_refs(data, store) == data
