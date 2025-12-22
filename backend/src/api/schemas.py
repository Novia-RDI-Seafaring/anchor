"""API request/response schemas (Pydantic models)."""
from pydantic import BaseModel
from typing import Optional, List


class URLRequest(BaseModel):
    """Request to add a URL to the knowledge base."""
    url: str


class SearchRequest(BaseModel):
    """Request to search the knowledge base."""
    query: str
    top_k: int = 5
    document_id: Optional[str] = None


class PageImagesRequest(BaseModel):
    """Request for multiple page images."""
    page_numbers: List[int]


class UpdateEmbeddingRequest(BaseModel):
    """Request to update the embedding model."""
    model_id: str
    provider: str
