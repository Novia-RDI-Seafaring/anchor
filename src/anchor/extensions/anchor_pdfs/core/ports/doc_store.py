"""DocStore protocol — durable shared documents (bronze/silver/gold)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class DocStore(Protocol):
    async def list_documents(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_index(self, slug: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_pages_meta(self, slug: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_page_text(self, slug: str, page: int) -> str | None:
        raise NotImplementedError

    async def get_page_image_path(self, slug: str, page: int) -> Path | None:
        raise NotImplementedError

    async def get_regions(self, slug: str, page: int | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def get_gold_map(self, slug: str) -> dict[str, Any] | None:
        """Full gold extraction for a document, or None when the document
        has no *complete* gold layer. Keyed on the completeness marker, so
        a crash-interrupted (partial) gold pass is reported as absent
        rather than as a truncated map."""
        raise NotImplementedError

    async def has_gold(self, slug: str) -> bool:
        """True when the gold layer for `slug` is complete (the pipeline or
        a harness session finished and committed the completeness marker).
        Partial gold from an interrupted run must return False."""
        raise NotImplementedError

    async def mark_gold_complete(self, slug: str, meta: dict[str, Any]) -> Path:
        """Atomically commit the gold completeness marker for `slug`.

        `meta` records how gold was produced (mode keyed|harness, model,
        region_count, timestamps). This is the transaction commit point:
        nothing written to gold/ is visible through `has_gold` /
        `get_gold_map` / `list_documents` until this lands."""
        raise NotImplementedError

    async def clear_gold_complete(self, slug: str) -> None:
        """Mark the gold layer incomplete before an overwriting pass, so a
        crash mid-overwrite leaves the document invisible-as-gold instead
        of a blend of old and new regions."""
        raise NotImplementedError

    async def get_page_candidates(self, slug: str, page: int) -> list[dict[str, Any]] | None:
        """Per-page docling candidate items `[{id, label, bbox, text}]`
        persisted during silver. None when the page (or document) has no
        candidates artifact."""
        raise NotImplementedError

    async def get_crop_path(self, slug: str, rel_path: str) -> Path | None:
        raise NotImplementedError

    async def get_raw_pdf_path(self, slug: str) -> Path | None:
        """Return the bronze-layer raw PDF for a document, if available.
        Stores that don't keep the raw bytes addressable (in-memory test
        doubles, S3-backed stores without a local mirror, ...) may return
        ``None``; callers must handle that case rather than reach into
        store internals."""
        raise NotImplementedError

    async def stash_bronze(self, pdf_bytes: bytes, filename: str) -> Path:
        """Write a raw PDF into bronze/. Returns path."""
        raise NotImplementedError

    async def write_silver_artifact(self, slug: str, name: str, payload: bytes | str) -> Path:
        raise NotImplementedError

    async def write_gold_region_file(self, slug: str, page: int, regions: list[dict[str, Any]]) -> Path:
        raise NotImplementedError

    async def add_derived_region(self, slug: str, region: dict[str, Any]) -> Path:
        """Append one derived region to an existing document's gold.

        A region producer (e.g. a chart digitizer) enriches an already-gold
        document: it consumes one region and writes a new one back into the
        same gold tree. The page is taken from ``region['source_ref']['page']``
        (a derived region inherits its parent's source_ref) or
        ``region['page']``. Replaces any existing region with the same ``id``
        so re-deriving is idempotent. Search picks the new region up on the
        next ``embed`` pass; this method does not embed.
        """
        raise NotImplementedError

    async def write_embeddings(self, slug: str, payload: dict[str, Any]) -> Path:
        """Write gold/<slug>/embeddings.json with the per-region vector payload.

        Expected shape:
            { "embed_model": str, "dim": int, "embedded_at": float,
              "vectors": [{"page": int, "region_id": str, "text": str, "vector": [float]}, ...] }
        """
        raise NotImplementedError

    async def get_embeddings(self, slug: str) -> dict[str, Any] | None:
        """Read gold/<slug>/embeddings.json. Returns None if not embedded yet."""
        raise NotImplementedError

    async def list_embeddings(self) -> list[dict[str, Any]]:
        """List embeddings.json files across the gold layer. Each entry:
            {"slug": str, "embed_model": str, "dim": int, "vector_count": int}
        """
        raise NotImplementedError
