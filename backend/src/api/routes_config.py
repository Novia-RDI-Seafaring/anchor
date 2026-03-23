"""Configuration and models API routes."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["config"])


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
