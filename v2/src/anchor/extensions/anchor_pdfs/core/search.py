"""Semantic search over gold-region embeddings.

Pure core: takes a query vector and an iterable of (slug, embeddings.json
payload) tuples, returns the top-k matches by cosine similarity. All
vectors are already L2-normalised at embed time, so the dot product is
the cosine.

A note on the model-compat contract: each embeddings.json carries its
own ``embed_model``. ``search`` requires that ALL inputs share the
same model — mixing 384-d bge vectors with 1536-d OpenAI vectors in
the same nearest-neighbour pool is a category error. Caller is expected
to group/filter by model before calling.
"""
from __future__ import annotations

from typing import Iterable


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def search(
    *,
    query_vector: list[float],
    docs: Iterable[tuple[str, dict]],
    k: int = 10,
) -> list[dict]:
    """Cosine top-k across pre-loaded embeddings.

    ``docs`` is an iterable of ``(slug, embeddings_payload)`` tuples, each
    payload as written by ``IngestService.embed_document``. Returns
    ``[{slug, page, region_id, text, score}]`` sorted descending by score.
    """
    hits: list[dict] = []
    qd = len(query_vector)
    for slug, payload in docs:
        if int(payload.get("dim", 0)) != qd:
            # Model mismatch — caller bug, but be loud about it by skipping
            # rather than returning garbage scores.
            continue
        for v in payload.get("vectors", []):
            score = cosine(query_vector, v.get("vector", []))
            hits.append({
                "slug": slug,
                "page": v.get("page"),
                "region_id": v.get("region_id"),
                "text": v.get("text", ""),
                "score": score,
            })
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:k]
