import os
import httpx
from typing import List, Dict, Any, Optional

def get_azure_model() -> Optional[Dict[str, str]]:
    """
    Checks for Azure OpenAI configuration in environment variables.
    Returns a model dict if configured, else None.
    """
    if os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        return {
            "id": f"azure:{deployment}",
            "label": f"Azure OpenAI - {deployment}",
            "provider": "Azure OpenAI",
            "type": "chat"
        }
    return None

async def get_ollama_models() -> List[Dict[str, str]]:
    """
    Queries the local Ollama instance for available models.
    """
    # Support both env names; prefer OLLAMA_URL but accept OLLAMA_BASE_URL to reduce config confusion
    ollama_url = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
    # Handle Docker scenarios where host.docker.internal is needed
    # But usually the backend running continuously might be on the host or in a container.
    # We will try the configured URL.
    
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{ollama_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get("models", []):
                    name = model.get("name")
                    
                    # Heuristics for classification
                    is_embedding = "embed" in name.lower()
                    
                    # If unsure, we could fetch details, but name check is fast and usually sufficient for Ollama
                    # Let's try to verify with details if ambiguous, but for now name is good first pass.
                    # Commonly: 'nomic-embed-text', 'mxbai-embed-large', 'snowflake-arctic-embed'
                    
                    models.append({
                        "id": f"ollama:{name}",
                        "label": f"Ollama - {name}",
                        "provider": "Ollama",
                        "type": "embedding" if is_embedding else "chat"
                    })
                return models
    except Exception as e:
        print(f"Failed to fetch Ollama models: {e}")
        pass
    
    return []

async def get_all_models() -> List[Dict[str, str]]:
    """
    Aggregates models from all providers.
    """
    models = []
    
    # Azure
    azure_model = get_azure_model()
    if azure_model:
        models.append(azure_model)
        
    # Ollama
    ollama_models = await get_ollama_models()
    models.extend(ollama_models)
    
    # Default fallback if nothing found (to avoid empty UI)
    if not models:
        models.append({
            "id": "gpt-4o", 
            "label": "OpenAI - GPT-4o (Fallback)", 
            "provider": "OpenAI",
            "type": "chat"
        })
        
    return models
