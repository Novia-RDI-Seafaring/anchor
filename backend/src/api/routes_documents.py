"""Document management API routes."""
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

from src.knowledge_base.service import get_document_service
from .schemas import URLRequest

router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    preserve_images: Optional[str] = Form("true"),
    preserve_tables: Optional[str] = Form("true"),
    enable_ocr: Optional[str] = Form("false"),
    table_mode: Optional[str] = Form("fast")
):
    """Upload and process a document via DocumentService."""
    try:
        preserve_images_bool = preserve_images.lower() == "true"
        preserve_tables_bool = preserve_tables.lower() == "true"
        enable_ocr_bool = enable_ocr.lower() == "true"
        
        if table_mode not in ["fast", "accurate"]:
            raise HTTPException(status_code=400, detail="table_mode must be 'fast' or 'accurate'")

        content = await file.read()
        service = await get_document_service()
        result = await service.upload_file(
            filename=file.filename,
            content=content,
            preserve_images=preserve_images_bool,
            preserve_tables=preserve_tables_bool,
            enable_ocr=enable_ocr_bool,
            table_mode=table_mode,
        )

        return {"success": True, "document": result}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/url")
async def add_url(request: URLRequest):
    """Add a URL to the knowledge base via DocumentService."""
    try:
        service = await get_document_service()
        result = await service.upload_url(request.url)
        return {"success": True, "document": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_documents():
    """List all documents in the knowledge base."""
    service = await get_document_service()
    docs = await service.list_documents()
    return {"success": True, "documents": docs}

@router.post("/documents/reingest")
async def reingest_documents():
    """Re-process all documents in the knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reingest_all()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/reset")
async def reset_knowledge_base():
    """Reset (clear) the entire knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reset_knowledge_base()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a specific document."""
    try:
        service = await get_document_service()
        success = await service.delete_document(document_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats():
    """Get knowledge base statistics."""
    try:
        service = await get_document_service()
        stats = await service.get_stats()
        return {"success": True, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/gold/{filename:path}")
async def get_gold_data(filename: str):
    """Get gold-layer pre-extracted product data for a document."""
    from src.agent.tools.product_data import _find_by_filename
    data = _find_by_filename(filename)
    if not data:
        raise HTTPException(status_code=404, detail="No gold data for this document")
    return data
