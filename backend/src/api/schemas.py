"""API request/response schemas (Pydantic models)."""
from pydantic import BaseModel
from typing import Optional


class URLRequest(BaseModel):
    """Request to add a URL to the knowledge base."""
    url: str


class SearchRequest(BaseModel):
    """Request to search the knowledge base."""
    query: str
    top_k: int = 5
    document_id: Optional[str] = None
