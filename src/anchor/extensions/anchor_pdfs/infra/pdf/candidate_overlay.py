"""Diagnostic candidate boxes in the raster viewer's top-left coordinate map."""
from __future__ import annotations

import math
from typing import Any

_COLORS = {
    "title": (0.52, 0.21, 0.69),
    "section_header": (0.52, 0.21, 0.69),
    "text": (0.13, 0.36, 0.78),
    "paragraph": (0.13, 0.36, 0.78),
    "list_item": (0.13, 0.36, 0.78),
    "table": (0.12, 0.54, 0.32),
    "picture": (0.83, 0.35, 0.06),
    "caption": (0.39, 0.52, 0.08),
    "formula": (0.72, 0.19, 0.29),
    "code": (0.22, 0.43, 0.52),
}
_DEFAULT_COLOR = (0.35, 0.35, 0.35)
_FONT_SIZE = 11


def _bbox(candidate: dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = candidate.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in bbox
    ):
        return None
    left, top, right, bottom = bbox
    return min(left, right), min(top, bottom), max(left, right), max(top, bottom)


def _label(candidate: dict[str, Any]) -> str:
    text = f"{candidate.get('id', '?')} {candidate.get('label', 'unknown')}"
    order = candidate.get("reading_order")
    if isinstance(order, int) and not isinstance(order, bool) and order >= 0:
        text += f" order={order}"
    return text[:160]


def render_candidate_overlay(
    page_image: bytes,
    candidates: list[dict[str, Any]],
    *,
    page_size: tuple[float, float] | None,
) -> bytes:
    import pymupdf

    pixmap = pymupdf.Pixmap(page_image)
    width, height = pixmap.width, pixmap.height
    with pymupdf.open() as document:
        page = document.new_page(width=width, height=height)
        page.insert_image(page.rect, stream=page_image)
        warnings: list[str] = []
        if page_size is None:
            warnings.append("Page dimensions unknown; candidate boxes cannot be mapped.")
        else:
            scale_x, scale_y = width / page_size[0], height / page_size[1]
            for candidate in candidates:
                bbox = _bbox(candidate)
                if bbox is None:
                    warnings.append(f"{_label(candidate)}: no usable bbox")
                    continue
                left, top, right, bottom = bbox
                rect = pymupdf.Rect(
                    left * scale_x, top * scale_y, right * scale_x, bottom * scale_y,
                )
                color = _COLORS.get(candidate.get("label"), _DEFAULT_COLOR)
                page.draw_rect(rect, color=color, fill=color, fill_opacity=0.08, width=2)
                label = _label(candidate)
                label_width = min(pymupdf.get_text_length(label, fontsize=_FONT_SIZE) + 6, width)
                label_x = min(max(0, rect.x0), max(0, width - label_width))
                label_y = rect.y0 - 3 if rect.y0 >= _FONT_SIZE + 6 else rect.y0 + _FONT_SIZE + 3
                label_y = min(max(_FONT_SIZE + 3, label_y), height - 3)
                page.draw_rect(
                    pymupdf.Rect(label_x, label_y - _FONT_SIZE - 2, label_x + label_width, label_y + 3),
                    color=color, fill=(1, 1, 1), width=0.5,
                )
                page.insert_text((label_x + 3, label_y), label, fontsize=_FONT_SIZE, color=color)
        for row, warning in enumerate(warnings):
            y = (row + 1) * (_FONT_SIZE + 5)
            page.draw_rect(pymupdf.Rect(0, y - _FONT_SIZE - 2, width, y + 3), fill=(1, 1, 1))
            page.insert_text((3, y), warning, fontsize=_FONT_SIZE, color=(0.7, 0.15, 0.1))
        return page.get_pixmap(dpi=72).tobytes("png")
