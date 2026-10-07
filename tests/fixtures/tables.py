"""Build current gold test tables through the production silver boundary."""

from anchor.extensions.anchor_pdfs.core.silver import normalize_items, table_data_from_items


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
