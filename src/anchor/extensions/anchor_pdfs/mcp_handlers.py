"""MCP tool definitions backed by IngestService and DocStore."""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_pdfs import mcp_tool_definitions
from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService, SynopsisService


def tool_definitions() -> list[dict[str, Any]]:
    """Return the PDF MCP catalog from its focused definition module."""
    return mcp_tool_definitions.tool_definitions()


# ── Byte-fetch envelope ────────────────────────────────────────────────────
#
# Read endpoints that return binary blobs (page images, region crops, raw
# PDFs) share a single response envelope: an agent on the same host can
# read the path directly; a remote agent (or an in-memory store) gets the
# bytes inlined as base64. The envelope makes the contract explicit and
# lets the agent decide once, up front, which transport it wants.
def _byte_envelope(path: Path | None, *, fmt: str, fallback_ext: str = "") -> str:
    if path is None:
        return json.dumps({"error": "not found"})
    is_memory = str(path).startswith("memory://")
    if fmt == "path":
        if is_memory:
            return json.dumps({"error": "in-memory store has no real path; request format=base64"})
        return json.dumps({"format": "path", "value": str(path), "content_type": _ctype(path, fallback_ext)})
    if fmt == "base64":
        if is_memory:
            # Memory store can't read by path; the caller has nothing to
            # decode. Surface a clear error so the agent doesn't burn
            # tokens on an empty payload.
            return json.dumps({"error": "in-memory store does not expose bytes via MCP yet"})
        try:
            raw = path.read_bytes()
        except OSError as e:
            return json.dumps({"error": f"read failed: {e}"})
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": _ctype(path, fallback_ext),
            "size_bytes": len(raw),
        })
    return json.dumps({"error": f"unknown format: {fmt!r} (use 'path' or 'base64')"})


def _ctype(path: Path, fallback_ext: str) -> str:
    guess, _ = mimetypes.guess_type(path.name or f"x{fallback_ext}")
    return guess or "application/octet-stream"


def gold_skipped_note() -> dict[str, Any]:
    """Machine- and human-readable note for a no-key gold skip (issue #226).

    ``ingest_pdf`` runs silver but cannot run the gold (region) stage when the
    environment has no provider/key wired (``region_extractor`` is None). The
    result then reads as a bland success with zero regions. This note makes the
    skip discoverable and points at the two fixes: the offline harness ingest
    path (no key, embeds locally) and the endpoint-key remedy. Kept as a small
    pure helper so it can be unit-tested and reused across surfaces.
    """
    from anchor.infra.providers import ANCHOR_KEY_VAR

    return {
        "gold_skipped": True,
        "reason": (
            "Gold (region) extraction was skipped: this environment has no "
            "vision provider/key wired, so only bronze/silver ran."
        ),
        "fix_offline": (
            "Ingest key-free through the harness tools: ingest_begin -> "
            "ingest_get_page -> ingest_submit_page -> ingest_finalize "
            "(the agent reads pages, embeddings are computed locally, no key)."
        ),
        "fix_key": (
            f"Or configure an endpoint: set {ANCHOR_KEY_VAR} in the "
            "environment's .env (a plain OPENAI_API_KEY there is ignored), "
            "then re-ingest. Run `anchor check` to verify the data zone + key."
        ),
    }


_SESSION_TOOL_NAMES = {
    "ingest_begin", "ingest_get_page", "ingest_submit_page",
    "ingest_status", "ingest_finalize", "ingest_abort",
}


async def _call_session_tool(
    ingest_session: IngestSessionService, name: str, args: dict[str, Any],
) -> str:
    if name == "ingest_begin":
        path = Path(args["pdf_path"])
        if not path.exists():
            return json.dumps({"error": f"PDF not found: {path}"})
        order = await ingest_session.ingest_begin(
            path.read_bytes(), path.name,
            slug=args.get("slug"),
            dpi=args.get("dpi"),
            force=args.get("force", False),
        )
        return json.dumps(order)
    if name == "ingest_get_page":
        item = await ingest_session.ingest_get_page(args["session_id"], int(args["page"]))
        if "error" in item:
            return json.dumps(item)
        image_path = item.pop("image_path", None)
        item["image"] = json.loads(_byte_envelope(
            Path(image_path) if image_path else None,
            fmt=args.get("format", "path"),
            fallback_ext=".png",
        ))
        return json.dumps(item)
    if name == "ingest_submit_page":
        verdict = await ingest_session.ingest_submit_page(
            args["session_id"], int(args["page"]),
            regions=args.get("regions") or [],
            polished_md=args.get("polished_md"),
            protocol_version=args.get("protocol_version"),
        )
        return json.dumps(verdict)
    if name == "ingest_status":
        return json.dumps(await ingest_session.ingest_status(
            args.get("session_id"), slug=args.get("slug"),
        ))
    if name == "ingest_finalize":
        return json.dumps(await ingest_session.ingest_finalize(
            args["session_id"],
            allow_missing_pages=args.get("allow_missing_pages"),
            declared_model=args.get("declared_model"),
        ))
    if name == "ingest_abort":
        return json.dumps(await ingest_session.ingest_abort(args["session_id"]))
    return json.dumps({"error": f"unknown session tool: {name}"})


async def call_tool(
    ingest: IngestService, store: DocStore, name: str, args: dict[str, Any],
    *, synopsis: SynopsisService | None = None,
    ingest_session: IngestSessionService | None = None,
) -> str:
    if name in _SESSION_TOOL_NAMES:
        if ingest_session is None:
            return json.dumps({"error": "harness ingest sessions not wired on this server"})
        return await _call_session_tool(ingest_session, name, args)
    if name == "ingest_pdf":
        from pathlib import Path
        path = Path(args["pdf_path"])
        if not path.exists():
            return json.dumps({"error": f"PDF not found: {path}"})
        pdf_bytes = path.read_bytes()
        want_regions = not args.get("skip_regions", False)
        summary = await ingest.ingest_pdf(
            pdf_bytes, path.name,
            slug=args.get("slug"),
            polish=not args.get("skip_polish", False),
            regions=want_regions,
            force=args.get("force", False),
            full_page_ocr=args.get("full_page_ocr", False),
        )
        # Gold silently skips when the caller wanted regions but no vision
        # provider/key is wired (region_extractor is None). Attach an actionable
        # note pointing at the offline harness path + the key remedy (#226). Not
        # applied to an idempotent skip (already-ingested) or a forced re-run.
        if (
            want_regions
            and ingest.region_extractor is None
            and not summary.get("skipped")
        ):
            summary["note"] = gold_skipped_note()
        return json.dumps(summary)
    if name == "list_documents":
        return json.dumps(await store.list_documents())
    if name == "list_active_ingests":
        from anchor.core.clock import SystemClock
        from anchor.extensions.anchor_pdfs.core.ingest_activity import (
            IngestActivityRegistry,
        )
        registry = IngestActivityRegistry(store=store, _now=SystemClock().now)
        activities = await registry.snapshot()
        return json.dumps({"ingests": [a.to_dict() for a in activities]})
    if name == "get_ingest_status":
        from anchor.core.clock import SystemClock
        from anchor.extensions.anchor_pdfs.core.ingest_activity import (
            IngestActivityRegistry,
        )
        registry = IngestActivityRegistry(store=store, _now=SystemClock().now)
        activity = await registry.get(args["slug"])
        if activity is None:
            return json.dumps({"slug": args["slug"], "found": False})
        return json.dumps({"found": True, **activity.to_dict()})
    if name == "get_document_index":
        out = await store.get_index(args["slug"])
        return json.dumps(out) if out else json.dumps({"error": "not found"})
    if name == "get_gold_regions":
        return json.dumps(await store.get_regions(args["slug"], page=args.get("page")))
    if name == "get_page_text":
        text = await store.get_page_text(args["slug"], int(args["page"]))
        return text if text is not None else json.dumps({"error": "not found"})
    if name == "locate_text":
        path = await store.get_raw_pdf_path(args["slug"])
        if path is None or str(path).startswith("memory://"):
            return json.dumps({"error": f"raw PDF not available for slug: {args['slug']}"})
        try:
            quads = await ingest.renderer.locate_text(
                path, int(args["page"]), args["query"], args.get("within_bbox"),
            )
        except (IndexError, ValueError) as e:
            return json.dumps({"error": str(e)})
        return json.dumps({
            "slug": args["slug"], "page": int(args["page"]),
            "query": args["query"], "quads": quads,
        })
    if name == "get_gold_map":
        out = await store.get_gold_map(args["slug"])
        return json.dumps(out) if out is not None else json.dumps({"error": "not found"})
    if name == "get_page_image":
        path = await store.get_page_image_path(args["slug"], int(args["page"]))
        return _byte_envelope(path, fmt=args.get("format", "path"), fallback_ext=".png")
    if name == "get_crop":
        path = await store.get_crop_path(args["slug"], args["rel_path"])
        # Content-type inference falls back to the extension of rel_path
        # for memory-backed stores that return None.
        ext = "." + args["rel_path"].rsplit(".", 1)[-1] if "." in args["rel_path"] else ""
        return _byte_envelope(path, fmt=args.get("format", "path"), fallback_ext=ext)
    if name == "get_pdf":
        path = await store.get_raw_pdf_path(args["slug"])
        return _byte_envelope(path, fmt=args.get("format", "path"), fallback_ext=".pdf")
    if name == "embed_document":
        if ingest.embedder is None:
            return json.dumps({"error": "no embedder wired"})
        slug = args["slug"]
        existing = await store.get_embeddings(slug)
        if existing and not args.get("overwrite", False):
            return json.dumps({
                "slug": slug, "skipped": True, "reason": "already embedded",
                "embed_model": existing.get("embed_model"),
            })
        n = await ingest.embed_document(slug)
        return json.dumps({"slug": slug, "embedded": n, "embed_model": ingest.embed_model_id})
    if name == "search_documents":
        try:
            return json.dumps(await ingest.search(args["query"], k=int(args.get("k", 10))))
        except RuntimeError as e:
            return json.dumps({"error": str(e)})
    if name == "derive_region":
        try:
            return json.dumps(
                await ingest.derive_region(
                    args["slug"], args["parent_region_id"], args["region"]
                )
            )
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})
    if name == "get_embeddings_meta":
        slug = args["slug"]
        data = await store.get_embeddings(slug)
        if data is None:
            return json.dumps({"error": f"no embeddings for {slug}"})
        return json.dumps({
            "slug": slug,
            "embed_model": data.get("embed_model"),
            "dim": data.get("dim"),
            "embedded_at": data.get("embedded_at"),
            "vector_count": len(data.get("vectors", [])),
        })
    if name == "extract_pointed":
        from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
            PointedExtractionError,
        )
        try:
            return json.dumps(await ingest.extract_pointed(
                args["slug"],
                select=args.get("select"),
                shape=args.get("shape"),
            ))
        except PointedExtractionError as e:
            return json.dumps({"error": str(e)})
    if name == "compose_synopsis":
        if synopsis is None:
            return json.dumps({"error": "synopsis service not wired (renderer/store missing)"})
        slug = args["slug"]
        entity = args["entity"]
        output = args.get("output", "json")
        try:
            if output == "json":
                from dataclasses import asdict
                data = await synopsis.compose(slug=slug, entity=entity)
                return json.dumps(asdict(data))
            if output == "pdf":
                pdf_bytes = await synopsis.render_pdf(slug=slug, entity=entity)
                return json.dumps({
                    "format": "base64",
                    "value": base64.b64encode(pdf_bytes).decode("ascii"),
                    "content_type": "application/pdf",
                    "size_bytes": len(pdf_bytes),
                })
            if output == "md":
                md = await synopsis.render_markdown(
                    slug=slug, entity=entity,
                    crop_url_base=args.get("crop_url_base"),
                )
                return json.dumps({"format": "text", "value": md, "content_type": "text/markdown"})
            return json.dumps({"error": f"unknown output: {output}"})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool: {name}"})
