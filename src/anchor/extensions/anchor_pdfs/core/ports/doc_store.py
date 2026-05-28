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
