"""
Embeddings Service.

Generates text embeddings using OpenAI or Azure OpenAI.
"""

import os
from typing import List
from openai import AzureOpenAI, OpenAI

from .config import get_settings


class EmbeddingsService:
    """Service to generate text embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Check for Azure OpenAI first
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        
        if azure_key and azure_endpoint:
            self.client = AzureOpenAI(
                api_key=azure_key,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
                azure_endpoint=azure_endpoint
            )
            # Use AZURE_EMBEDDING_DEPLOYMENT env var, fallback to text-embedding-ada-002
            self.model = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "azure-text-embedding-ada-002")
            self.provider = "azure"
            print(f"EmbeddingsService: Using Azure OpenAI with deployment '{self.model}'")
        else:
            # Fallback to OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = "text-embedding-ada-002"
            self.provider = "openai"
            print("EmbeddingsService: Using OpenAI")
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        return response.data[0].embedding
    
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
        return [item.embedding for item in sorted_data]


# Singleton instance
_embeddings_service = None

def get_embeddings_service() -> EmbeddingsService:
    """Get or create the embeddings service singleton."""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = EmbeddingsService()
    return _embeddings_service

