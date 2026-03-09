"""RAG agent state types.

Re-exports UIComponentType and UIComponentData from shared.ui_components
and defines RAGState which uses them.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from src.api.file_provider import get_pdf_screenshot
# Re-export UI component types from shared module (single source of truth)
from src.shared.ui_components import UIComponentType, UIComponentData

class Source(BaseModel):
    filename: str
    page: int

    @property
    def image_url(self) -> str:
        return f"http://localhost:8001/api/documents/pdf/screenshot?filename={self.filename}&page_no={self.page}"

class SourceBox(BaseModel):
    source: Source
    bbox: list[int]
    
    @property
    def image_url(self) -> str:
        return f"http://localhost:8001/api/documents/pdf/screenshot?filename={self.source.filename}&page_no={self.source.page}&bbox_l={self.bbox[0]}&bbox_t={self.bbox[1]}&bbox_r={self.bbox[2]}&bbox_b={self.bbox[3]}"

class Fact(BaseModel):
    text: str
    sources: list[SourceBox]

class Note(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    facts: list[Fact]

class Relation(BaseModel):
    from_id: str
    to_id: str
    label: str = ""

class Canvas(BaseModel):
    notes: list[Note] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)




class RAGState(BaseModel):
    """State for RAG-powered conversation."""
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description='The conversation history',
    )
    current_sources: list[str] = Field(
        default_factory=list,
        description='Sources from the most recent knowledge base query',
    )
    vector_db_status: str = Field(
        default='disconnected',
        description='Status of the vector database connection',
    )
    # UI rendering state
    active_ui_components: list[UIComponentData] = Field(
        default_factory=list,
        description='Active UI components to render with their data'
    )
    render_mode: str = Field(
        default='auto',
        description='How the agent decided to render: auto, list, table, etc.'
    )
    # RAG context storage for tools
    last_chunks: list[dict[str, Any]] = Field(
        default_factory=list,
        description='Chunks from the most recent knowledge base query, used for context injection'
    )
    last_retrieval_meta: dict[str, Any] = Field(
        default_factory=dict,
        description='Metadata for the latest retrieval operation including retrieval and trace ids'
    )


__all__ = ["RAGState", "UIComponentData", "UIComponentType", "Canvas"]
