"""In-memory MemoryDocStore — used by tests and ephemeral mode."""
from __future__ import annotations

import asyncio
from datetime import UTC
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_pdfs.infra._region_normalize import _normalise_regions


def _derived_page(region: dict[str, Any]) -> int | None:
    """Resolve the gold page a derived region belongs on."""
    sref = region.get("source_ref")
    if isinstance(sref, dict) and isinstance(sref.get("page"), int):
        return sref["page"]
    if isinstance(region.get("page"), int):
        return region["page"]
    return None


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
        self._embeddings: dict[str, dict[str, Any]] = {}
        self._candidates: dict[tuple[str, int], list[dict[str, Any]]] = {}
        # Gold completeness markers: slug -> marker dict ({"complete": bool, ...}).
        self._gold_markers: dict[str, dict[str, Any]] = {}
        # Failed-ingest records: slug -> failure record (mirrors the fs
        # ingest-report.json with status == "failed").
        self._failures: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def list_documents(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for slug, doc in self._docs.items():
            seen.add(slug)
            entry = dict(doc)
            failure = self._failures.get(slug)
            if failure:
                entry["status"] = "failed"
                entry["stage"] = failure.get("stage", "unknown")
                entry["error"] = failure.get("error", "")
                if failure.get("bronze_path"):
                    entry["bronze_path"] = failure["bronze_path"]
            else:
                entry["status"] = "ok"
            out.append(entry)
        # Failures with no seeded doc row (crash-early ingests) still surface.
        for slug, failure in self._failures.items():
            if slug in seen:
                continue
            entry: dict[str, Any] = {
                "slug": slug,
                "title": slug,
                "filename": failure.get("filename", ""),
                "page_count": 0,
                "has_gold": False,
                "region_count": 0,
                "status": "failed",
                "stage": failure.get("stage", "unknown"),
                "error": failure.get("error", ""),
            }
            if failure.get("bronze_path"):
                entry["bronze_path"] = failure["bronze_path"]
            out.append(entry)
        return out

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
            pages[p] = _normalise_regions(regions)
        return {"slug": slug, "pages": pages}

    async def get_gold_map(self, slug: str) -> dict[str, Any] | None:
        explicit = self._gold_maps.get(slug)
        if explicit is not None:
            return explicit
        # Keyed on completeness, mirroring FsDocStore: silver-only or
        # partially golded documents have no gold map.
        if not await self.has_gold(slug):
            return None
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

    async def has_gold(self, slug: str) -> bool:
        if slug in self._gold_maps:
            # Explicitly seeded gold maps count as complete (test helper).
            return True
        marker = self._gold_markers.get(slug)
        return bool(marker and marker.get("complete"))

    async def mark_gold_complete(self, slug: str, meta: dict[str, Any]) -> Path:
        async with self._lock:
            self._gold_markers[slug] = {"complete": True, **meta}
        return Path(f"memory://gold/{slug}/.complete.json")

    async def clear_gold_complete(self, slug: str) -> None:
        async with self._lock:
            self._gold_markers[slug] = {"complete": False}

    async def get_page_candidates(self, slug: str, page: int) -> list[dict[str, Any]] | None:
        candidates = self._candidates.get((slug, page))
        return [dict(c) for c in candidates] if candidates is not None else None

    async def get_crop_path(self, slug: str, rel_path: str) -> Path | None:
        return None

    async def get_raw_pdf_path(self, slug: str) -> Path | None:
        idx = self._indexes.get(slug)
        filename = ((idx or {}).get("document") or {}).get("filename")
        if filename and filename in self._bronze:
            # Memory store has no real filesystem path; surface a `memory://`
            # URI so callers can detect this case and fall back to a
            # base64 transport.
            return Path(f"memory://bronze/{filename}")
        return None

    async def stash_bronze(self, pdf_bytes: bytes, filename: str) -> Path:
        async with self._lock:
            self._bronze[filename] = pdf_bytes
        return Path(f"memory://bronze/{filename}")

    async def write_silver_artifact(self, slug: str, name: str, payload: bytes | str) -> Path:
        # In-memory store dispatches to specific keys based on filename convention.
        import json
        import re
        if name == "index.json":
            self._indexes[slug] = json.loads(payload) if isinstance(payload, str) else json.loads(payload.decode())
            # A successful re-ingest clears any prior failure record so the
            # doc flips back to status == "ok".
            self._failures.pop(slug, None)
            idx = self._indexes[slug]
            doc = idx.get("document", {}) if isinstance(idx, dict) else {}
            self._docs[slug] = {
                "slug": slug,
                "title": doc.get("title", slug),
                "filename": doc.get("filename", ""),
                "page_count": int(doc.get("page_count", 0)),
                "has_gold": False,
                "region_count": 0,
            }
        elif name == "pages.meta.json":
            self._pages_meta[slug] = json.loads(payload) if isinstance(payload, str) else json.loads(payload.decode())
        elif (m := re.fullmatch(r"pages/(\d+)\.candidates\.json", name)):
            data = json.loads(payload) if isinstance(payload, str) else json.loads(payload.decode())
            self._candidates[(slug, int(m.group(1)))] = data
        elif (m := re.fullmatch(r"pages/(\d+)\.md", name)) and isinstance(payload, str):
            self._page_text[(slug, int(m.group(1)))] = payload
        elif (m := re.fullmatch(r"pages/(\d+)\.raw\.md", name)) and isinstance(payload, str):
            self._page_text.setdefault((slug, int(m.group(1))), payload)
        return Path(f"memory://silver/{slug}/{name}")

    async def write_ingest_failure(
        self,
        slug: str,
        *,
        filename: str,
        stage: str,
        error: str,
        bronze_path: str | None,
        failed_at: float | None = None,
    ) -> Path:
        record: dict[str, Any] = {
            "status": "failed",
            "stage": stage,
            "error": error,
            "filename": filename,
            "bronze_path": bronze_path,
        }
        if failed_at is not None:
            from datetime import datetime
            record["failed_at"] = datetime.fromtimestamp(
                failed_at, tz=UTC
            ).isoformat()
        async with self._lock:
            self._failures[slug] = record
        return Path(f"memory://silver/{slug}/ingest-report.json")

    async def write_gold_region_file(self, slug: str, page: int, regions: list[dict[str, Any]]) -> Path:
        async with self._lock:
            self._regions[(slug, page)] = _normalise_regions(regions)
        return Path(f"memory://gold/{slug}/{page}.regions.json")

    async def add_derived_region(self, slug: str, region: dict[str, Any]) -> Path:
        page = _derived_page(region)
        if page is None:
            raise ValueError(
                "add_derived_region: cannot resolve page from region.source_ref.page "
                "or region.page"
            )
        async with self._lock:
            existing = list(self._regions.get((slug, page), []))
            rid = region.get("id")
            kept = [r for r in existing if r.get("id") != rid] if rid else existing
            kept.append(region)
            self._regions[(slug, page)] = _normalise_regions(kept)
        return Path(f"memory://gold/{slug}/{page}.regions.json")

    async def write_embeddings(self, slug: str, payload: dict[str, Any]) -> Path:
        async with self._lock:
            self._embeddings[slug] = dict(payload)
        return Path(f"memory://gold/{slug}/embeddings.json")

    async def get_embeddings(self, slug: str) -> dict[str, Any] | None:
        payload = self._embeddings.get(slug)
        return dict(payload) if payload is not None else None

    async def list_embeddings(self) -> list[dict[str, Any]]:
        return [
            {
                "slug": slug,
                "embed_model": payload.get("embed_model", ""),
                "dim": int(payload.get("dim", 0)),
                "vector_count": len(payload.get("vectors", [])),
            }
            for slug, payload in sorted(self._embeddings.items())
        ]

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
