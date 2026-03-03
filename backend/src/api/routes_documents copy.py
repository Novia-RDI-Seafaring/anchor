"""Document management API routes."""
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

from src.knowledge_base.service import get_document_service
from src.knowledge_base.vector_store import get_vector_store
from .schemas import URLRequest, PageImagesRequest

router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    preserve_images: Optional[str] = Form("true"),
    preserve_tables: Optional[str] = Form("true"),
    enable_ocr: Optional[str] = Form("false"),
    table_mode: Optional[str] = Form("fast")
):
    """Upload and process a document with configurable processing options."""
    try:
        # Convert string form values to appropriate types
        preserve_images_bool = preserve_images.lower() == "true"
        preserve_tables_bool = preserve_tables.lower() == "true"
        enable_ocr_bool = enable_ocr.lower() == "true"
        
        # Validate table_mode
        if table_mode not in ["fast", "accurate"]:
            raise HTTPException(status_code=400, detail="table_mode must be 'fast' or 'accurate'")
        
        content = await file.read()
        service = await get_document_service()
        result = await service.upload_file(
            file.filename,
            content,
            preserve_images=preserve_images_bool,
            preserve_tables=preserve_tables_bool,
            enable_ocr=enable_ocr_bool,
            table_mode=table_mode
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
    """Add a URL to the knowledge base."""
    try:
        service = await get_document_service()
        result = await service.upload_url(request.url)
        return {"success": True, "document": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_documents():
    """List all documents in the knowledge base."""
    try:
        service = await get_document_service()
        documents = await service.list_documents()
        return {"success": True, "documents": documents}
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


@router.get("/stats")
async def get_stats():
    """Get knowledge base statistics."""
    try:
        service = await get_document_service()
        stats = await service.get_stats()
        return {"success": True, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== Page Images =====

@router.get("/documents/{document_id}/pages/{page_number}/image")
async def get_page_image(document_id: str, page_number: int):
    """Get a page image as Base64."""
    try:
        vector_store = await get_vector_store()
        image_data = await vector_store.get_page_image(document_id, page_number)
        if not image_data:
            raise HTTPException(status_code=404, detail="Page image not found")
        return {"success": True, **image_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{document_id}/pages/images")
async def get_page_images(document_id: str, request: PageImagesRequest):
    """Get multiple page images as Base64."""
    try:
        vector_store = await get_vector_store()
        images = await vector_store.get_page_images_for_pages(document_id, request.page_numbers)
        return {"success": True, "images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chunks/{chunk_id}/pages/images")
async def get_page_images_by_chunk(chunk_id: int):
    """Get page images for a specific chunk by chunk ID."""
    try:
        vector_store = await get_vector_store()
        images = await vector_store.get_page_images_by_chunk_id(chunk_id)
        return {"success": True, "images": images, "count": len(images)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
