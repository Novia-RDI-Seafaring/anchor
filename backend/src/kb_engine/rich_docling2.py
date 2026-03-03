from ketju.rag.llama_index.variants.simple_docling_full_ctx import SimpleDoclingFullCtxRag
from ketju.rag.base import BaseRAG
from pathlib import Path
_rag_handler = None

from llama_index.core import VectorStoreIndex, get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from llama_index.core.base.response.schema import RESPONSE_TYPE
from ketju.rag.llama_index.ingestion.simple_docling_full_ctx import DoclingFullCtxIngestionHandler

from logging import getLogger
logger = getLogger(__name__)

from typing import Dict, Any
class QueryHandler:
    def query(self, rag: LlamaIndexRag, question: str, **kwargs: Dict[str, Any]) -> RESPONSE_TYPE: 
        #def query(self, question: str, similarity_top_k: int = 5, document_id: str = None) -> RESPONSE_TYPE:
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
        result =  query_engine.query(question)
        logger.info(f"Result: {result}")
        return result

def get_rag_handler() -> BaseRAG: 
    global _rag_handler
    if _rag_handler is None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            _rag_handler = SimpleDoclingFullCtxRag(
                name="anchor_rag",
                persist_dir=Path(tmpdir),
                query_handler=QueryHandler()
            )
    return _rag_handler