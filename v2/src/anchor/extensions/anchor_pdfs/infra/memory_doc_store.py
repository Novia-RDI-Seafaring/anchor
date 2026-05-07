"""In-memory MemoryDocStore — used by tests and ephemeral mode."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class MemoryDocStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._indexes: dict[str, dict[str, Any]] = {}
        self._pages_meta: dict[str, dict[str, Any]] = {}
        self._page_text: dict[tuple[str, int], str] = {}
        self._page_images: dict[tuple[str, int], bytes] = {}
        self._regions: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self._gold_maps: dict[str, dict[str, Any]] = {}
        self._crops: dict[tuple[str, str], bytes] = {}
        self._bronze: dict[str, bytes] = {}
        self._lock = asyncio.Lock()

    async def list_documents(self) -> list[dict[str, Any]]:
        return list(self._docs.values())

    async def get_index(self, slug: str) -> dict[str, Any] | None:
        return self._indexes.get(slug)

    async def get_pages_meta(self, slug: str) -> dict[str, Any] | None:
        return self._pages_meta.get(slug)

    async def get_page_text(self, slug: str, page: int) -> str | None:
        return self._page_text.get((slug, page))

    async def get_page_image_path(self, slug: str, page: int) -> Path | None:
        return None  # in-memory has no path

    async def get_regions(self, slug: str, page: int | None = None) -> dict[str, Any]:
        pages: dict[int, list[dict[str, Any]]] = {}
        for (s, p), regions in self._regions.items():
            if s != slug:
                continue
            if page is not None and p != page:
                continue
            pages[p] = regions
        return {"slug": slug, "pages": pages}

    async def get_gold_map(self, slug: str) -> dict[str, Any] | None:
        explicit = self._gold_maps.get(slug)
        if explicit is not None:
            return explicit
        index = self._indexes.get(slug)
        if index is None:
            return None
        regions = await self.get_regions(slug)
        return {
            "slug": slug,
            "document": index.get("document", {}),
            "outline": index.get("outline", []),
            "pages": regions.get("pages", {}),
            "pages_meta": self._pages_meta.get(slug, {}),
        }

    async def get_crop_path(self, slug: str, rel_path: str) -> Path | None:
        return None

    async def stash_bronze(self, pdf_bytes: bytes, filename: str) -> Path:
        async with self._lock:
            self._bronze[filename] = pdf_bytes
        return Path(f"memory://bronze/{filename}")

    async def write_silver_artifact(self, slug: str, name: str, payload: bytes | str) -> Path:
        # In-memory store dispatches to specific keys based on filename convention.
        if name == "index.json":
            import json
            self._indexes[slug] = json.loads(payload) if isinstance(payload, str) else json.loads(payload.decode())
        elif name == "pages.meta.json":
            import json
            self._pages_meta[slug] = json.loads(payload) if isinstance(payload, str) else json.loads(payload.decode())
        return Path(f"memory://silver/{slug}/{name}")

    async def write_gold_region_file(self, slug: str, page: int, regions: list[dict[str, Any]]) -> Path:
        async with self._lock:
            self._regions[(slug, page)] = list(regions)
        return Path(f"memory://gold/{slug}/{page}.regions.json")

    # Test helpers
    def seed_document(self, slug: str, *, filename: str = "", title: str = "", page_count: int = 0) -> None:
        self._docs[slug] = {
            "slug": slug,
            "filename": filename or f"{slug}.pdf",
            "title": title or slug,
            "page_count": page_count,
        }

    def seed_page_text(self, slug: str, page: int, text: str) -> None:
        self._page_text[(slug, page)] = text
