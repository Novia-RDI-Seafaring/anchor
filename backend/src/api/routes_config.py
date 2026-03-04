"""Configuration and models API routes."""
from typing import Optional
from fastapi import APIRouter, HTTPException

from src.core.context import get_active_document_id, set_active_document_id
from .schemas import UpdateEmbeddingRequest

router = APIRouter(prefix="/api", tags=["config"])


# ===== Active Document Filter =====

@router.get("/active-document")
async def get_active_document():
    """Get the currently active document filter."""
    return {"document_id": get_active_document_id()}


@router.post("/active-document")
async def set_active_document(document_id: Optional[str] = None):
    """
    Set the active document filter for RAG queries.
    Accepts document_id as query parameter (?document_id=xxx).
    """
    # Handle empty string as None (when user selects "All Documents")
    if document_id == '':
        document_id = None
    
    set_active_document_id(document_id)
    print(f"API: Set active document filter to: {document_id or 'All Documents'}")
    return {"success": True, "document_id": get_active_document_id()}


# ===== Models API =====

@router.get("/models")
async def get_models():
    """Get available models from configured providers (Azure, Ollama)."""
    try:
        print("API: Fetching models...")
        import os
        models = [os.getenv("DEFAULT_MODEL")]
        return {"success": True, "models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/embedding")
async def update_embedding_model(request: UpdateEmbeddingRequest):
    """Update the active embedding model."""
    try:
        
        # Parse model_id which might be "ollama:nomic-embed-text"
        model_name = request.model_id
        if ":" in model_name: 
            # strip prefix if present in ID but not actual model name for Ollama
            if request.provider == "Ollama" and model_name.startswith("ollama:"):
                model_name = model_name.replace("ollama:", "")
        
        # Re-configure global settings
        raise NotImplementedError("update_embedding_model is not implemented")
        #configure_llama_index(model_name=model_name, provider=request.provider.lower())
        
        return {"success": True, "message": f"Embedding model updated to {model_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
