# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from __future__ import annotations

import io
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Sequence

from PIL import Image, ImageDraw
from llama_index.core.base.response.schema import NodeWithScore
import pypdfium2 as pdfium  # type: ignore[reportMissingTypeStubs]

logger = getLogger(__name__)


def _iter_provs(node: NodeWithScore) -> List[Dict[str, Any]]:
    metadata = node.metadata or {}
    doc_items_raw = metadata.get("doc_items", [])
    if not isinstance(doc_items_raw, list):
        return []

    provs: List[Dict[str, Any]] = []
    for item_raw in doc_items_raw:
        if not isinstance(item_raw, dict):
            continue
        prov_items_raw = item_raw.get("prov", [])
        if not isinstance(prov_items_raw, list):
            continue
        for prov_raw in prov_items_raw:
            if isinstance(prov_raw, dict):
                provs.append(prov_raw)
    return provs


def _docling_bbox_to_image_coords(
    bbox: Dict[str, Any],
    page_w: float,
    page_h: float,
    image_w: int,
    image_h: int,
) -> tuple[float, float, float, float]:
    l = float(bbox.get("l", 0.0))
    r = float(bbox.get("r", 0.0))
    t = float(bbox.get("t", 0.0))
    b = float(bbox.get("b", 0.0))

    x_left_pdf, x_right_pdf = sorted((l, r))
    y_top_pdf, y_bottom_pdf = sorted((t, b), reverse=True)

    scale_x = image_w / page_w if page_w else 1.0
    scale_y = image_h / page_h if page_h else 1.0

    coord_origin = str(bbox.get("coord_origin", "BOTTOMLEFT")).upper()
    if coord_origin == "BOTTOMLEFT":
        y_top = (page_h - y_top_pdf) * scale_y
        y_bottom = (page_h - y_bottom_pdf) * scale_y
    else:
        y_top = y_top_pdf * scale_y
        y_bottom = y_bottom_pdf * scale_y

    x_left = x_left_pdf * scale_x
    x_right = x_right_pdf * scale_x

    x0, x1 = sorted((max(0.0, x_left), min(float(image_w), x_right)))
    y0, y1 = sorted((max(0.0, y_top), min(float(image_h), y_bottom)))
    return x0, y0, x1, y1


def _draw_boxes(
    image: Image.Image,
    page: Any,
    box_specs: Sequence[Dict[str, Any]],
) -> None:
    if not box_specs:
        return
    page_w, page_h = page.get_size()
    draw = ImageDraw.Draw(image, "RGBA")
    for spec in box_specs:
        bbox = spec.get("bbox")
        if not isinstance(bbox, dict):
            continue
        score = float(spec.get("_score", 1.0))
        score = max(0.0, min(1.0, score))

        # Higher score => stronger visual emphasis.
        fill_alpha = int(30 + score * 140)      # 30..170
        outline_alpha = int(120 + score * 135)  # 120..255
        width = max(2, int(2 + score * 4))      # 2..6

        x0, y0, x1, y1 = _docling_bbox_to_image_coords(
            bbox=bbox,
            page_w=page_w,
            page_h=page_h,
            image_w=image.width,
            image_h=image.height,
        )
        draw.rectangle(
            [x0, y0, x1, y1],
            outline=(255, 0, 0, outline_alpha),
            fill=(255, 0, 0, fill_alpha),
            width=width,
        )


def _render_page_with_provs(
    pdf_path: Path,
    page_nr: int,
    box_specs: Sequence[Dict[str, Any]],
    scale: int = 2,
) -> Image.Image:
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            page = pdf[page_nr - 1]  # Docling page numbering is 1-indexed.
            bitmap: Any = page.render(scale=scale)
            image: Image.Image = bitmap.to_pil()
            _draw_boxes(image=image, page=page, box_specs=box_specs)
            return image
        finally:
            pdf.close()
    except Exception:
        logger.exception("Failed to render highlighted PDF page, falling back to .png")
        fallback = pdf_path.with_suffix(".png")
        if fallback.exists():
            return Image.open(fallback)
        raise


def _node_score(node: NodeWithScore) -> float:
    score_raw = getattr(node, "score", 1.0)
    if score_raw is None:
        return 1.0
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, score))


def _render_node_image(
    self: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
) -> Image.Image:
    file = Path(str(self.metadata.get("filepath")))
    provs = _iter_provs(self)

    if page_no is not None:
        target_page = page_no
    else:
        target_page = int(provs[0].get("page_no", 1)) if provs else 1

    score = _node_score(self) if relevance_weighted else 1.0
    page_specs = []
    for prov in provs:
        if int(prov.get("page_no", target_page)) != target_page:
            continue
        spec = dict(prov)
        spec["_score"] = score
        page_specs.append(spec)

    return _render_page_with_provs(pdf_path=file, page_nr=target_page, box_specs=page_specs, scale=scale)


def render_nodes_to_image(
    nodes: Sequence[NodeWithScore],
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
) -> Image.Image:
    if not nodes:
        raise ValueError("nodes must contain at least one NodeWithScore")

    first = nodes[0]
    file = Path(str(first.metadata.get("filepath")))
    all_specs: List[Dict[str, Any]] = []
    for node in nodes:
        score = _node_score(node) if relevance_weighted else 1.0
        for prov in _iter_provs(node):
            spec = dict(prov)
            spec["_score"] = score
            all_specs.append(spec)

    if page_no is not None:
        target_page = page_no
    else:
        target_page = int(all_specs[0].get("page_no", 1)) if all_specs else 1

    page_specs = [s for s in all_specs if int(s.get("page_no", target_page)) == target_page]
    return _render_page_with_provs(pdf_path=file, page_nr=target_page, box_specs=page_specs, scale=scale)


def render_nodes_to_image_bytes(
    nodes: Sequence[NodeWithScore],
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
) -> bytes:
    image = render_nodes_to_image(
        nodes=nodes,
        scale=scale,
        page_no=page_no,
        relevance_weighted=relevance_weighted,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _to_image(
    self: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
) -> Image.Image:
    return _render_node_image(self, scale=scale, page_no=page_no, relevance_weighted=relevance_weighted)


def _to_image_bytes(
    self: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
) -> bytes:
    image = _render_node_image(
        self,
        scale=scale,
        page_no=page_no,
        relevance_weighted=relevance_weighted,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


NodeWithScore.to_image = _to_image  # type: ignore[attr-defined]
NodeWithScore.to_image_bytes = _to_image_bytes  # type: ignore[attr-defined]
