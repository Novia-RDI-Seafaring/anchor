# pyright: reportUnknownMemberType=false
from typing import Any, cast
from urllib.parse import urlencode

from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from llama_index.core.base.response.schema import NodeWithScore
from logging import getLogger

from .patches import NodeWithScore
from .search_models import (
    PdfBBox,
    PdfCitation,
    PdfCitationDocument,
    PdfCitationLocation,
    PdfCitationRender,
    PdfSearchResponse,
)

logger = getLogger(__name__)


def _node_metadata(node_with_score: NodeWithScore) -> dict[str, Any]:
    node = node_with_score.node
    metadata = getattr(node, "metadata", None)
    if isinstance(metadata, dict):
        return cast(dict[str, Any], metadata)
    extra_info = getattr(node, "extra_info", None)
    if isinstance(extra_info, dict):
        return cast(dict[str, Any], extra_info)
    return {}


def _first_doc_item(metadata: dict[str, Any]) -> dict[str, Any]:
    doc_items_raw = metadata.get("doc_items", [])
    if not isinstance(doc_items_raw, list) or not doc_items_raw:
        return cast(dict[str, Any], {})
    first = cast(Any, doc_items_raw[0])
    return cast(dict[str, Any], first) if isinstance(first, dict) else cast(dict[str, Any], {})


def _extract_location(metadata: dict[str, Any]) -> PdfCitationLocation | None:
    doc_item = _first_doc_item(metadata)
    prov_raw = doc_item.get("prov", [])
    if not isinstance(prov_raw, list) or not prov_raw:
        return None

    first_prov = cast(Any, prov_raw[0])
    if not isinstance(first_prov, dict):
        return None

    page_raw = cast(Any, first_prov.get("page_no", 1))
    try:
        page = int(page_raw)
    except (TypeError, ValueError):
        page = 1

    bbox_raw = cast(Any, first_prov.get("bbox"))
    bbox: PdfBBox | None = None
    if isinstance(bbox_raw, dict):
        try:
            l_raw = cast(Any, bbox_raw.get("l", 0.0))
            t_raw = cast(Any, bbox_raw.get("t", 0.0))
            r_raw = cast(Any, bbox_raw.get("r", 0.0))
            b_raw = cast(Any, bbox_raw.get("b", 0.0))
            coord_raw = cast(Any, bbox_raw.get("coord_origin", "BOTTOMLEFT"))
            bbox = PdfBBox(l=float(l_raw), t=float(t_raw), r=float(r_raw), b=float(b_raw), coord_origin=str(coord_raw))
        except (TypeError, ValueError):
            bbox = None

    return PdfCitationLocation(page=page, bbox=bbox)


def _build_render_urls(filename: str, location: PdfCitationLocation | None) -> PdfCitationRender:
    image_params: dict[str, Any] = {"filename": filename}
    if location is not None:
        image_params["page_no"] = location.page
        if location.bbox is not None:
            image_params.update(
                {
                    "bbox_l": location.bbox.l,
                    "bbox_t": location.bbox.t,
                    "bbox_r": location.bbox.r,
                    "bbox_b": location.bbox.b,
                    "bbox_coord_origin": location.bbox.coord_origin,
                }
            )
    image_url = f"/api/documents/pdf/screenshot?{urlencode(image_params, doseq=True)}"
    pdf_url = f"/api/documents/pdf/serve?{urlencode({'filename': filename})}"
    return PdfCitationRender(image_url=image_url, pdf_url=pdf_url)


def _to_pdf_search_response(result: Any) -> PdfSearchResponse:
    answer = str(getattr(result, "response", "") or "")
    source_nodes = getattr(result, "source_nodes", [])
    if not isinstance(source_nodes, list):
        source_nodes = []

    citations: list[PdfCitation] = []
    for source in source_nodes:
        if not isinstance(source, NodeWithScore):
            continue
        metadata = _node_metadata(source)
        origin = metadata.get("origin", {})
        if not isinstance(origin, dict):
            origin = {}
        filename_raw = cast(Any, origin.get("filename", ""))
        filename = str(filename_raw or "")
        if not filename:
            continue

        node_id = str(getattr(source.node, "node_id", None) or getattr(source.node, "id_", ""))
        text = str(getattr(source.node, "text", "") or "")
        score = float(source.score or 0.0)
        label = _first_doc_item(metadata).get("label", "text")
        headings_raw = metadata.get("headings", [])
        headings: list[str] = []
        if isinstance(headings_raw, list):
            for item in cast(list[Any], headings_raw):
                if isinstance(item, str):
                    headings.append(item)
        location = _extract_location(metadata)

        citations.append(
            PdfCitation(
                id=node_id,
                score=score,
                text=text,
                type=str(label),
                headings=headings,
                document=PdfCitationDocument(
                    filename=filename,
                    mime_type=(
                        str(cast(Any, origin.get("mimetype")))
                        if origin.get("mimetype") is not None
                        else None
                    ),
                ),
                location=location,
                render=_build_render_urls(filename=filename, location=location),
            )
        )

    return PdfSearchResponse(answer=answer, citations=citations)


class QueryHandler:
    def query(self, rag: LlamaIndexRag, question: str, **kwargs: Any) -> PdfSearchResponse:
        query_engine: Any = rag.vector_index.as_query_engine()
        result = query_engine.query(question)
        logger.info("Result generated with %d source nodes", len(getattr(result, "source_nodes", []) or []))
        return _to_pdf_search_response(result)

    def get_page_image(self, node: NodeWithScore) -> bytes:
        to_image_bytes = getattr(node, "to_image_bytes", None)
        if callable(to_image_bytes):
            return to_image_bytes()

        to_image = getattr(node, "to_image", None)
        if callable(to_image):
            image = to_image()
            from io import BytesIO

            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()

        raise AttributeError("NodeWithScore image patch is unavailable")
