"""Filesystem-backed DocStore.

Owns document-addressed originals and slug-addressed extraction artifacts.
Flat legacy originals remain readable only with unambiguous ownership:

    data_dir/
        bronze/<slug>/<sha256>.pdf
        bronze/<slug>/original.json
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
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from copy import copy
from datetime import UTC
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import uuid4

import aiofiles

from anchor.core.ids import validate_workspace_slug
from anchor.core.upload_safety import UnsafeUploadError, assert_within, safe_upload_name
from anchor.extensions.anchor_pdfs.core.generation import polished_membership
from anchor.extensions.anchor_pdfs.core.ingest.validation import require_unique_region_ids
from anchor.extensions.anchor_pdfs.core.ports.doc_store import IngestLockHeld
from anchor.extensions.anchor_pdfs.core.silver import project_index
from anchor.extensions.anchor_pdfs.core.source_identity import SourceIdentityError, original_source
from anchor.extensions.anchor_pdfs.infra._generation import document_view
from anchor.extensions.anchor_pdfs.infra._region_normalize import _normalise_regions

#: How long a stale ingest lock file may sit before another writer reclaims it.
#: A lock is freed in a ``finally`` on normal exit and on a handled crash, but a
#: hard kill (SIGKILL, power loss) can orphan it. Rather than wedge every future
#: ingest of that slug forever, a lock older than this is treated as abandoned
#: and broken. Sized well above the longest realistic gold pass.
INGEST_LOCK_STALE_SECONDS = 6 * 60 * 60

#: Gold completeness marker filename, written atomically as the commit
#: point of a gold pass (keyed pipeline or harness finalize). Content is
#: `{"complete": bool, ...meta}` - an explicit `complete: false` is left
#: behind by `clear_gold_complete` so a crashed overwrite never resurrects
#: stale gold through the legacy fallback.
GOLD_COMPLETE_MARKER = ".complete.json"


def _derived_page(region: dict[str, Any]) -> int | None:
    """Resolve the gold page a derived region belongs on."""
    sref = region.get("source_ref")
    if isinstance(sref, dict) and isinstance(sref.get("page"), int):
        return sref["page"]
    if isinstance(region.get("page"), int):
        return region["page"]
    return None


class FsDocStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.bronze = self.data_dir / "bronze"
        self.silver = self.data_dir / "silver"
        self.gold = self.data_dir / "gold"
        # Live ingest-activity records (issue #51): one small JSON per slug the
        # pipeline updates as it advances, so an in-flight ingest is visible
        # across process boundaries and survives a restart.
        self.ingest_status = self.data_dir / "ingest_status"
        # Per-slug ingest lock files (issue #175). A single-writer guard so two
        # concurrent `anchor ingest --force` on one slug cannot interleave and
        # desync the gold-complete marker from the real artifacts.
        self.ingest_locks = self.data_dir / "ingest_locks"
        for p in (self.bronze, self.silver, self.gold, self.ingest_locks):
            p.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._pinned: dict[str, str | None] = {}
        self._published: dict[str, dict[str, Any]] = {}

    def _current_manifest(self, slug: str) -> dict[str, Any] | None:
        path = self._base_dir(self.silver, slug) / ".current.json"
        path = assert_within(path, self.silver)
        if not path.exists():
            return None
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            token = manifest["generation"]
            self._validate_generation(token)
            if manifest.get("version") != 1 or not isinstance(manifest.get("pages"), list) or not isinstance(manifest.get("source"), dict):
                raise ValueError
            return manifest
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SourceIdentityError("document generation metadata is invalid") from exc

    def _current_generation(self, slug: str) -> str | None:
        manifest = self._current_manifest(slug)
        return manifest["generation"] if manifest is not None else None

    @staticmethod
    def _validate_generation(token: str) -> None:
        if not isinstance(token, str) or len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
            raise SourceIdentityError("invalid document generation")

    def snapshot(self, slug: str) -> FsDocStore:
        if slug in self._pinned:
            return self
        manifest = self._current_manifest(slug)
        view = copy(self)
        view._pinned = {**self._pinned, slug: manifest["generation"] if manifest is not None else None}
        view._published = {**self._published}
        if manifest is not None:
            view._published[slug] = manifest
        return view

    def replacement(self, slug: str, generation: str) -> FsDocStore:
        self._validate_generation(generation)
        view = copy(self)
        view._pinned = {**self._pinned, slug: generation}
        view._published = {s: m for s, m in self._published.items() if s != slug}
        if not (view._doc_dir(self.silver, slug) / ".replacement.json").is_file():
            raise SourceIdentityError("replacement generation is unavailable")
        return view

    async def begin_replacement(self, slug: str, pages: list[int]) -> str:
        old = self.snapshot(slug)
        token = uuid4().hex
        view = copy(self)
        view._pinned = {**self._pinned, slug: token}
        base = view._doc_dir(self.silver, slug)
        base.mkdir(parents=True, exist_ok=False)
        view._doc_dir(self.gold, slug).mkdir(parents=True, exist_ok=False)
        (base / ".replacement.json").write_text(json.dumps({
            "parent": old._pinned[slug],
        }), encoding="utf-8")
        return token

    async def publish_replacement(self, slug: str, generation: str, pages: list[int]) -> None:
        view = self.replacement(slug, generation)
        index = await view.get_index(slug, include_content=True)
        if index is None or await view.get_raw_pdf_path(slug) is None:
            raise SourceIdentityError("replacement is missing its source index or original")
        membership = sorted(set(pages))
        if any(not isinstance(page, int) or page < 1 for page in membership):
            raise SourceIdentityError("replacement page membership is invalid")
        metadata = await view.get_pages_meta(slug)
        report = view._read_ingest_report(slug)
        if (metadata is None or set(metadata.get("pages", {})) != {str(p) for p in membership}
                or index["document"].get("page_count") != len(membership)
                or not report or report.get("status") != "success"):
            raise SourceIdentityError("replacement is incomplete or has inconsistent page membership")
        for page in membership:
            base = view._doc_dir(self.silver, slug) / "pages"
            if any(not (base / f"{page}{suffix}").is_file() for suffix in (".raw.md", ".png", ".candidates.json")):
                raise SourceIdentityError("replacement silver page is incomplete")
        polished = polished_membership(report)
        if not set(polished).issubset(membership) or any(
            not (view._doc_dir(self.silver, slug) / "pages" / f"{page}.md").is_file() for page in polished
        ):
            raise SourceIdentityError("replacement polished page is incomplete or outside current membership")
        gold = (await view.get_regions(slug))["pages"]
        if not set(gold).issubset(membership):
            raise SourceIdentityError("replacement gold is outside current page membership")
        for page, regions in gold.items():
            require_unique_region_ids(regions, page=page)
        identities = {(page, r["id"]) for page, regions in gold.items() for r in regions}
        embeddings = await view.get_embeddings(slug)
        if embeddings and any((v["page"], v["region_id"]) not in identities for v in embeddings.get("vectors", [])):
            raise SourceIdentityError("replacement embeddings contain obsolete regions")
        base = view._doc_dir(self.silver, slug)
        parent = json.loads((base / ".replacement.json").read_text(encoding="utf-8"))["parent"]
        manifest = {"version": 1, "generation": generation, "source": index["document"]["source"],
                    "pages": membership, "gold": {str(p): [r["id"] for r in rs] for p, rs in gold.items()},
                    "embedded": embeddings is not None, "polished_pages": polished}
        index["document"]["generation"] = {"id": generation, "pages": membership}
        await view.write_silver_artifact(slug, "index.json", json.dumps(index))
        # The only publication point switches both derived trees and source.
        # Retained old trees keep previously returned file paths readable.
        async with self.ingest_lock(slug):
            current = self._current_generation(slug)
            if current == generation:
                return
            if current != parent:
                raise SourceIdentityError("replacement was superseded; begin a fresh ingest")
            target = self._base_dir(self.silver, slug) / ".current.json"
            tmp = target.with_name(f"{uuid4().hex}.tmp")
            try:
                tmp.write_text(json.dumps(manifest), encoding="utf-8")
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)

    # ── Per-slug ingest lock (issue #175) ────────────────────────────────
    #
    # Cross-process single-writer guard for one slug's gold pass. Backed by an
    # exclusively-created lock file under ``ingest_locks/`` (O_CREAT|O_EXCL is
    # atomic on POSIX and Windows). An in-process ``asyncio.Lock`` shares the
    # same slug-keyed file across coroutines so two tasks in one event loop also
    # serialize. A lock orphaned by a hard kill is reclaimed once it goes stale.

    def _ingest_lock_path(self, slug: str) -> Path:
        if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
            raise UnsafeUploadError(f"unsafe ingest-lock slug: {slug!r}")
        target = self.ingest_locks / f"{slug}.lock"
        assert_within(target, self.ingest_locks)
        return target

    def _base_dir(self, root: Path, slug: str) -> Path:
        """``root/<slug>`` for a caller-supplied slug, refusing traversal.

        Slugs reach the store from HTTP/MCP/CLI arguments, so a read path built
        from one is a path-injection sink. Reject path components and traversal
        tokens, then assert the resolved directory stays under ``root`` — the
        same guard the ingest lock and bronze stash apply.
        """
        if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
            raise UnsafeUploadError(f"unsafe document slug: {slug!r}")
        # Inline normalise-then-prefix-check (not delegated) so the containment
        # barrier sits in the same function that builds the path.
        base = os.path.realpath(os.fspath(root))
        candidate = os.path.normpath(os.path.join(base, slug))
        if not candidate.startswith(base + os.sep):
            raise UnsafeUploadError(f"document slug {slug!r} escapes {root!s}")
        return Path(candidate)

    def _doc_dir(self, root: Path, slug: str) -> Path:
        base = self._base_dir(root, slug)
        token = self._pinned[slug] if slug in self._pinned else self._current_generation(slug)
        if token is not None:
            base = assert_within(base / "generations" / token, base)
        # A document directory can itself be a link. Check the final selected
        # path against the storage layer, not only against that document link.
        layer = os.path.realpath(os.fspath(root))
        candidate = os.path.realpath(os.fspath(base))
        if not candidate.startswith(layer + os.sep):
            raise UnsafeUploadError("document directory escapes its storage layer")
        return Path(candidate)

    def _try_create_lock(self, path: Path) -> bool:
        """Atomically create the lock file. True on success, False if held.

        Breaks a stale lock (older than ``INGEST_LOCK_STALE_SECONDS``) left by a
        hard-killed writer, then retries once."""
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                return False
            if age < INGEST_LOCK_STALE_SECONDS:
                return False
            # Stale lock from an orphaned run: reclaim it. unlink + retry; if a
            # racing writer grabbed it first, the retry simply fails and we wait.
            try:
                path.unlink()
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError:
                return False
        try:
            os.write(fd, f"pid={os.getpid()} acquired_at={time.time()}\n".encode())
        finally:
            os.close(fd)
        return True

    @asynccontextmanager
    async def ingest_lock(
        self, slug: str, *, wait: bool = True, timeout: float | None = None,
    ):
        path = self._ingest_lock_path(slug)  # validate the slug up front
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        poll = 0.05
        while True:
            if self._try_create_lock(path):
                break
            if not wait:
                raise IngestLockHeld(
                    f"ingest lock for {slug!r} is held by another writer; "
                    "another ingest is running for this slug"
                )
            if deadline is not None and time.monotonic() >= deadline:
                raise IngestLockHeld(
                    f"timed out after {timeout}s waiting for the ingest lock on "
                    f"{slug!r}; another ingest is still running for this slug"
                )
            await asyncio.sleep(poll)
            poll = min(poll * 2, 1.0)
        try:
            yield
        finally:
            try:
                path.unlink()
            except FileNotFoundError:
                # Lock already removed (for example by a racing cleanup); ignore.
                pass
            except OSError:
                raise

    async def list_documents(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.silver.is_dir():
            return out
        for d in sorted(self.silver.iterdir()):
            if not d.is_dir():
                continue
            slug = d.name
            try:
                reader = self.snapshot(slug)
                idx = await reader.get_index(slug)
            except UnsafeUploadError:
                continue
            page_count = 0
            title = slug
            filename = ""
            if idx is not None:
                doc = idx.get("document", {})
                page_count = int(doc.get("page_count", 0))
                title = doc.get("title", slug)
                filename = doc.get("filename", "")
            has_gold = reader._gold_complete(slug)
            # Count the regions actually on disk (not the marker's stale figure)
            # so a marker desynced by a concurrent --force (issue #175) still
            # reports the true region_count once the cross-check vouches for gold.
            region_count = reader._count_gold_regions(slug) if has_gold else 0
            entry = {
                "slug": slug, "title": title, "filename": filename,
                "page_count": page_count, "has_gold": has_gold, "region_count": region_count,
            }
            # Surface ingest outcome. A report with `status: failed` is a
            # crash-stashed bronze with no silver/gold — make it visible as
            # failed (with the failing stage + error) instead of an empty
            # ok-looking row. A report with `status: empty_gold` is a gold pass
            # that finished but produced 0 regions on a non-empty document
            # (issue #188) — surface it as a distinct, actionable non-ok state
            # so an agent retries instead of trusting a silent ok. Missing
            # report or `status: success` reads ok.
            report = reader._read_ingest_report(slug)
            report_status = report.get("status") if report else None
            if report_status == "failed":
                entry["status"] = "failed"
                entry["stage"] = report.get("stage", "unknown")
                entry["error"] = report.get("error", "")
                if report.get("bronze_path"):
                    entry["bronze_path"] = report["bronze_path"]
                if not filename and report.get("filename"):
                    entry["filename"] = report["filename"]
            elif report_status == "empty_gold":
                entry["status"] = "empty_gold"
                entry["reason"] = report.get("reason", "gold extraction produced 0 regions")
            else:
                entry["status"] = "ok"
            marker = reader._read_gold_marker(slug)
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
        p = self._doc_dir(self.silver, slug) / "ingest-report.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _read_gold_marker(self, slug: str) -> dict[str, Any] | None:
        p = self._doc_dir(self.gold, slug) / GOLD_COMPLETE_MARKER
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _count_gold_regions(self, slug: str) -> int:
        """Count regions actually present on disk in gold/<slug>/pages/."""
        total = 0
        for rf in (self._doc_dir(self.gold, slug) / "pages").glob("*.regions.json"):
            try:
                rdata = json.loads(rf.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            total += len(rdata if isinstance(rdata, list) else rdata.get("regions", []))
        return total

    def _gold_artifacts_consistent(self, slug: str) -> bool:
        """Cross-check: are real, queryable gold artifacts present for ``slug``?

        Issue #175: a killed/concurrent ``--force`` ingest can reset
        ``.complete.json`` to the start-of-run stub ``{"complete": false}`` and
        exit before finalizing, even though every gold artifact was written.
        Trusting only the stub then reports a fully-golded, queryable doc as
        ``has_gold: false``, so a consumer needlessly re-ingests (re-billing the
        vision model). When the marker is missing or not-complete we therefore
        cross-check the durable artifacts instead of trusting the stub.

        Conservative on purpose: we require BOTH the finished ingest-report
        (``gold_complete: true`` with a positive ``region_count``) AND that the
        same number of regions are actually on disk. A genuinely-incomplete doc
        (no report, partial regions, empty_gold) fails the check and stays
        ``has_gold: false``."""
        report = self._read_ingest_report(slug)
        if not report:
            return False
        if report.get("status") != "success":
            return False
        # An explicit `gold_complete: false` is the empty_gold outcome
        # (issue #188): a finished pass that produced no usable gold. Never
        # vouch for it. A legacy pre-#188 report has no `gold_complete` key at
        # all; for those we fall back to status + a positive region_count.
        if report.get("gold_complete") is False:
            return False
        reported = int(report.get("region_count") or 0)
        if reported <= 0:
            return False
        # The report claims N regions; require at least N actually present on
        # disk so a report left over from a different (overwritten) run cannot
        # vouch for gold that a crash truncated.
        return self._count_gold_regions(slug) >= reported

    def _gold_complete(self, slug: str) -> bool:
        marker = self._read_gold_marker(slug)
        if marker is not None and marker.get("complete"):
            return True
        # Marker missing, stub, or explicitly not-complete. Before trusting it,
        # cross-check the durable gold artifacts (issue #175): a concurrent /
        # killed --force ingest can reset the marker to the start-of-run stub
        # while leaving a complete, queryable gold layer behind. This also
        # covers legacy pre-marker docs whose only completeness signal is the
        # ingest-report the keyed pipeline wrote as its last step.
        return self._gold_artifacts_consistent(slug)

    @document_view
    async def has_gold(self, slug: str) -> bool:
        return self._gold_complete(slug)

    async def mark_gold_complete(self, slug: str, meta: dict[str, Any]) -> Path:
        target = self._doc_dir(self.gold, slug) / GOLD_COMPLETE_MARKER
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
        target = self._doc_dir(self.gold, slug) / GOLD_COMPLETE_MARKER
        if not target.parent.is_dir():
            return
        payload = json.dumps({"complete": False})
        tmp = target.with_name(GOLD_COMPLETE_MARKER + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(payload)
        os.replace(tmp, target)

    @document_view
    async def get_index(self, slug: str, *, include_content: bool = False) -> dict[str, Any] | None:
        p = self._doc_dir(self.silver, slug) / "index.json"
        if self._pinned.get(slug) is not None and not p.is_file():
            raise SourceIdentityError("document generation index is unavailable")
        index = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        manifest = self._published.get(slug)
        if manifest is not None:
            document = index.get("document", {}) if isinstance(index, dict) else {}
            if document.get("source") != manifest["source"] or document.get("generation") != {"id": manifest["generation"], "pages": manifest["pages"]}:
                raise SourceIdentityError("document generation and source metadata disagree")
        return project_index(index, include_content=include_content)

    @document_view
    async def get_pages_meta(self, slug: str) -> dict[str, Any] | None:
        p = self._doc_dir(self.silver, slug) / "pages.meta.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    @document_view
    async def get_page_text(self, slug: str, page: int) -> str | None:
        pages = self._doc_dir(self.silver, slug) / "pages"
        names = (f"{int(page)}.md", f"{int(page)}.raw.md")
        if self._pinned.get(slug) is not None:
            proof = self._published.get(slug)
            if proof is None:
                report = self._read_ingest_report(slug) or {}
                proof = report if report.get("status") == "success" else {}
            try:
                polished = polished_membership(proof)
            except ValueError:
                polished = []
            if page not in polished:
                names = (f"{int(page)}.raw.md",)
        for name in names:
            p = pages / name
            if p.exists():
                return p.read_text(encoding="utf-8")
        return None

    @document_view
    async def get_page_image_path(
        self, slug: str, page: int, dpi: int | None = None
    ) -> Path | None:
        name = f"{int(page)}.png" if dpi is None else f"{int(page)}@{int(dpi)}dpi.png"
        p = self._doc_dir(self.silver, slug) / "pages" / name
        return p if p.exists() else None

    @document_view
    async def get_page_candidates(self, slug: str, page: int) -> list[dict[str, Any]] | None:
        p = self._doc_dir(self.silver, slug) / "pages" / f"{int(page)}.candidates.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, list) else None

    @document_view
    async def get_regions(self, slug: str, page: int | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"slug": slug, "pages": {}}
        d = self._doc_dir(self.gold, slug) / "pages"
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

    @document_view
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

    @document_view
    async def get_crop_path(self, slug: str, rel_path: str) -> Path | None:
        # ``rel_path`` arrives from the agent (e.g. region.crops.png →
        # ``"3/r1.png"``). It must stay inside this document's gold pages
        # directory. The previous implementation used an ad-hoc
        # ``re.sub(r"\.\.+", ".", ...)`` replacement which fails closed for
        # ``..`` but does nothing about backslashes, absolute paths, or
        # symlink escapes. Resolve the candidate and verify containment.
        base = self._doc_dir(self.gold, slug) / "pages"
        candidate = (base / rel_path)
        try:
            resolved = assert_within(candidate, base)
        except UnsafeUploadError:
            return None
        return resolved if resolved.exists() else None

    @document_view
    async def write_crop(self, slug: str, rel_path: str, data: bytes) -> Path:
        # Both components arrive from CLI/MCP/HTTP arguments, so the write
        # path is a path-injection sink. Inline normalise-then-prefix-check
        # (not delegated) so the containment barrier sits in the same function
        # that builds the path - the same guard `_doc_dir` applies on reads.
        if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
            raise UnsafeUploadError(f"unsafe document slug: {slug!r}")
        base = os.path.realpath(os.fspath(self.gold))
        doc_base = os.path.realpath(os.path.join(os.fspath(self._doc_dir(self.gold, slug)), "pages"))
        candidate = os.path.realpath(os.path.join(os.fspath(self._doc_dir(self.gold, slug)), "pages", rel_path))
        if not candidate.startswith(base + os.sep):
            raise UnsafeUploadError(f"crop rel_path {rel_path!r} escapes the gold dir")
        if not candidate.startswith(doc_base + os.sep):
            raise UnsafeUploadError(f"crop rel_path {rel_path!r} escapes the gold pages dir")
        target = Path(candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "wb") as f:
            await f.write(data)
        return target

    @document_view
    async def get_raw_pdf_path(self, slug: str, *, page: int | None = None) -> Path | None:
        base = self._original_dir(slug)
        try:
            index = await self.get_index(slug)
            if index is None and (self._doc_dir(self.silver, slug) / "index.json").exists():
                raise ValueError
            if index is not None and (not isinstance(index, dict) or not isinstance(index.get("document"), dict)):
                raise ValueError
            document = index["document"] if index is not None else {}
            membership = document.get("generation", {}).get("pages")
            if page is not None and membership is not None and page not in membership:
                return None
        except (OSError, ValueError, AttributeError) as exc:
            raise SourceIdentityError("document source metadata is inconsistent") from exc
        if "source" in document:
            return self._verified_original(base, slug, document["source"])
        if index is None and (base / "original.json").exists():
            return self._verified_original(base, slug, self._original_record(base))
        if index is None:
            return None
        return self._legacy_original(slug, document)

    def _legacy_original(self, slug: str, document: dict[str, Any]) -> Path | None:
        """Read only: filename lookup requires a proven legacy ownership set."""
        try:
            filename = safe_upload_name(document.get("filename"), allowed_extensions={".pdf"})
            path = assert_within(self.bronze / filename, self.bronze)
            if not path.is_file():
                return None
            owners = []
            for directory in self.silver.iterdir():
                index_path = self.snapshot(directory.name)._doc_dir(self.silver, directory.name) / "index.json"
                if not index_path.is_file():
                    continue
                assert_within(index_path, self.silver)
                candidate = json.loads(index_path.read_text(encoding="utf-8"))["document"]
                # Keep competing filename claims even after re-ingestion.
                # Dropping a modernized owner would make an old conflict look
                # unambiguous without establishing whose bytes survived.
                name = safe_upload_name(candidate.get("filename"), allowed_extensions={".pdf"})
                other = assert_within(self.bronze / name, self.bronze)
                if os.path.normcase(str(other)) == os.path.normcase(str(path)):
                    owners.append((directory.name, candidate.get("source_sha256")))
            # A renamed/re-ingested document still claimed its old original.
            # Retain that evidence so modernization cannot erase a conflict.
            for directory in self.bronze.iterdir():
                if not directory.is_dir() or not (directory / "original.json").exists():
                    continue
                record = self._original_record(directory)
                if record.get("slug") != directory.name:
                    raise SourceIdentityError("legacy original ownership metadata is inconsistent")
                for claim in record.get("legacy_sources", []):
                    name = safe_upload_name(claim["filename"], allowed_extensions={".pdf"})
                    other = assert_within(self.bronze / name, self.bronze)
                    if os.path.normcase(str(other)) == os.path.normcase(str(path)):
                        owners.append((directory.name, claim.get("source_sha256")))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if not any(owner == slug for owner, _ in owners):
                raise SourceIdentityError("legacy original ownership is inconsistent")
            if len({owner for owner, _ in owners}) > 1 and not all(fingerprint == digest for _, fingerprint in owners):
                raise SourceIdentityError(
                    "legacy original has ambiguous ownership; recover each document's original and re-ingest"
                )
            if any(fingerprint is not None and fingerprint != digest for _, fingerprint in owners):
                raise SourceIdentityError("legacy original fingerprint mismatch; recover the original")
            return path
        except SourceIdentityError:
            raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SourceIdentityError("legacy source metadata is unsafe or inconsistent") from exc

    def _original_dir(self, slug: str) -> Path:
        validate_workspace_slug(slug)
        if slug.endswith(".") or PureWindowsPath(slug).is_reserved():
            raise SourceIdentityError("document slug aliases a reserved filesystem name")
        try:
            for root in (self.bronze, self.silver):
                if any(p.name != slug and p.name.casefold() == slug.casefold() for p in root.iterdir()):
                    raise SourceIdentityError("document slug conflicts with an existing filesystem identity")
            base = self._base_dir(self.bronze, slug)
            silver = self._base_dir(self.silver, slug)
            if base.is_symlink() or silver.is_symlink():
                raise SourceIdentityError("original storage has conflicting ownership")
            base = assert_within(base, self.bronze)
            assert_within(self._doc_dir(self.silver, slug) / "index.json", self.silver)
            return base
        except (UnsafeUploadError, OSError) as exc:
            raise SourceIdentityError("original storage path is unsafe or conflicting") from exc

    @staticmethod
    def _original_record(base: Path) -> dict[str, Any]:
        try:
            root = os.path.realpath(os.fspath(base))
            candidate = os.path.realpath(os.path.join(root, "original.json"))
            if not candidate.startswith(root + os.sep):
                raise SourceIdentityError("original source metadata escapes its document")
            path = Path(candidate)
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError
            return record
        except (OSError, ValueError) as exc:
            raise SourceIdentityError("original source metadata is invalid; recover the original") from exc

    @staticmethod
    def _verified_original(base: Path, slug: str, source: Any) -> Path | None:
        if not isinstance(source, dict) or source.get("slug") != slug:
            raise SourceIdentityError("original source ownership does not match document identity")
        digest = source.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise SourceIdentityError("original source fingerprint is invalid")
        try:
            root = os.path.realpath(os.fspath(base))
            candidate = os.path.realpath(os.path.join(root, f"{digest}.pdf"))
            if not candidate.startswith(root + os.sep):
                raise SourceIdentityError("original source escapes its document")
            path = Path(candidate)
            if not path.is_file():
                return None
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise SourceIdentityError("original source fingerprint mismatch; recover the original")
            return path
        except OSError as exc:
            raise SourceIdentityError("original source cannot be read") from exc
        except UnsafeUploadError as exc:
            raise SourceIdentityError("original source is unsafe or its fingerprint does not match") from exc

    async def stash_bronze(self, pdf_bytes: bytes, filename: str, *, slug: str) -> Path:
        clean = safe_upload_name(filename, allowed_extensions={".pdf"})
        source = original_source(pdf_bytes, slug)
        base = self._original_dir(slug)
        if base.exists() and not base.is_dir():
            raise SourceIdentityError("original storage conflicts with an existing legacy file")
        # Serializes even filesystem aliases of a slug. The exact recorded
        # owner must also agree (Windows treats case variants as one path).
        async with self.ingest_lock(slug):
            record_path = base / "original.json"
            previous = self._original_record(base) if record_path.exists() else {}
            if record_path.exists() and previous.get("slug") != slug:
                raise SourceIdentityError("original storage belongs to a different document slug")
            try:
                legacy_sources = previous.get("legacy_sources", [])
                if not isinstance(legacy_sources, list):
                    raise SourceIdentityError("original ownership history is invalid")
                for claim in legacy_sources:
                    if not isinstance(claim, dict):
                        raise SourceIdentityError("original ownership history is invalid")
                    safe_upload_name(claim.get("filename"), allowed_extensions={".pdf"})
                index = await self.get_index(slug)
                if index is None and (self._doc_dir(self.silver, slug) / "index.json").exists():
                    raise SourceIdentityError("document source metadata is inconsistent")
                if index is not None:
                    if not isinstance(index, dict) or not isinstance(index.get("document"), dict):
                        raise SourceIdentityError("document source metadata is inconsistent")
                    document = index["document"]
                    if "source" not in document:
                        claim = {"filename": safe_upload_name(document.get("filename"), allowed_extensions={".pdf"})}
                        if "source_sha256" in document:
                            claim["source_sha256"] = document["source_sha256"]
                        if claim not in legacy_sources:
                            legacy_sources = [*legacy_sources, claim]
                target = assert_within(base / f"{source['sha256']}.pdf", base)
                record_path = assert_within(record_path, base)
                if target.exists():
                    if self._verified_original(base, slug, source) is None:
                        raise SourceIdentityError("original source target is not a file")
                else:
                    base.mkdir(parents=True, exist_ok=True)
                    tmp = base / f"{uuid4().hex}.tmp"
                    try:
                        tmp.write_bytes(pdf_bytes)
                        os.replace(tmp, target)
                    finally:
                        tmp.unlink(missing_ok=True)
                tmp = base / f"{uuid4().hex}.tmp"
                try:
                    tmp.write_text(json.dumps({**source, "filename": clean, "legacy_sources": legacy_sources}), encoding="utf-8")
                    os.replace(tmp, record_path)
                finally:
                    tmp.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                raise SourceIdentityError("original source could not be stored safely") from exc
            return target

    async def write_silver_artifact(self, slug: str, name: str, payload: bytes | str) -> Path:
        # Callers pass pipeline-internal names, but the slug can arrive from
        # HTTP/MCP/CLI arguments (e.g. the DPI page-image variants). Inline
        # normalise-then-prefix-check (not delegated) so the containment
        # barrier sits in the same function that builds the path.
        base = os.path.realpath(os.fspath(self.silver))
        candidate = os.path.normpath(os.path.join(os.fspath(self._doc_dir(self.silver, slug)), name))
        if not candidate.startswith(base + os.sep):
            raise UnsafeUploadError(
                f"silver artifact path escapes the silver dir: {slug!r}/{name!r}"
            )
        target = Path(candidate)
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

    # ── Ingest activity (issue #51) ──────────────────────────────────────
    #
    # A tiny per-slug JSON written as the pipeline advances. Kept in its own
    # ``ingest_status/`` tree (not silver) so it never collides with corpus
    # artifacts and is trivial to list. The slug is validated against the
    # filename rules so a crafted slug can't escape the directory.

    def _activity_path(self, slug: str) -> Path:
        # The slug is the file stem. Reject anything with a path component or
        # traversal up front, then verify containment via the resolved path so
        # a crafted slug can never escape the ingest_status directory.
        if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
            raise UnsafeUploadError(f"unsafe ingest-activity slug: {slug!r}")
        target = self.ingest_status / f"{slug}.json"
        assert_within(target, self.ingest_status)
        return target

    async def write_ingest_activity(self, slug: str, record: dict[str, Any]) -> None:
        target = self._activity_path(slug)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({**record, "slug": slug})
        # Atomic upsert so a concurrent reader never sees a half-written file.
        tmp = target.with_suffix(".json.tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(payload)
        os.replace(tmp, target)

    async def read_ingest_activity(self, slug: str) -> dict[str, Any] | None:
        try:
            target = self._activity_path(slug)
        except UnsafeUploadError:
            return None
        if not target.is_file():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    async def list_ingest_activity(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.ingest_status.is_dir():
            return out
        for p in sorted(self.ingest_status.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(data, dict):
                data.setdefault("slug", p.stem)
                out.append(data)
        return out

    async def write_gold_region_file(self, slug: str, page: int, regions: list[dict[str, Any]]) -> Path:
        # The slug reaches this write from CLI/MCP/HTTP arguments (derive /
        # remove region), so the path is a path-injection sink. Inline
        # normalise-then-prefix-check (not delegated) so the containment
        # barrier sits in the same function that builds the path — the same
        # guard `write_crop` applies.
        if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
            raise UnsafeUploadError(f"unsafe document slug: {slug!r}")
        base = os.path.realpath(os.fspath(self.gold))
        candidate = os.path.normpath(
            os.path.join(os.fspath(self._doc_dir(self.gold, slug)), "pages", f"{int(page)}.regions.json")
        )
        if not candidate.startswith(base + os.sep):
            raise UnsafeUploadError(f"document slug {slug!r} escapes the gold dir")
        target = Path(candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        normalised = _normalise_regions(regions)
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(json.dumps({"page": page, "regions": normalised}, indent=2))
        return target

    @document_view
    async def add_derived_region(self, slug: str, region: dict[str, Any]) -> Path:
        page = _derived_page(region)
        if page is None:
            raise ValueError(
                "add_derived_region: cannot resolve page from region.source_ref.page "
                "or region.page"
            )
        async with self._lock:
            # Same inline barrier as `write_gold_region_file`: the slug is
            # caller-supplied, so check containment right where the read path
            # is built.
            if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
                raise UnsafeUploadError(f"unsafe document slug: {slug!r}")
            base = os.path.realpath(os.fspath(self.gold))
            candidate = os.path.normpath(
                os.path.join(os.fspath(self._doc_dir(self.gold, slug)), "pages", f"{page}.regions.json")
            )
            if not candidate.startswith(base + os.sep):
                raise UnsafeUploadError(f"document slug {slug!r} escapes the gold dir")
            target = Path(candidate)
            existing: list[dict[str, Any]] = []
            if target.is_file():
                data = json.loads(target.read_text())
                raw = data.get("regions", data) if isinstance(data, dict) else data
                if isinstance(raw, list):
                    existing = [r for r in raw if isinstance(r, dict)]
            rid = region.get("id")
            kept = [r for r in existing if r.get("id") != rid] if rid else existing
            kept.append(region)
            return await self.write_gold_region_file(slug, page, kept)

    async def write_embeddings(self, slug: str, payload: dict[str, Any]) -> Path:
        # Inline normalise-then-prefix-check (not delegated): the slug can
        # arrive from a request (remove_region's cleanup writes here).
        base = os.path.realpath(os.fspath(self.gold))
        candidate = os.path.normpath(os.path.join(os.fspath(self._doc_dir(self.gold, slug)), "embeddings.json"))
        if not candidate.startswith(base + os.sep):
            raise UnsafeUploadError(f"document slug {slug!r} escapes the gold dir")
        target = Path(candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{uuid4().hex}.tmp")
        try:
            async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload))
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return target

    @document_view
    async def get_embeddings(self, slug: str) -> dict[str, Any] | None:
        base = os.path.realpath(os.fspath(self.gold))
        candidate = os.path.normpath(os.path.join(os.fspath(self._doc_dir(self.gold, slug)), "embeddings.json"))
        if not candidate.startswith(base + os.sep):
            return None
        target = Path(candidate)
        if not target.is_file():
            return None
        async with aiofiles.open(target, encoding="utf-8") as f:
            return json.loads(await f.read())

    async def list_embeddings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.gold.is_dir():
            return out
        for d in sorted(self.gold.iterdir()):
            p = self.snapshot(d.name)._doc_dir(self.gold, d.name) / "embeddings.json"
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
