# pyright: reportUnknownMemberType=false
from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from llama_index.core.base.response.schema import RESPONSE_TYPE, NodeWithScore

from logging import getLogger

from . import patch as _node_with_score_patch
del _node_with_score_patch

logger = getLogger(__name__)

from typing import Dict, Any
class QueryHandler:
    def query(self, rag: LlamaIndexRag, question: str, **kwargs: Dict[str, Any]) -> RESPONSE_TYPE: 
        
        query_engine: Any = rag.vector_index.as_query_engine()
        result =  query_engine.query(question)
        logger.info(f"Result: {result}")
        return result

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


"""
add this later to filter per doc id..


def query(self, question: str, similarity_top_k: int = 5, document_id: str = None) -> RESPONSE_TYPE:
    filename = kwargs.get("filename", None)
    filters = None
    logger.info(f"Query: {question}")
    
    if filename is not None:
        logger.info(f"Filename: {filename}")
        filters = MetadataFilters(filters=[MetadataFilter(key="filename", value=filename, operator="EQ")])

    doc_ids = kwargs.get("doc_ids", [])
    if doc_ids:
        doc_ids = [doc_id]
    from llama_index.core.vector_stores.types import  MetadataFilters, MetadataFilter
    retriever = VectorIndexRetriever(
        index=rag.vector_store_index,
        filters=filters,
        doc_ids=doc_ids if doc_ids else None,
        similarity_top_k=kwargs.get("top_k") if kwargs.get("top_k") else 5,
    )
    query_engine = RetrieverQueryEngine(
        retriever=retriever,
    )
    



"""