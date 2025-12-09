"""
Embeddings Service.

Generates text embeddings using OpenAI or Azure OpenAI.
"""

import os
from typing import List
from openai import AzureOpenAI, OpenAI

from .config import get_settings


# Model dimension mapping
MODEL_DIMENSIONS = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "azure-text-embedding-ada-002": 1536,
    "azure-text-embedding-3-small": 1536,
    "azure-text-embedding-3-large": 3072,
}


class EmbeddingsService:
    """Service to generate text embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Check for Azure OpenAI first
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_key = os.getenv("OPENAI_API_KEY")
        
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
        else:
            # Fallback to OpenAI - validate API key is set
            if not openai_key:
                raise ValueError(
                    "No valid embeddings API credentials found. "
                    "Set either:\n"
                    "  - AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT (for Azure OpenAI), or\n"
                    "  - OPENAI_API_KEY (for OpenAI)\n"
                    "At least one set of credentials is required."
                )
            
            # Fallback to OpenAI - default to text-embedding-3-large to match config
            self.client = OpenAI(api_key=openai_key)
            # Default to text-embedding-3-large (3072 dims) to match config.embedding_dimension
            self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
            self.provider = "openai"
            print(f"EmbeddingsService: Using OpenAI with model '{self.model}'")
        
        # Validate dimension matches config
        model_dim = MODEL_DIMENSIONS.get(self.model, None)
        if model_dim is None:
            print(f"Warning: Unknown model '{self.model}', cannot validate dimension")
        elif model_dim != self.settings.embedding_dimension:
            raise ValueError(
                f"Model '{self.model}' produces {model_dim}-dimensional embeddings, "
                f"but config.embedding_dimension is {self.settings.embedding_dimension}. "
                f"Update config.embedding_dimension or use a model matching the configured dimension."
            )
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        embedding = response.data[0].embedding
        
        # Validate dimension at runtime
        if len(embedding) != self.settings.embedding_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(embedding)} dimensions, "
                f"expected {self.settings.embedding_dimension} (model: {self.model})"
            )
        
        return embedding
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []
        
        # OpenAI API supports batching up to 2048 texts
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


# Singleton instance
_embeddings_service = None

def get_embeddings_service() -> EmbeddingsService:
    """Get or create the embeddings service singleton."""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = EmbeddingsService()
    return _embeddings_service

