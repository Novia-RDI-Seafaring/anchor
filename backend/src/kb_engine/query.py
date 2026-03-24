# pyright: reportUnknownMemberType=false
from typing import Any, cast
from urllib.parse import urlencode

from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from ketju.rag.llama_index.query.simple import SimpleLlamaIndexQueryHandler
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


def _to_pdf_search_response(source_nodes: list[NodeWithScore]) -> PdfSearchResponse:
    citations: list[PdfCitation] = []
    for source in source_nodes:
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

    answer = ""
    if source_nodes:
        first_text = str(getattr(source_nodes[0].node, "text", "") or "").strip()
        answer = first_text[:500]

    return PdfSearchResponse(answer=answer, citations=citations)


class QueryHandler(SimpleLlamaIndexQueryHandler):
    """App-specific Ketju query handler for retrieval and PDF-aware responses."""

    def _retriever_kwargs(
        self,
        document_id: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        from llama_index.core.vector_stores import (
            FilterCondition,
            FilterOperator,
            MetadataFilter,
            MetadataFilters,
        )

        retriever_kwargs: dict[str, Any] = {"similarity_top_k": top_k}
        if document_id:
            retriever_kwargs["filters"] = MetadataFilters(
                filters=[MetadataFilter(key="document_id", operator=FilterOperator.EQ, value=document_id)]
            )
        elif document_ids:
            retriever_kwargs["filters"] = MetadataFilters(
                filters=[
                    MetadataFilter(key="document_id", operator=FilterOperator.EQ, value=value)
                    for value in dict.fromkeys(document_ids)
                ],
                condition=FilterCondition.OR,
            )
        return retriever_kwargs

    def retrieve(
        self,
        rag: LlamaIndexRag,
        question: str,
        document_id: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> list[NodeWithScore]:
        retriever = rag.vector_index.as_retriever(
            **self._retriever_kwargs(document_id=document_id, document_ids=document_ids, top_k=top_k)
        )
        retrieved = retriever.retrieve(question)
        source_nodes = [node for node in retrieved if isinstance(node, NodeWithScore)]
        trace: list[dict[str, Any]] = []
        for rank, node_with_score in enumerate(source_nodes, start=1):
            metadata = _node_metadata(node_with_score)
            origin = metadata.get("origin", {})
            filename = ""
            if isinstance(origin, dict):
                filename = str(cast(Any, origin.get("filename", "")) or "")
            location = _extract_location(metadata)
            trace.append(
                {
                    "rank": rank,
                    "filename": filename or metadata.get("filename") or metadata.get("file_name"),
                    "page": location.page if location is not None else None,
                    "score": float(node_with_score.score or 0.0),
                }
            )
        if trace:
            logger.info("Top retrieved chunks: %s", trace)
        return source_nodes

    def query(
        self,
        rag: LlamaIndexRag,
        question: str,
        document_id: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> PdfSearchResponse:
        source_nodes = self.retrieve(
            rag,
            question,
            document_id=document_id,
            document_ids=document_ids,
            top_k=top_k,
        )
        return _to_pdf_search_response(source_nodes)

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
