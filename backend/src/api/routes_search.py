"""Search API routes."""
from fastapi import APIRouter, HTTPException

from src.knowledge_base.service import get_document_service
from .schemas import SearchRequest

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search")
async def search_knowledge_base(request: SearchRequest):
    """Search the knowledge base, optionally filtered by document."""
    try:
        raise NotImplementedError("search_knowledge_base is not implemented")
        service = await get_document_service()
        results = await service.search(request.query, request.top_k, request.document_id)
        first_provenance = (results[0].get("provenance") if results else {}) or {}
        retrieval = first_provenance.get("pipeline", {}).get("retrieval", {})
        trace = first_provenance.get("trace", {})

        return {
            "success": True,
            "results": results,
            "retrieval_id": retrieval.get("retrieval_id"),
            "trace_id": trace.get("trace_id"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
