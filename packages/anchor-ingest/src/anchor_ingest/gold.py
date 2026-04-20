"""Gold layer — semantic regions, sections, and cropped assets.

The gold atom is the *region*: a tagged, source-grounded visual block on a
page. Sections (an optional second view) group regions semantically. See
`PIPELINE.md` for the full design.

This module ships:
    - `Region` / `RegionCrop` / `Section` Pydantic schemas
    - `crop_region_png` / `crop_region_svg` / `crop_region_pdf` — pure
      deterministic cropping over a bronze PDF given a BOTTOMLEFT bbox
    - `extract_page_regions` — VLM extractor (uses an injected client so
      tests can mock without hitting OpenAI)
    - `RegionExtractorClient` Protocol the extractor expects
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from .silver import snap_to_docling_items
from .tags import is_known_tag

# Default frontier model for the gold extractor. Override per call.
DEFAULT_GOLD_MODEL = "gpt-5.4"


# ── Schemas ──────────────────────────────────────────────────────────────────


class SourceRef(BaseModel):
    page: int
    bbox: list[float]
    item_indices: list[int] = Field(default_factory=list)


class RegionCrop(BaseModel):
    png: str
    svg: str | None = None
    pdf: str | None = None


RegionKind = Literal[
    "chart",
    "spec_block",
    "table",
    "figure",
    "diagram",
    "text",
    "caption",
]


class Region(BaseModel):
    id: str
    page: int
    bbox: list[float]
    kind: RegionKind
    title: str
    description: str
    markdown: str | None = None
    data: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    crops: RegionCrop | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags_must_be_known(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if not is_known_tag(t)]
        if bad:
            raise ValueError(f"unknown tag(s): {bad}")
        return v


class Section(BaseModel):
    id: str
    title: str
    path: list[str]
    level: int
    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    page_range: tuple[int, int]
    region_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    kind: Literal["narrative", "property_group", "table_2d", "figure", "mixed"] = "mixed"

    @field_validator("tags")
    @classmethod
    def _tags_must_be_known(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if not is_known_tag(t)]
        if bad:
            raise ValueError(f"unknown tag(s): {bad}")
        return v


class PageRegions(BaseModel):
    """The on-disk shape of `gold/<slug>/pages/N.regions.json`."""
    page: int
    regions: list[Region]
    schema_version: int = 1


# ── Cropping ─────────────────────────────────────────────────────────────────


def _bottomleft_to_pymupdf(page_height: float, bbox: list[float]) -> tuple[float, float, float, float]:
    """Convert BOTTOMLEFT [l, top, r, bottom] -> PyMuPDF [x0, y0, x1, y1] (top-left)."""
    left, top, right, bottom = bbox
    return (left, page_height - top, right, page_height - bottom)


def crop_region_png(
    pdf_path: Path,
    page: int,
    bbox: list[float],
    out_path: Path,
    *,
    dpi: int = 200,
) -> Path:
    """Render a BOTTOMLEFT bbox region of a PDF page to PNG."""
    import pymupdf

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf_path) as doc:
        p = doc[page - 1]
        rect = pymupdf.Rect(*_bottomleft_to_pymupdf(p.rect.height, bbox))
        pix = p.get_pixmap(dpi=dpi, clip=rect)
        pix.save(out_path)
    return out_path


def crop_region_svg(
    pdf_path: Path,
    page: int,
    bbox: list[float],
    out_path: Path,
) -> Path:
    """Export a BOTTOMLEFT bbox region of a PDF page as SVG (vector preserved).

    PyMuPDF always exports the full page as SVG. We crop by:
    1. Setting the viewBox to the region rect (so it renders only that area).
    2. Setting explicit width/height so the SVG scales correctly.
    """
    import re as _re

    import pymupdf

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf_path) as doc:
        p = doc[page - 1]
        rect = pymupdf.Rect(*_bottomleft_to_pymupdf(p.rect.height, bbox))
        svg = p.get_svg_image(matrix=pymupdf.Identity, text_as_path=False)

        # Replace the <svg> tag's viewBox, width, and height to crop to the region.
        new_viewbox = f"{rect.x0:.1f} {rect.y0:.1f} {rect.width:.1f} {rect.height:.1f}"
        svg = _re.sub(
            r'viewBox="[^"]*"',
            f'viewBox="{new_viewbox}"',
            svg,
            count=1,
        )
        svg = _re.sub(
            r'width="[^"]*"',
            f'width="{rect.width:.1f}pt"',
            svg,
            count=1,
        )
        svg = _re.sub(
            r'height="[^"]*"',
            f'height="{rect.height:.1f}pt"',
            svg,
            count=1,
        )
        out_path.write_text(svg, encoding="utf-8")
    return out_path


def crop_region_pdf(
    pdf_path: Path,
    page: int,
    bbox: list[float],
    out_path: Path,
) -> Path:
    """Produce a single-page mini-PDF cropped to a BOTTOMLEFT bbox region."""
    import pymupdf

    out_path.parent.mkdir(parents=True, exist_ok=True)
    src = pymupdf.open(pdf_path)
    try:
        new = pymupdf.open()
        new.insert_pdf(src, from_page=page - 1, to_page=page - 1)
        p = new[0]
        rect = pymupdf.Rect(*_bottomleft_to_pymupdf(p.rect.height, bbox))
        p.set_cropbox(rect)
        new.save(out_path)
        new.close()
    finally:
        src.close()
    return out_path


# ── VLM extractor ────────────────────────────────────────────────────────────


class RegionExtractorClient(Protocol):
    """Minimal interface the extractor needs from an LLM client.

    The extractor passes a page image path + the docling items on that page
    and expects a list of region dicts (validated through the `Region`
    schema). The default implementation wraps OpenAI's responses API; tests
    inject a stub.
    """

    def extract_page(
        self,
        *,
        page_image: Path,
        page_no: int,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]: ...


@dataclass
class _StubClient:
    """Default no-op client. Real OpenAI client is wired up at the call site
    so we don't import it (and pay the cost) just to import this module."""

    def extract_page(self, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError(
            "No RegionExtractorClient configured. Pass `client=...` to "
            "extract_page_regions, or build a real client at the call site."
        )


def extract_page_regions(
    docling: dict[str, Any],
    *,
    page: int,
    page_image: Path,
    pdf_path: Path,
    out_dir: Path,
    client: RegionExtractorClient | None = None,
    model: str = DEFAULT_GOLD_MODEL,
) -> PageRegions:
    """Two-pass region extraction for a single page.

    1. VLM pass: ask `client` for region candidates given the page image and
       docling items on this page.
    2. Snap + crop pass: snap each region's approximate bbox to docling
       items, build crops (PNG always; SVG when kind in {chart, diagram,
       figure}), and persist them under `out_dir/{page}/`.

    Returns the validated `PageRegions` object; the caller is responsible for
    writing it to `out_dir/{page}.regions.json`.
    """
    items = docling.get("items") or []
    page_items = [it for it in items if isinstance(it, dict) and it.get("page") == page]

    extractor = client or _StubClient()
    raw_regions = extractor.extract_page(
        page_image=page_image,
        page_no=page,
        docling_items=page_items,
        model=model,
    )

    regions: list[Region] = []
    for i, raw in enumerate(raw_regions):
        # Snap the VLM bbox to docling items.
        approx = list(raw.get("bbox") or [])
        snapped, indices = snap_to_docling_items(docling, page, approx)
        bbox = snapped or approx
        rid = raw.get("id") or f"p{page}-r{i + 1}"

        # Build crops.
        crops_obj: RegionCrop | None = None
        if bbox:
            stem = f"{rid}"
            png_path = out_dir / str(page) / f"{stem}.png"
            svg_path = out_dir / str(page) / f"{stem}.svg"
            crop_region_png(pdf_path, page, bbox, png_path)
            crop_region_svg(pdf_path, page, bbox, svg_path)
            crops_obj = RegionCrop(
                png=str(png_path.relative_to(out_dir)),
                svg=str(svg_path.relative_to(out_dir)),
            )

        regions.append(
            Region(
                id=rid,
                page=page,
                bbox=bbox,
                kind=raw.get("kind", "text"),
                title=raw.get("title", ""),
                description=raw.get("description", ""),
                markdown=raw.get("markdown"),
                data=raw.get("data"),
                tags=[t for t in (raw.get("tags") or []) if is_known_tag(t)],
                entities=raw.get("entities", []),
                crops=crops_obj,
                source_refs=[SourceRef(page=page, bbox=bbox, item_indices=indices)] if bbox else [],
            )
        )

    return PageRegions(page=page, regions=regions)
