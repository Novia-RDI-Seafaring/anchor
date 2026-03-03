"""Search API routes."""
from fastapi import APIRouter, HTTPException

from src.knowledge_base.service import get_document_service
from src.knowledge_base.doc_service2 import get_document_service2
from .schemas import SearchRequest

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search")
async def search_knowledge_base(request: SearchRequest):
    """Search the knowledge base, optionally filtered by document."""
    try:
        service = await get_document_service2()
        results = await service.query(request.query, request.top_k, request.document_id)
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
