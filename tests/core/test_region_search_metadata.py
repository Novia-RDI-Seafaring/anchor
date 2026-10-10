"""Metadata-only queries stay findable through every embedding entry point."""
from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import pytest

from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.core.silver import region_search_text
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.extensions.anchor_pdfs.infra.memory_session_store import (
    MemoryIngestSessionStore,
)
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)


class MetadataEmbedder:
    """Rank by two metadata terms that never appear in source content."""

    model_id = "metadata-test"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vector = [float(term in lowered) for term in ("cavitation", "lkh-85")]
            vector.append(1.0)
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector])
        return vectors


@pytest.mark.parametrize("entry_point", ["keyed", "harness", "reembed"])
@pytest.mark.parametrize("query", ["cavitation", "LKH-85"])
def test_metadata_only_query_selects_matching_region(entry_point, query):
    async def run():
        store = MemoryDocStore()
        bus = MemoryEventBus()
        embedder = MetadataEmbedder()
        extractor = FakePdfExtractor(docling={"items": [{
            "label": "text", "text": "Pressure 17 bar", "page": 1,
            "bbox": [10, 20, 100, 40],
        }]})
        renderer = FakePdfRenderer()
        ingest = IngestService(
            store, bus, extractor=extractor, renderer=renderer, embedder=embedder,
        )
        session = IngestSessionService(
            store, MemoryIngestSessionStore(), bus,
            extractor=extractor, renderer=renderer, embedder=embedder,
        )
        # Insert the distractor first: a tie must not accidentally pass.
        for slug in ("a-distractor", "z-target"):
            region: dict[str, Any] = {
                "id": "r1", "kind": "text", "title": "Overview",
                "description": "Operating limits",
                "tags": ["cavitation"] if slug == "z-target" else [],
                "entities": ["LKH-85"] if slug == "z-target" else [],
            }
            if entry_point == "keyed":
                keyed = IngestService(
                    store, bus, extractor=extractor, renderer=renderer,
                    embedder=embedder, polisher=FakePolisher(),
                    region_extractor=FakeRegionExtractor([
                        dict(region, bbox=[10, 20, 100, 40]),
                    ]),
                )
                result = await keyed.ingest_pdf(b"%PDF-fake", f"{slug}.pdf")
                assert result["embedded_count"] == 1
                assert await store.has_gold(slug)
            elif entry_point == "harness":
                order = await session.ingest_begin(b"%PDF-fake", f"{slug}.pdf")
                verdict = await session.ingest_submit_page(
                    order["session_id"], 1,
                    regions=[dict(region, member_item_ids=["p1-i0"])],
                )
                assert verdict["accepted"] is True
                result = await session.ingest_finalize(order["session_id"])
                assert result["finalized"] is True
            else:
                store.seed_document(slug, page_count=1)
                await store.write_silver_artifact(slug, "index.json", json.dumps({
                    "document": {"page_count": 1, "filename": f"{slug}.pdf"},
                }))
                await store.write_gold_region_file(
                    slug, 1, [dict(region, content="Pressure 17 bar")],
                )
                await store.mark_gold_complete(slug, {"region_count": 1})
                assert await ingest.embed_document(slug) == 1

        result = await ingest.search(query, k=1)
        assert result["hits"][0]["slug"] == "z-target"
        assert result["hits"][0]["score"] > 0.5
        assert "Pressure 17 bar" in result["hits"][0]["text"]

    asyncio.run(run())


def test_metadata_is_deduplicated_and_malformed_entries_are_ignored():
    text = region_search_text({
        "title": "Operating limits", "description": "Supported pumps",
        "content": "Pressure 17 bar",
        "tags": [" operating   LIMITS ", "cavitation", "", None, 17, {}],
        "entities": ["LKH-85", "CAVITATION", " supported pumps "],
    })
    assert text.split("\n\n") == [
        "Operating limits", "Supported pumps", "Pressure 17 bar",
        "cavitation", "LKH-85",
    ]
    assert region_search_text({
        "title": "Overview", "tags": "malformed", "entities": {"name": "bad"},
    }) == "Overview"


def test_metadata_preserves_undescribed_table_cell_fallback():
    text = region_search_text({
        "title": "Limits", "description": " ", "tags": ["pressure"],
        "entities": ["LKH-85"],
        "cells": [
            {"row": 0, "col": 0, "text": "Pressure"},
            {"row": 0, "col": 1, "text": "17 bar"},
        ],
    })
    assert "17 bar" in text
    assert "LKH-85" in text
