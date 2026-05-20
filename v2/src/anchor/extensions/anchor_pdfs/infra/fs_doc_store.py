"""Filesystem-backed DocStore.

Mirrors the on-disk layout the v1 packages already use, so v1 and v2 can
read/write the same data dir during migration:

    data_dir/
        bronze/<filename>.pdf
        silver/<slug>/
            index.json
            pages.meta.json
            pages/<n>.md, <n>.raw.md, <n>.png
        gold/<slug>/
            pages/<n>.regions.json
            pages/<n>/<region-id>.png
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from anchor.core.ids import slugify


class FsDocStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.bronze = self.data_dir / "bronze"
        self.silver = self.data_dir / "silver"
        self.gold = self.data_dir / "gold"
        for p in (self.bronze, self.silver, self.gold):
            p.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def list_documents(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.silver.is_dir():
            return out
        for d in sorted(self.silver.iterdir()):
            if not d.is_dir():
                continue
            slug = d.name
            idx_path = d / "index.json"
            page_count = 0
            title = slug
            filename = ""
            if idx_path.exists():
                idx = json.loads(idx_path.read_text())
                doc = idx.get("document", {})
                page_count = int(doc.get("page_count", 0))
                title = doc.get("title", slug)
                filename = doc.get("filename", "")
            has_gold = (self.gold / slug / "pages").is_dir()
            region_count = 0
            if has_gold:
                for rf in (self.gold / slug / "pages").glob("*.regions.json"):
                    rdata = json.loads(rf.read_text())
                    region_count += len(rdata if isinstance(rdata, list) else rdata.get("regions", []))
            out.append({
                "slug": slug, "title": title, "filename": filename,
                "page_count": page_count, "has_gold": has_gold, "region_count": region_count,
            })
        return out

    async def get_index(self, slug: str) -> dict[str, Any] | None:
        p = self.silver / slug / "index.json"
        return json.loads(p.read_text()) if p.exists() else None

    async def get_pages_meta(self, slug: str) -> dict[str, Any] | None:
        p = self.silver / slug / "pages.meta.json"
        return json.loads(p.read_text()) if p.exists() else None

    async def get_page_text(self, slug: str, page: int) -> str | None:
        for name in (f"{page}.md", f"{page}.raw.md"):
            p = self.silver / slug / "pages" / name
            if p.exists():
                return p.read_text()
        return None

    async def get_page_image_path(self, slug: str, page: int) -> Path | None:
        p = self.silver / slug / "pages" / f"{page}.png"
        return p if p.exists() else None

    async def get_regions(self, slug: str, page: int | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"slug": slug, "pages": {}}
        d = self.gold / slug / "pages"
        if not d.is_dir():
            return result
        for rf in sorted(d.glob("*.regions.json")):
            data = json.loads(rf.read_text())
            pg = int(data.get("page", rf.stem.rstrip(".regions")))
            if page is not None and pg != page:
                continue
            result["pages"][pg] = data.get("regions", data) if isinstance(data, dict) else data
        return result

    async def get_gold_map(self, slug: str) -> dict[str, Any] | None:
        index = await self.get_index(slug)
        regions = await self.get_regions(slug)
        pages_meta = await self.get_pages_meta(slug)
        if index is None:
            return None
        return {
            "slug": slug,
            "document": index.get("document", {}),
            "outline": index.get("outline", []),
            "pages": regions.get("pages", {}),
            "pages_meta": pages_meta or {},
        }

    async def get_crop_path(self, slug: str, rel_path: str) -> Path | None:
        cleaned = re.sub(r"\.\.+", ".", rel_path).lstrip("/")
        p = self.gold / slug / "pages" / cleaned
        return p if p.exists() else None

    async def get_raw_pdf_path(self, slug: str) -> Path | None:
        # bronze/ uses the original filename, not the slug — recover from
        # the silver index which carries `document.filename`.
        index = await self.get_index(slug)
        if not index:
            return None
        filename = (index.get("document") or {}).get("filename")
        if not filename:
            return None
        p = self.bronze / filename
        return p if p.is_file() else None

    async def stash_bronze(self, pdf_bytes: bytes, filename: str) -> Path:
        async with self._lock:
            target = self.bronze / filename
            async with aiofiles.open(target, "wb") as f:
                await f.write(pdf_bytes)
            return target

    async def write_silver_artifact(self, slug: str, name: str, payload: bytes | str) -> Path:
        target = self.silver / slug / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            async with aiofiles.open(target, "w") as f:
                await f.write(payload)
        else:
            async with aiofiles.open(target, "wb") as f:
                await f.write(payload)
        return target

    async def write_gold_region_file(self, slug: str, page: int, regions: list[dict[str, Any]]) -> Path:
        target = self.gold / slug / "pages" / f"{page}.regions.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "w") as f:
            await f.write(json.dumps({"page": page, "regions": list(regions)}, indent=2))
        return target

    async def write_embeddings(self, slug: str, payload: dict[str, Any]) -> Path:
        target = self.gold / slug / "embeddings.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "w") as f:
            await f.write(json.dumps(payload))
        return target

    async def get_embeddings(self, slug: str) -> dict[str, Any] | None:
        target = self.gold / slug / "embeddings.json"
        if not target.is_file():
            return None
        async with aiofiles.open(target) as f:
            return json.loads(await f.read())

    async def list_embeddings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.gold.is_dir():
            return out
        for d in sorted(self.gold.iterdir()):
            p = d / "embeddings.json"
            if not p.is_file():
                continue
            try:
                async with aiofiles.open(p) as f:
                    data = json.loads(await f.read())
                out.append({
                    "slug": d.name,
                    "embed_model": data.get("embed_model", ""),
                    "dim": int(data.get("dim", 0)),
                    "vector_count": len(data.get("vectors", [])),
                })
            except (ValueError, OSError):
                continue
        return out
