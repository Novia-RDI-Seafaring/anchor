# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
from __future__ import annotations

import io
import time
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Sequence

from PIL import Image, ImageDraw
from llama_index.core.base.response.schema import NodeWithScore
import pypdfium2 as pdfium  # type: ignore[reportMissingTypeStubs]

logger = getLogger(__name__)


def _open_pdf_document(pdf_path: Path) -> pdfium.PdfDocument:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return pdfium.PdfDocument(str(pdf_path))
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.05)
                continue
    try:
        return pdfium.PdfDocument(pdf_path.read_bytes())
    except Exception:
        if last_error is not None:
            raise last_error
        raise


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


def _phrase_box_specs(page: Any, phrases: Sequence[str], max_matches_per_phrase: int = 10) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    if not phrases:
        return specs

    text_page = page.get_textpage()
    try:
        for phrase in phrases:
            phrase_clean = phrase.strip()
            if not phrase_clean:
                continue

            searcher = text_page.search(phrase_clean, match_case=False)
            matches = 0
            while True:
                found = searcher.get_next()
                if found is None:
                    break
                start_idx, count = found
                rect_count = text_page.count_rects(start_idx, count)
                for i in range(rect_count):
                    left, bottom, right, top = text_page.get_rect(i)
                    specs.append(
                        {
                            "bbox": {
                                "l": float(left),
                                "r": float(right),
                                "t": float(top),
                                "b": float(bottom),
                                "coord_origin": "BOTTOMLEFT",
                            },
                            "_score": 1.0,
                            "_phrase": phrase_clean,
                            "_style": "underline",
                        }
                    )
                matches += 1
                if matches >= max_matches_per_phrase:
                    break
    finally:
        text_page.close()

    return specs


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

        fill_alpha = int(12 + score * 28)
        outline_alpha = int(180 + score * 55)
        width = max(2, int(2 + score * 2))

        x0, y0, x1, y1 = _docling_bbox_to_image_coords(
            bbox=bbox,
            page_w=page_w,
            page_h=page_h,
            image_w=image.width,
            image_h=image.height,
        )
        style = str(spec.get("_style", "box"))
        if style == "underline":
            draw.rectangle(
                [x0, y0, x1, y1],
                outline=None,
                fill=(252, 211, 77, min(72, fill_alpha + 20)),
                width=1,
            )
            underline_y = y1
            draw.line(
                [(x0, underline_y), (x1, underline_y)],
                fill=(245, 158, 11, outline_alpha),
                width=max(2, width),
            )
        else:
            draw.rectangle(
                [x0, y0, x1, y1],
                outline=(245, 158, 11, outline_alpha),
                fill=(251, 191, 36, min(48, fill_alpha)),
                width=width,
            )


def _crop_image_by_bbox(
    image: Image.Image,
    page_w: float,
    page_h: float,
    crop_bbox: Dict[str, Any] | None,
) -> Image.Image:
    if not crop_bbox:
        return image

    x0, y0, x1, y1 = _docling_bbox_to_image_coords(
        bbox=crop_bbox,
        page_w=page_w,
        page_h=page_h,
        image_w=image.width,
        image_h=image.height,
    )
    left = int(max(0, min(image.width - 1, round(x0))))
    top = int(max(0, min(image.height - 1, round(y0))))
    right = int(max(left + 1, min(image.width, round(x1))))
    bottom = int(max(top + 1, min(image.height, round(y1))))
    return image.crop((left, top, right, bottom))


def _render_page_with_provs(
    pdf_path: Path,
    page_nr: int,
    box_specs: Sequence[Dict[str, Any]],
    phrases: Sequence[str] | None = None,
    crop_bbox: Dict[str, Any] | None = None,
    scale: int = 2,
) -> Image.Image:
    try:
        pdf = _open_pdf_document(pdf_path)
        try:
            page_count = len(pdf)
            if page_count <= 0:
                raise ValueError("PDF has no pages")
            safe_page_index = max(0, min(page_nr - 1, page_count - 1))
            page = pdf[safe_page_index]
            bitmap: Any = page.render(scale=scale)
            image: Image.Image = bitmap.to_pil()
            merged_specs = list(box_specs)
            if phrases:
                merged_specs.extend(_phrase_box_specs(page=page, phrases=phrases))
            _draw_boxes(image=image, page=page, box_specs=merged_specs)
            page_w, page_h = page.get_size()
            return _crop_image_by_bbox(image=image, page_w=page_w, page_h=page_h, crop_bbox=crop_bbox)
        finally:
            pdf.close()
    except Exception as exc:
        fallback = pdf_path.with_suffix(".png")
        if fallback.exists():
            logger.warning(
                "Failed to render PDF preview for %s page %s (%s); using PNG fallback",
                pdf_path.name,
                page_nr,
                exc,
            )
            return Image.open(fallback).copy()
        logger.exception(
            "Failed to render PDF preview for %s page %s",
            pdf_path.name,
            page_nr,
        )
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


def render_node_to_image(
    node: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
    phrases: Sequence[str] | None = None,
    use_metadata_phrases: bool = True,
) -> Image.Image:
    file = Path(str(node.metadata.get("filepath")))
    provs = _iter_provs(node)

    if page_no is not None:
        target_page = page_no
    else:
        target_page = int(provs[0].get("page_no", 1)) if provs else 1

    score = _node_score(node) if relevance_weighted else 1.0
    page_specs = []
    for prov in provs:
        if int(prov.get("page_no", target_page)) != target_page:
            continue
        spec = dict(prov)
        spec["_score"] = score
        page_specs.append(spec)

    phrase_list: List[str] = []
    if phrases:
        phrase_list.extend([p for p in phrases if p])
    if use_metadata_phrases:
        meta_phrases = node.metadata.get("highlight_phrases", [])
        if isinstance(meta_phrases, list):
            for item in meta_phrases:
                if isinstance(item, str) and item.strip():
                    phrase_list.append(item.strip())

    return _render_page_with_provs(
        pdf_path=file,
        page_nr=target_page,
        box_specs=page_specs,
        phrases=phrase_list,
        crop_bbox=None,
        scale=scale,
    )


def render_node_to_image_bytes(
    node: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
    phrases: Sequence[str] | None = None,
    use_metadata_phrases: bool = True,
) -> bytes:
    image = render_node_to_image(
        node=node,
        scale=scale,
        page_no=page_no,
        relevance_weighted=relevance_weighted,
        phrases=phrases,
        use_metadata_phrases=use_metadata_phrases,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_nodes_to_image(
    nodes: Sequence[NodeWithScore],
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
    phrases: Sequence[str] | None = None,
    use_metadata_phrases: bool = True,
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
    phrase_list: List[str] = []
    if phrases:
        phrase_list.extend([p for p in phrases if p])
    if use_metadata_phrases:
        for node in nodes:
            meta_phrases = node.metadata.get("highlight_phrases", [])
            if isinstance(meta_phrases, list):
                for item in meta_phrases:
                    if isinstance(item, str) and item.strip():
                        phrase_list.append(item.strip())

    return _render_page_with_provs(
        pdf_path=file,
        page_nr=target_page,
        box_specs=page_specs,
        phrases=phrase_list,
        crop_bbox=None,
        scale=scale,
    )


def render_nodes_to_image_bytes(
    nodes: Sequence[NodeWithScore],
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
    phrases: Sequence[str] | None = None,
    use_metadata_phrases: bool = True,
) -> bytes:
    image = render_nodes_to_image(
        nodes=nodes,
        scale=scale,
        page_no=page_no,
        relevance_weighted=relevance_weighted,
        phrases=phrases,
        use_metadata_phrases=use_metadata_phrases,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_pdf_page_to_image(
    pdf_path: Path | str,
    page_no: int = 1,
    phrases: Sequence[str] | None = None,
    box_specs: Sequence[Dict[str, Any]] | None = None,
    crop_bbox: Dict[str, Any] | None = None,
    scale: int = 2,
) -> Image.Image:
    return _render_page_with_provs(
        pdf_path=Path(pdf_path),
        page_nr=page_no,
        box_specs=list(box_specs or []),
        phrases=phrases,
        crop_bbox=crop_bbox,
        scale=scale,
    )


def render_pdf_page_to_image_bytes(
    pdf_path: Path | str,
    page_no: int = 1,
    phrases: Sequence[str] | None = None,
    box_specs: Sequence[Dict[str, Any]] | None = None,
    crop_bbox: Dict[str, Any] | None = None,
    scale: int = 2,
) -> bytes:
    image = render_pdf_page_to_image(
        pdf_path=pdf_path,
        page_no=page_no,
        phrases=phrases,
        box_specs=box_specs,
        crop_bbox=crop_bbox,
        scale=scale,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
