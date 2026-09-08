"""Lazy region-crop and page-image rendering - the gold crop contract.

Gold promises a crop per region at ``gold/<slug>/pages/<page>/<region_id>.png``,
but the ingest pipeline never wrote one - only readers existed. These read-ops
close that gap without a migration: when a crop is requested and the PNG is
missing, it is rendered from the bronze PDF (region bbox + a small margin) at
that moment, persisted at the canonical path, and served. Every already-ingested
document is fixed retroactively on first read.

Also here: page images re-rendered at a caller-chosen DPI. The silver page PNG
is ~150 dpi, far too coarse for e.g. chart tracing (a pump curve is ~20 px
wide); an explicit ``dpi`` renders from bronze and caches the variant beside
the silver page image.

Lives in core so CLI (`anchor crop` / `anchor page-image`), MCP (`get_crop` /
`get_page_image`) and HTTP (`/crops/...` / `/pages/{n}/image`) share one
behaviour - adapter parity is a house rule.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer

#: Default render DPI for lazily generated crops. 150 (the silver page
#: default) is too coarse for downstream consumers like chart tracing.
DEFAULT_CROP_DPI = 300
#: Sanity cap on caller-supplied DPI; also the floor below which text smears.
MAX_RENDER_DPI = 600
MIN_RENDER_DPI = 72
#: Breathing room around the region bbox, in PDF points.
CROP_MARGIN_PT = 3.0

CROP_REF_HELP = (
    "valid form is '<page>/<region_id>.png' (e.g. '4/r1.png'; "
    "'p4/r1' is also accepted)"
)

_REGION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class CropUnavailable(ValueError):
    """The crop/page image cannot be produced; the message says why."""


def parse_crop_ref(rel_path: str) -> tuple[int | None, str]:
    """Parse a crop reference into ``(page, region_id)``.

    Accepts the canonical ``'4/r1.png'`` plus the inspect-region token styles
    ``'p4/r1'``, ``'4/r1'``, ``'p4/r1.png'`` and a bare ``'r1'`` / ``'r1.png'``
    (any page). Raises :class:`CropUnavailable` for anything else.
    """
    ref = (rel_path or "").strip()
    if ref.lower().endswith(".png"):
        ref = ref[:-4]
    page: int | None = None
    rid = ref
    if "/" in ref:
        page_part, rid = ref.split("/", 1)
        try:
            page = int(page_part.lstrip("pP"))
        except ValueError:
            page = None
        if page is None or page < 1:
            raise CropUnavailable(f"unrecognised crop reference {rel_path!r}: {CROP_REF_HELP}")
    if not _REGION_ID_RE.fullmatch(rid) or rid in {".", ".."}:
        raise CropUnavailable(f"unrecognised crop reference {rel_path!r}: {CROP_REF_HELP}")
    return page, rid


def clamp_dpi(dpi: int) -> int:
    return max(MIN_RENDER_DPI, min(MAX_RENDER_DPI, int(dpi)))


async def _find_region(
    store: DocStore, slug: str, page: int | None, region_id: str
) -> tuple[int, dict[str, Any]] | None:
    gold = await store.get_regions(slug, page)
    pages = gold.get("pages", {}) if isinstance(gold, dict) else {}
    for pg, regions in pages.items():
        for region in regions or []:
            if isinstance(region, dict) and region.get("id") == region_id:
                return int(pg), region
    return None


async def _not_found_message(
    store: DocStore, slug: str, page: int | None, region_id: str
) -> str:
    """Explain whether the region exists at all, and the valid address form."""
    gold = await store.get_regions(slug)
    pages = gold.get("pages", {}) if isinstance(gold, dict) else {}
    for pg, regions in pages.items():
        for region in regions or []:
            if isinstance(region, dict) and region.get("id") == region_id:
                return (
                    f"region {region_id!r} exists in {slug!r} but on page {pg}, "
                    f"not page {page}: request '{pg}/{region_id}.png'"
                )
    if not pages:
        return f"no gold regions found for {slug!r} (is the document gold-extracted?)"
    known = sorted(pages)
    return (
        f"region {region_id!r} not found in {slug!r} "
        f"(pages with regions: {', '.join(str(p) for p in known)}); {CROP_REF_HELP}"
    )


async def _bronze_pdf(store: DocStore, slug: str) -> Path:
    pdf = await store.get_raw_pdf_path(slug)
    if pdf is None or str(pdf).startswith("memory://"):
        raise CropUnavailable(
            f"bronze PDF not available for {slug!r}; cannot render on demand"
        )
    return pdf


def _expand_and_clamp(
    bbox: list[float], size: tuple[float, float] | None
) -> list[float]:
    left, top, right, bottom = (float(v) for v in bbox)
    left, right = min(left, right) - CROP_MARGIN_PT, max(left, right) + CROP_MARGIN_PT
    top, bottom = min(top, bottom) - CROP_MARGIN_PT, max(top, bottom) + CROP_MARGIN_PT
    if size is not None:
        w, h = size
        left, right = max(0.0, left), min(w, right)
        top, bottom = max(0.0, top), min(h, bottom)
    return [left, top, right, bottom]


async def get_region_crop(
    store: DocStore,
    renderer: PdfRenderer,
    slug: str,
    rel_path: str,
    *,
    dpi: int | None = None,
) -> Path:
    """The crop PNG for one gold region, rendered lazily on first request.

    Serves the persisted crop when it exists; otherwise renders the region's
    bbox (+``CROP_MARGIN_PT``) from the bronze PDF at ``dpi`` (default
    ``DEFAULT_CROP_DPI``), persists it at the canonical
    ``<page>/<region_id>.png`` rel path, and returns that path. An explicit
    ``dpi`` re-renders and overwrites the cached crop at that resolution.
    Raises :class:`CropUnavailable` with an actionable message otherwise.
    """
    # Whatever the reference style, an existing file wins when no explicit
    # dpi asks for a re-render.
    if dpi is None:
        existing = await store.get_crop_path(slug, rel_path)
        if existing is not None:
            return existing
    page_hint, region_id = parse_crop_ref(rel_path)
    canonical = f"{page_hint}/{region_id}.png" if page_hint is not None else None
    if dpi is None and canonical is not None and canonical != rel_path:
        existing = await store.get_crop_path(slug, canonical)
        if existing is not None:
            return existing

    found = await _find_region(store, slug, page_hint, region_id)
    if found is None:
        raise CropUnavailable(await _not_found_message(store, slug, page_hint, region_id))
    page, region = found
    bbox = region.get("bbox") or region.get("approx_bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4):
        raise CropUnavailable(
            f"region {region_id!r} on page {page} of {slug!r} has no bbox to crop"
        )
    if dpi is None:
        existing = await store.get_crop_path(slug, f"{page}/{region_id}.png")
        if existing is not None:
            return existing

    pdf = await _bronze_pdf(store, slug)
    sizes = await renderer.page_sizes(pdf)
    clip = _expand_and_clamp(bbox, sizes.get(page))
    try:
        png = await renderer.crop_region(
            pdf, page, clip, fmt="png", dpi=clamp_dpi(dpi or DEFAULT_CROP_DPI),
        )
    except (IndexError, ValueError) as e:
        raise CropUnavailable(
            f"could not render crop for region {region_id!r} on page {page}: {e}"
        ) from e
    return await store.write_crop(slug, f"{page}/{region_id}.png", png)


async def get_page_image(
    store: DocStore,
    renderer: PdfRenderer,
    slug: str,
    page: int,
    *,
    dpi: int | None = None,
) -> Path | None:
    """The page PNG, at the silver default or re-rendered at an explicit DPI.

    ``dpi=None`` returns the stored silver page image (or ``None`` when the
    page does not exist). An explicit ``dpi`` renders the full page from the
    bronze PDF at that resolution (capped to ``MAX_RENDER_DPI``) and caches
    the variant beside the silver image, so repeated reads are free.
    """
    if dpi is None:
        return await store.get_page_image_path(slug, page)
    dpi = clamp_dpi(dpi)
    cached = await store.get_page_image_path(slug, page, dpi=dpi)
    if cached is not None:
        return cached
    pdf = await _bronze_pdf(store, slug)
    sizes = await renderer.page_sizes(pdf)
    size = sizes.get(int(page))
    if size is None:
        raise CropUnavailable(
            f"page {page} out of range for {slug!r} (document has {len(sizes)} pages)"
        )
    try:
        png = await renderer.crop_region(
            pdf, int(page), [0.0, 0.0, size[0], size[1]], fmt="png", dpi=dpi,
        )
    except (IndexError, ValueError) as e:
        raise CropUnavailable(f"could not render page {page} at {dpi} dpi: {e}") from e
    await store.write_silver_artifact(slug, f"pages/{int(page)}@{dpi}dpi.png", png)
    return await store.get_page_image_path(slug, page, dpi=dpi)
