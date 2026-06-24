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
import os
from datetime import UTC
from pathlib import Path
from typing import Any

import aiofiles

from anchor.core.upload_safety import UnsafeUploadError, assert_within, safe_upload_name

#: Gold completeness marker filename, written atomically as the commit
#: point of a gold pass (keyed pipeline or harness finalize). Content is
#: `{"complete": bool, ...meta}` - an explicit `complete: false` is left
#: behind by `clear_gold_complete` so a crashed overwrite never resurrects
#: stale gold through the legacy fallback.
GOLD_COMPLETE_MARKER = ".complete.json"


def _with_bbox_alias(region: dict[str, Any]) -> dict[str, Any]:
    if "bbox" in region or "approximate_bbox" not in region:
        return region
    bbox = region.get("approximate_bbox")
    if not (
        isinstance(bbox, list)
        and len(bbox) == 4
        and all(isinstance(v, (int, float)) for v in bbox)
    ):
        return region
    return {**region, "bbox": [float(v) for v in bbox]}


def _normalise_regions(regions: Any) -> Any:
    if not isinstance(regions, list):
        return regions
    return [_with_bbox_alias(r) if isinstance(r, dict) else r for r in regions]


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
                idx = json.loads(idx_path.read_text(encoding="utf-8"))
                doc = idx.get("document", {})
                page_count = int(doc.get("page_count", 0))
                title = doc.get("title", slug)
                filename = doc.get("filename", "")
            has_gold = self._gold_complete(slug)
            region_count = 0
            if has_gold:
                for rf in (self.gold / slug / "pages").glob("*.regions.json"):
                    rdata = json.loads(rf.read_text(encoding="utf-8"))
                    region_count += len(rdata if isinstance(rdata, list) else rdata.get("regions", []))
            entry = {
                "slug": slug, "title": title, "filename": filename,
                "page_count": page_count, "has_gold": has_gold, "region_count": region_count,
            }
            # Surface ingest outcome. A report with `status: failed` is a
            # crash-stashed bronze with no silver/gold — make it visible as
            # failed (with the failing stage + error) instead of an empty
            # ok-looking row. Missing report or any non-failed status reads ok.
            report = self._read_ingest_report(slug)
            if report and report.get("status") == "failed":
                entry["status"] = "failed"
                entry["stage"] = report.get("stage", "unknown")
                entry["error"] = report.get("error", "")
                if report.get("bronze_path"):
                    entry["bronze_path"] = report["bronze_path"]
                if not filename and report.get("filename"):
                    entry["filename"] = report["filename"]
            else:
                entry["status"] = "ok"
            marker = self._read_gold_marker(slug)
            if has_gold and marker:
                if marker.get("mode"):
                    entry["gold_mode"] = marker["mode"]
                model = marker.get("declared_model") or marker.get("model")
                if model:
                    entry["gold_model"] = model
            out.append(entry)
        return out

    # ── Gold completeness ────────────────────────────────────────────────
    #
    # `has_gold` used to be `(gold/<slug>/pages).is_dir()`, which reported
    # a crash-interrupted gold pass (or a multi-turn harness session) as a
    # complete document. Completeness is now an explicit marker committed
    # atomically at the end of a gold pass. Legacy docs ingested before the
    # marker existed fall back to the ingest report: a successful keyed run
    # wrote it as its very last step, so its presence with regions implies
    # the gold loop finished.

    def _read_ingest_report(self, slug: str) -> dict[str, Any] | None:
        p = self.silver / slug / "ingest-report.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _read_gold_marker(self, slug: str) -> dict[str, Any] | None:
        p = self.gold / slug / GOLD_COMPLETE_MARKER
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _gold_complete(self, slug: str) -> bool:
        marker = self._read_gold_marker(slug)
        if marker is not None:
            return bool(marker.get("complete"))
        # Legacy fallback (pre-marker docs): the keyed pipeline wrote
        # ingest-report.json after the whole gold loop, so a success report
        # with regions means gold completed. A crashed run has no report.
        report_path = self.silver / slug / "ingest-report.json"
        if not report_path.is_file():
            return False
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return False
        return (
            isinstance(report, dict)
            and report.get("status") == "success"
            and int(report.get("region_count") or 0) > 0
        )

    async def has_gold(self, slug: str) -> bool:
        return self._gold_complete(slug)

    async def mark_gold_complete(self, slug: str, meta: dict[str, Any]) -> Path:
        target = self.gold / slug / GOLD_COMPLETE_MARKER
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"complete": True, **meta}, indent=2)
        # Atomic commit: write a sibling temp file, then rename over the
        # marker. A crash leaves either the old marker or the new one.
        tmp = target.with_name(GOLD_COMPLETE_MARKER + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(payload)
        os.replace(tmp, target)
        return target

    async def clear_gold_complete(self, slug: str) -> None:
        target = self.gold / slug / GOLD_COMPLETE_MARKER
        if not target.parent.is_dir():
            return
        payload = json.dumps({"complete": False})
        tmp = target.with_name(GOLD_COMPLETE_MARKER + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(payload)
        os.replace(tmp, target)

    async def get_index(self, slug: str) -> dict[str, Any] | None:
        p = self.silver / slug / "index.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    async def get_pages_meta(self, slug: str) -> dict[str, Any] | None:
        p = self.silver / slug / "pages.meta.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    async def get_page_text(self, slug: str, page: int) -> str | None:
        for name in (f"{page}.md", f"{page}.raw.md"):
            p = self.silver / slug / "pages" / name
            if p.exists():
                return p.read_text(encoding="utf-8")
        return None

    async def get_page_image_path(self, slug: str, page: int) -> Path | None:
        p = self.silver / slug / "pages" / f"{page}.png"
        return p if p.exists() else None

    async def get_page_candidates(self, slug: str, page: int) -> list[dict[str, Any]] | None:
        p = self.silver / slug / "pages" / f"{page}.candidates.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, list) else None

    async def get_regions(self, slug: str, page: int | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"slug": slug, "pages": {}}
        d = self.gold / slug / "pages"
        if not d.is_dir():
            return result
        for rf in sorted(d.glob("*.regions.json")):
            data = json.loads(rf.read_text(encoding="utf-8"))
            pg = int(data.get("page", rf.stem.rstrip(".regions")))
            if page is not None and pg != page:
                continue
            regions = data.get("regions", data) if isinstance(data, dict) else data
            result["pages"][pg] = _normalise_regions(regions)
        return result

    async def get_gold_map(self, slug: str) -> dict[str, Any] | None:
        # Keyed on actual gold completeness: silver-only documents and
        # crash-interrupted (partial) gold passes have no gold map.
        if not self._gold_complete(slug):
            return None
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
        # ``rel_path`` arrives from the agent (e.g. region.crops.png →
        # ``"3/r1.png"``). It must stay inside this document's gold pages
        # directory. The previous implementation used an ad-hoc
        # ``re.sub(r"\.\.+", ".", ...)`` replacement which fails closed for
        # ``..`` but does nothing about backslashes, absolute paths, or
        # symlink escapes. Resolve the candidate and verify containment.
        base = self.gold / slug / "pages"
        candidate = (base / rel_path)
        try:
            resolved = assert_within(candidate, base)
        except UnsafeUploadError:
            return None
        return resolved if resolved.exists() else None

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
        # Defence-in-depth: re-validate the filename here so direct
        # callers (CLI ``anchor ingest``, tests, future agents) get the
        # same protection the HTTP upload route applies. ``safe_upload_name``
        # rejects path components and a non-pdf extension; ``assert_within``
        # rejects any residual escape via the resolved path.
        clean = safe_upload_name(filename, allowed_extensions={".pdf"})
        async with self._lock:
            target = self.bronze / clean
            assert_within(target, self.bronze)
            async with aiofiles.open(target, "wb") as f:
                await f.write(pdf_bytes)
            return target

    async def write_silver_artifact(self, slug: str, name: str, payload: bytes | str) -> Path:
        target = self.silver / slug / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            async with aiofiles.open(target, "w", encoding="utf-8") as f:
                await f.write(payload)
        else:
            async with aiofiles.open(target, "wb") as f:
                await f.write(payload)
        return target

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
        # Reuse the silver writer so the record lands in the same
        # ingest-report.json slot the success path uses; this also creates
        # silver/<slug>/ so the orphaned doc surfaces in list_documents.
        return await self.write_silver_artifact(
            slug, "ingest-report.json", json.dumps(record, indent=2),
        )

    async def write_gold_region_file(self, slug: str, page: int, regions: list[dict[str, Any]]) -> Path:
        target = self.gold / slug / "pages" / f"{page}.regions.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        normalised = _normalise_regions(regions)
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(json.dumps({"page": page, "regions": normalised}, indent=2))
        return target

    async def write_embeddings(self, slug: str, payload: dict[str, Any]) -> Path:
        target = self.gold / slug / "embeddings.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload))
        return target

    async def get_embeddings(self, slug: str) -> dict[str, Any] | None:
        target = self.gold / slug / "embeddings.json"
        if not target.is_file():
            return None
        async with aiofiles.open(target, encoding="utf-8") as f:
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
                async with aiofiles.open(p, encoding="utf-8") as f:
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
