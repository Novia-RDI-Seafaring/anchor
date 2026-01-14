"""
Embeddings Service.

Generates text embeddings using OpenAI, Azure OpenAI, or Ollama.
"""

import os
import httpx
import time
from typing import List, Optional
from openai import AzureOpenAI, OpenAI

from ..core.config import get_settings
from evals.trace_logger import log_event
from evals.token_utils import estimate_tokens, estimate_tokens_bulk


# Model dimension mapping
MODEL_DIMENSIONS = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "azure-text-embedding-ada-002": 1536,
    "azure-text-embedding-3-small": 1536,
    "azure-text-embedding-3-large": 3072,
    # Ollama models (variable, but commonly these)
    "nomic-embed-text": 768,
    # "mxbai-embed-large": 1024,
    # "snowflake-arctic-embed": 1024,
    "all-minilm": 384,
}


class EmbeddingsService:
    """Service to generate text embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        # Support both OLLAMA_URL and OLLAMA_BASE_URL to avoid env-name mismatches
        self.ollama_url = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
        
        # Check for explicitly configured embedding provider
        self.provider = "openai" # default
        
        # Check for Azure OpenAI first
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_key = os.getenv("OPENAI_API_KEY")
        ollama_model = os.getenv("OLLAMA_EMBEDDING_MODEL")
        
        if azure_key and azure_endpoint:
            # Both credentials are present, proceed with Azure OpenAI
            self.client = AzureOpenAI(
                api_key=azure_key,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
                azure_endpoint=azure_endpoint
            )
            # Use AZURE_EMBEDDING_DEPLOYMENT env var, fallback to text-embedding-3-large
            # to match config.embedding_dimension (3072)
            self.model = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "azure-text-embedding-3-large")
            self.provider = "azure"
            print(f"EmbeddingsService: Using Azure OpenAI with deployment '{self.model}'")
            
        elif ollama_model:
            # Ollama configured
            self.provider = "ollama"
            self.model = ollama_model
            self.client = httpx.Client(timeout=30.0) # Sync client for simplicity in this synchronous-looking interface
            print(f"EmbeddingsService: Using Ollama with model '{self.model}'")
            
        else:
            # Fallback to OpenAI - validate API key is set
            if not openai_key:
                # If specifically requested OpenAI, error out. But if we are just exploring, maybe logging is enough?
                # The original code raised ValueError, so we preserve that if no provider found.
                raise ValueError(
                    "No valid embeddings API credentials found. "
                    "Set either:\n"
                    "  - AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT (for Azure OpenAI), or\n"
                    "  - OPENAI_API_KEY (for OpenAI), or\n"
                    "  - OLLAMA_EMBEDDING_MODEL (for Ollama)\n"
                    "At least one configuration is required."
                )
            
            # Fallback to OpenAI - default to text-embedding-3-large to match config
            self.client = OpenAI(api_key=openai_key)
            # Default to text-embedding-3-large (3072 dims) to match config.embedding_dimension
            self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
            self.provider = "openai"
            print(f"EmbeddingsService: Using OpenAI with model '{self.model}'")
        
        # Validate dimension matches config
        # Note: For Ollama we might not know dimension upfront easily without querying, 
        # so we might skip strict init-time validation or warn.
        model_dim = MODEL_DIMENSIONS.get(self.model, None)
        
        # Heuristic for unknown Azure/OpenAI models
        if model_dim is None and self.provider != "ollama":
             print(f"Warning: Unknown model '{self.model}', cannot validate dimension against config.")
        
        # Only strict check if we know the dimension
        if model_dim is not None and model_dim != self.settings.embedding_dimension:
             print(f"WARNING: Model '{self.model}' produces {model_dim}-dimensional embeddings, "
                   f"but config.embedding_dimension is {self.settings.embedding_dimension}. "
                   "This may cause dimension mismatch errors in vector store.")

    def set_model(self, model_name: str, provider: str = "ollama"):
        """
        Updates the embedding model at runtime.
        WARNING: Changing this requires re-ingesting documents if dimensions change.
        """
        print(f"EmbeddingsService: Switching to model '{model_name}' (provider: {provider})")
        self.model = model_name
        self.provider = provider
        
        if provider == "ollama":
            self.client = httpx.Client(timeout=30.0)
        elif provider == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                 raise ValueError("Cannot switch to OpenAI: OPENAI_API_KEY not set.")
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == "azure":
             # Re-init Azure client if needed, or assume existing env vars are fine for just switching deployment?
             # Usually Azure endpoint/key is static, but deployment might change.
             # For now, simplistic support for Ollama switching which is the main user request.
             pass
             
        # Validate new dimension
        model_dim = MODEL_DIMENSIONS.get(self.model, None)
        if model_dim is not None and model_dim != self.settings.embedding_dimension:
             print(f"WARNING: New model '{self.model}' has dimension {model_dim}, but DB is configured for {self.settings.embedding_dimension}.")

    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        started = time.perf_counter()

        if self.provider == "ollama":
            response = self.client.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text}
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]
        else:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            embedding = response.data[0].embedding
        
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            log_event({
                "type": "embedding",
                "mode": "single",
                "model": self.model,
                "provider": self.provider,
                "input_chars": len(text),
                "input_tokens_est": estimate_tokens(text, model_name=self.model),
                "latency_ms": latency_ms,
            })
        except Exception:
            pass
        
        # Validate dimension at runtime
        if len(embedding) != self.settings.embedding_dimension:
            # Just warn for now to avoid crashing if user is experimenting
            # Or raise if critical. Original raised ValueError.
            # We keep raising to ensure data integrity.
            raise ValueError(
                f"Embedding dimension mismatch: got {len(embedding)} dimensions, "
                f"expected {self.settings.embedding_dimension} (model: {self.model}). "
                "Update PGVECTOR_DIMENSION in .env or choose a compatible model."
            )
        
        return embedding
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []
        started = time.perf_counter()
        try:
            if self.provider == "ollama":
                # Ollama API currently does one at a time for /api/embeddings usually,
                # though /api/embed (new) might support batch. /api/embeddings is strictly single.
                # Let's verify documentation or use loop. Safest is loop for now.
                embeddings = []
                for text in texts:
                    embeddings.append(self.embed_text(text))
                return embeddings
                
            else:
                # OpenAI / Azure Batch
                response = self.client.embeddings.create(
                    input=texts,
                    model=self.model
                )
                
                # Sort by index to maintain order
                sorted_data = sorted(response.data, key=lambda x: x.index)
                embeddings = [item.embedding for item in sorted_data]
                
                # Validate dimensions at runtime
                expected_dim = self.settings.embedding_dimension
                for i, emb in enumerate(embeddings):
                    if len(emb) != expected_dim:
                        raise ValueError(
                            f"Embedding dimension mismatch at index {i}: got {len(emb)} dimensions, "
                            f"expected {expected_dim} (model: {self.model})"
                        )
                
                return embeddings
        finally:
            latency_ms = (time.perf_counter() - started) * 1000
            try:
                log_event({
                    "type": "embedding",
                    "mode": "batch",
                    "model": self.model,
                    "provider": self.provider,
                    "batch_size": len(texts),
                    "input_chars": sum(len(t) for t in texts),
                    "input_tokens_est": estimate_tokens_bulk(texts, model_name=self.model),
                    "latency_ms": latency_ms,
                })
            except Exception:
                pass


# Singleton instance
_embeddings_service = None

def get_embeddings_service() -> EmbeddingsService:
    """Get or create the embeddings service singleton."""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = EmbeddingsService()
    return _embeddings_service
