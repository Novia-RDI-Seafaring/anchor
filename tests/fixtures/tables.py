"""Build current gold test tables through the production silver boundary."""

import json

from anchor.extensions.anchor_pdfs.core.ingest.region_resolution import source_region_metadata
from anchor.extensions.anchor_pdfs.core.silver import (
    build_page_candidates,
    build_pages_meta,
    normalize_items,
    table_data_from_items,
)


async def write_source_table_regions(store, slug, page, regions):
    """Give current-generation table fixtures real silver evidence to resolve."""
    items = [{**region, "label": "table", "page": page, "id": f"p{page}-i{i}"}
             for i, region in enumerate(regions)]
    await store.write_silver_artifact(slug, f"pages/{page}.items.json", json.dumps(items))
    await store.write_silver_artifact(slug, f"pages/{page}.candidates.json",
                                      json.dumps(build_page_candidates({"items": items})[page]))
    metadata = await store.get_pages_meta(slug) or {"pages": {}}
    updated = build_pages_meta({"items": items})["pages"][str(page)]
    metadata.setdefault("pages", {}).setdefault(str(page), {}).update(updated)
    await store.write_silver_artifact(slug, "pages.meta.json", json.dumps(metadata))
    await store.write_gold_region_file(slug, page, [
        {**source_region_metadata(region), "member_item_ids": [item["id"]]}
        for region, item in zip(regions, items, strict=True)
    ])


def canonical_regions(regions, *, origin="bottom-left", page_height=600):
    """Normalize the older test fixtures' declared PDF user-space geometry.

    Tests intentionally exercising stale gold must store their raw cells
    directly. This helper never manufactures a topology verdict in a fixture.
    """
    result = []
    for region in regions:
        page = region.get("page", 1)
        item = normalize_items(
            {
                "coord_origin": origin,
                "pages": {page: {"width": 600, "height": page_height}},
                "items": [
                    {
                        **region,
                        "label": "table",
                        "page": page,
                        "cells": [
                            {"row_span": 1, "col_span": 1, **cell} for cell in region["cells"]
                        ],
                    }
                ],
            }
        )["items"][0]
        result.append({**region, "bbox": item["bbox"], **table_data_from_items([item])})
    return result
