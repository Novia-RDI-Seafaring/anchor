"""Embed gold regions for semantic search.

Produces `embeddings.jsonl` in the data directory — one line per region with:
    { region_id, doc_slug, page, text, vector }

Uses OpenAI `text-embedding-3-large` (3072 dims, matching existing pgvector setup).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def _region_text(region: dict[str, Any]) -> str:
    """Flatten a region into an embeddable text string."""
    parts: list[str] = []
    if region.get("title"):
        parts.append(region["title"])
    if region.get("description"):
        parts.append(region["description"])
    if region.get("markdown"):
        parts.append(region["markdown"][:2000])
    if region.get("entities"):
        parts.append("Entities: " + ", ".join(region["entities"]))
    if region.get("tags"):
        parts.append("Tags: " + ", ".join(region["tags"]))
    return "\n".join(parts)


def collect_region_texts(gold_dir: Path) -> list[dict[str, Any]]:
    """Collect all regions as {region_id, doc_slug, page, text} dicts."""
    items: list[dict[str, Any]] = []
    for slug_dir in sorted(gold_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        pages_dir = slug_dir / "pages"
        if not pages_dir.is_dir():
            continue
        slug = slug_dir.name
        for region_file in sorted(pages_dir.glob("*.regions.json")):
            try:
                data = json.loads(region_file.read_text())
            except Exception:
                continue
            for region in data.get("regions", []):
                text = _region_text(region)
                if not text.strip():
                    continue
                items.append({
                    "region_id": region.get("id", ""),
                    "doc_slug": slug,
                    "page": region.get("page", 0),
                    "kind": region.get("kind", ""),
                    "title": region.get("title", ""),
                    "text": text,
                })
    return items


def embed_regions(
    gold_dir: Path,
    out_path: Path,
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 50,
) -> int:
    """Embed all gold regions and write to a JSONL file.

    Returns the number of regions embedded.
    """
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    items = collect_region_texts(gold_dir)
    if not items:
        logger.info("embed: no regions to embed")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            texts = [it["text"] for it in batch]
            response = client.embeddings.create(model=model, input=texts)

            for item, emb in zip(batch, response.data):
                record = {
                    "region_id": item["region_id"],
                    "doc_slug": item["doc_slug"],
                    "page": item["page"],
                    "kind": item["kind"],
                    "title": item["title"],
                    "text": item["text"],
                    "vector": emb.embedding,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    logger.info("embed: wrote %d region embeddings to %s", count, out_path)
    return count
