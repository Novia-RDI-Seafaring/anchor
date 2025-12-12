from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from src.agent import agent, StateDeps, AppState
from src.config import get_settings
from src.document_service import get_document_service
from src.vector_store import get_vector_store
from typing import List
from src.active_document import get_active_document_id, set_active_document_id


# Create main FastAPI app
app = FastAPI(title="Knowledge Base API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from src.request_context import set_current_model_id

@app.middleware("http")
async def model_context_middleware(request: Request, call_next):
    # Extract 'model' query param
    model_param = request.query_params.get("model")
    if model_param:
        # print(f"Middleware: Setting model to {model_param}")
        set_current_model_id(model_param)
        
    response = await call_next(request)
    return response

# Mount the AG-UI agent
ag_ui_app = agent.to_ag_ui(deps=StateDeps(AppState()))
app.mount("/agent", ag_ui_app)


# ===== Document API Endpoints =====

class URLRequest(BaseModel):
    url: str

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    document_id: Optional[str] = None


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a document."""
    try:
        content = await file.read()
        service = await get_document_service()
        result = await service.upload_file(file.filename, content)
        return {"success": True, "document": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documents/url")
async def add_url(request: URLRequest):
    """Add a URL to the knowledge base."""
    try:
        service = await get_document_service()
        result = await service.upload_url(request.url)
        return {"success": True, "document": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
async def list_documents():
    """List all documents in the knowledge base."""
    try:
        service = await get_document_service()
        documents = await service.list_documents()
        return {"success": True, "documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{document_id}")
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


@app.post("/api/documents/reingest")
async def reingest_documents():
    """Re-process all documents in the knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reingest_all()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/reset")
async def reset_knowledge_base():
    """Reset (clear) the entire knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reset_knowledge_base()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
async def search_knowledge_base(request: SearchRequest):
    """Search the knowledge base, optionally filtered by document."""
    try:
        service = await get_document_service()
        results = await service.search(request.query, request.top_k, request.document_id)
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get knowledge base statistics."""
    try:
        service = await get_document_service()
        stats = await service.get_stats()
        return {"success": True, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== Page Images API =====

@app.get("/api/documents/{document_id}/pages/{page_number}/image")
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


class PageImagesRequest(BaseModel):
    page_numbers: List[int]


@app.post("/api/documents/{document_id}/pages/images")
async def get_page_images(document_id: str, request: PageImagesRequest):
    """Get multiple page images as Base64."""
    try:
        vector_store = await get_vector_store()
        images = await vector_store.get_page_images_for_pages(document_id, request.page_numbers)
        return {"success": True, "images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chunks/{chunk_id}/pages/images")
async def get_page_images_by_chunk(chunk_id: int):
    """Get page images for a specific chunk by chunk ID."""
    try:
        vector_store = await get_vector_store()
        images = await vector_store.get_page_images_by_chunk_id(chunk_id)
        return {"success": True, "images": images, "count": len(images)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== Active Document Filter =====

@app.get("/api/active-document")
async def get_active_document():
    """Get the currently active document filter."""
    return {"document_id": get_active_document_id()}

@app.post("/api/active-document")
async def set_active_document(document_id: Optional[str] = None):
    """Set the active document filter for RAG queries."""
    set_active_document_id(document_id)
    return {"success": True, "document_id": get_active_document_id()}


# ===== Health Check =====

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}



# ===== Models API =====

@app.get("/api/models")
async def get_models():
    """Get available models from configured providers (Azure, Ollama)."""
    try:
        from src.models_service import get_all_models
        models = await get_all_models()
        return {"success": True, "models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UpdateEmbeddingRequest(BaseModel):
    model_id: str
    provider: str

@app.post("/api/config/embedding")
async def update_embedding_model(request: UpdateEmbeddingRequest):
    """Update the active embedding model."""
    try:
        from src.embeddings import get_embeddings_service
        
        # Parse model_id which might be "ollama:nomic-embed-text"
        model_name = request.model_id
        if ":" in model_name: 
            # strip prefix if present in ID but not actual model name for Ollama
            # For Ollama service we expect just the name
            if request.provider == "Ollama" and model_name.startswith("ollama:"):
                model_name = model_name.replace("ollama:", "")
        
        service = get_embeddings_service()
        service.set_model(model_name, request.provider.lower())
        
        return {"success": True, "message": f"Embedding model updated to {model_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # run the app with config from settings
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app", 
        host=settings.host, 
        port=settings.port, 
        reload=settings.reload
    )
