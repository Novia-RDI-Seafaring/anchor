"""Render a SynopsisData into a publishable artefact (PDF, Marp markdown).

Pymupdf is the only PDF dep allowed in this layer; Marp markdown is plain
string templating (callers run `marp` themselves to convert to HTML/PDF
if they want a slide deck). The renderer signatures stay small and
synchronous — they take a fully-built ``SynopsisData`` plus an optional
crop-path resolver and return ``bytes`` (PDF) or ``str`` (Marp).
"""
from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import fitz

from anchor.extensions.anchor_pdfs.core.synopsis import SynopsisData


CropPathResolver = Callable[[str, str], Awaitable[Path | None]]
"""(slug, rel_path) → absolute path to the crop image. Usually
``DocStore.get_crop_path`` passed in by the calling service."""


# ── PDF ────────────────────────────────────────────────────────────────────


class PymupdfSynopsisRenderer:
    """Render to a multi-page A4 PDF with cover + specs + chart pages."""

    PAGE_W = 595
    PAGE_H = 842
    MARGIN = 50

    async def render_pdf(
        self,
        data: SynopsisData,
        *,
        resolve_crop: CropPathResolver,
    ) -> bytes:
        doc = fitz.open()

        # Cover
        p = doc.new_page(width=self.PAGE_W, height=self.PAGE_H)
        _text(p, (self.MARGIN, 90), data.title, size=24, font="hebo")
        if data.operating_conditions:
            _box(p, fitz.Rect(self.MARGIN, 130, self.PAGE_W - self.MARGIN, 160),
                 " · ".join(data.operating_conditions), size=10)
        _box(
            p,
            fitz.Rect(self.MARGIN, 180, self.PAGE_W - self.MARGIN, 310),
            f"Synopsis for {data.entity}, derived from the source document. "
            "All values are filtered to {entity} or are general properties that apply to every model. "
            "Consult the source datasheet for context, footnotes, and option lists.".format(entity=data.entity),
            size=10,
        )

        # Specs pages
        for section in data.sections:
            p = doc.new_page(width=self.PAGE_W, height=self.PAGE_H)
            _text(p, (self.MARGIN, 60), section.title, size=18, font="hebo")
            _text(p, (self.MARGIN, 88),
                  f"From page {section.source_ref.page if section.source_ref else '?'} of the source.",
                  size=10)
            y = 125
            for row in section.rows:
                _text(p, (self.MARGIN, y), row.label, size=10, font="hebo")
                _text(p, (self.MARGIN + 280, y), row.value, size=10)
                y += 16
                if y > self.PAGE_H - self.MARGIN - 30:
                    break

        # Crop pages (chart, diagrams)
        for crop in data.crops:
            path = await resolve_crop(data.slug, crop.rel_path)
            if path is None or str(path).startswith("memory://"):
                continue
            p = doc.new_page(width=self.PAGE_W, height=self.PAGE_H)
            _text(p, (self.MARGIN, 60), crop.title, size=18, font="hebo")
            _text(p, (self.MARGIN, 88),
                  f"From page {crop.source_ref.page} of the source (region {crop.source_ref.region_id}).",
                  size=10)
            try:
                pix = fitz.Pixmap(str(path))
                w, h = pix.width, pix.height
                max_w = self.PAGE_W - 2 * self.MARGIN
                max_h = self.PAGE_H - 240
                s = min(max_w / w, max_h / h)
                dw, dh = w * s, h * s
                x = (self.PAGE_W - dw) / 2
                p.insert_image(
                    fitz.Rect(x, 120, x + dw, 120 + dh),
                    filename=str(path),
                )
                if crop.description:
                    _box(p, fitz.Rect(self.MARGIN, 120 + dh + 20,
                                       self.PAGE_W - self.MARGIN, 120 + dh + 90),
                         crop.description, size=9)
            except Exception:  # noqa: BLE001 — best effort on bad crops
                _text(p, (self.MARGIN, 130), f"(could not embed crop {crop.rel_path})", size=10)

        out = doc.tobytes()
        doc.close()
        return out


# ── Marp markdown ──────────────────────────────────────────────────────────


class MarpSynopsisRenderer:
    """Render to a Marp-compatible markdown slide deck (one slide per section)."""

    def render_markdown(self, data: SynopsisData, *, crop_url_for: Callable[[str, str], str] | None = None) -> str:
        # Crop URL strategy: if no resolver is provided, embed relative
        # `<slug>/<rel>` paths the caller will materialise alongside.
        if crop_url_for is None:
            def crop_url_for(slug: str, rel: str) -> str:  # type: ignore[misc]
                return f"crops/{rel}"

        lines: list[str] = [
            "---",
            "marp: true",
            "theme: gaia",
            "class: lead",
            "paginate: true",
            "size: 16:9",
            "backgroundColor: '#fff'",
            "---",
            "",
            f"# {data.title}",
            "",
        ]
        if data.operating_conditions:
            lines += ["## Conditions", ""]
            for c in data.operating_conditions:
                lines.append(f"- {c}")
            lines.append("")

        for section in data.sections:
            lines += ["---", "", f"## {section.title}", ""]
            if section.rows:
                lines += ["| Property | Value |", "| --- | --- |"]
                for r in section.rows:
                    lines.append(f"| **{r.label}** | {r.value} |")
            if section.source_ref:
                lines += ["", f"<small>Source: page {section.source_ref.page}.</small>", ""]

        for crop in data.crops:
            lines += [
                "---",
                "",
                f"## {crop.title}",
                "",
                f"![h:480px]({crop_url_for(data.slug, crop.rel_path)})",
                "",
            ]
            if crop.description:
                lines += [f"<small>{crop.description}</small>", ""]
            lines.append(f"<small>From page {crop.source_ref.page}, region {crop.source_ref.region_id}.</small>")

        if data.caveats:
            lines += ["---", "", "## Caveats", ""]
            for c in data.caveats:
                lines.append(f"- {c}")

        return "\n".join(lines) + "\n"


# ── small pymupdf helpers ──────────────────────────────────────────────────


def _text(page, xy, s, size=10, font="helv"):
    page.insert_text(xy, s, fontsize=size, fontname=font)


def _box(page, rect, s, size=10, font="helv"):
    page.insert_textbox(rect, s, fontsize=size, fontname=font, align=0)


__all__ = ["PymupdfSynopsisRenderer", "MarpSynopsisRenderer", "CropPathResolver"]
