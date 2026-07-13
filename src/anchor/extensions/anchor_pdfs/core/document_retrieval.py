"""Embedding and semantic retrieval for ingested document regions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from anchor.core.clock import Clock
from anchor.extensions.anchor_pdfs.core.events import IngestProgress
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.embedder import Embedder
from anchor.extensions.anchor_pdfs.core.search import search as search_topk
from anchor.extensions.anchor_pdfs.core.silver import region_search_text

Publish = Callable[[Any, str | None], Awaitable[None]]


class DocumentRetrieval:
    """Own document embedding persistence and compatible-model search."""

    def __init__(
        self,
        store: DocStore,
        *,
        embedder: Embedder | None,
        embed_model_id: str | None,
        clock: Clock,
        publish: Publish,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.embed_model_id = embed_model_id
        self.clock = clock
        self.publish = publish

    async def embed_document(
        self,
        slug: str,
        *,
        publish_workspace_id: str | None = None,
    ) -> int:
        """Embed every gold region and persist its vectors."""
        if self.embedder is None:
            raise RuntimeError("IngestService.embed_document called but no embedder wired")
        gold = await self.store.get_gold_map(slug)
        if gold is None:
            return 0

        items: list[tuple[int, str, str]] = []
        for page_key, regions in (gold.get("pages") or {}).items():
            try:
                page = int(page_key)
            except (TypeError, ValueError):
                continue
            for region in regions:
                region_id = region.get("id")
                if not region_id:
                    continue
                text = region_search_text(region)
                if text:
                    items.append((page, region_id, text))

        if not items:
            return 0
        vectors = await self.embedder.embed([text for _, _, text in items])
        payload: dict[str, Any] = {
            "embed_model": self.embed_model_id or "unknown",
            "dim": len(vectors[0]) if vectors else 0,
            "embedded_at": self.clock.now(),
            "vectors": [
                {
                    "page": page,
                    "region_id": region_id,
                    "text": text,
                    "vector": vector,
                }
                for (page, region_id, text), vector in zip(
                    items,
                    vectors,
                    strict=True,
                )
            ],
        }
        await self.store.write_embeddings(slug, payload)
        await self.publish(
            IngestProgress(
                slug=slug,
                stage="embed",
                current=len(items),
                total=len(items),
            ),
            publish_workspace_id,
        )
        return len(items)

    async def search(self, query: str, *, k: int = 10) -> dict[str, Any]:
        """Search embeddings that use the active query model."""
        if self.embedder is None:
            raise RuntimeError("IngestService.search called but no embedder wired")
        query_model = self.embed_model_id or "unknown"
        vectors = await self.embedder.embed([query])
        if not vectors:
            return {
                "query": query,
                "embed_model": query_model,
                "k": k,
                "hits": [],
                "doc_count": 0,
                "skipped": [],
            }

        manifest = await self.store.list_embeddings()
        compatible = [
            item for item in manifest if item.get("embed_model") == query_model
        ]
        skipped = [
            {
                "slug": item.get("slug", ""),
                "stored_model": item.get("embed_model") or "unknown",
                "query_model": query_model,
                "reason": "embed_model_mismatch",
            }
            for item in manifest
            if item.get("embed_model") != query_model
        ]
        documents: list[tuple[str, dict[str, Any]]] = []
        for item in compatible:
            payload = await self.store.get_embeddings(item["slug"])
            if payload is not None:
                documents.append((item["slug"], payload))

        return {
            "query": query,
            "embed_model": query_model,
            "k": k,
            "hits": search_topk(query_vector=vectors[0], docs=documents, k=k),
            "doc_count": len(documents),
            "skipped": skipped,
        }
