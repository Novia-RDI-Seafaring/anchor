from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# =====
# UI Component Types
# =====
class UIComponentType(str, Enum):
  """Types of UI components the agent can request to render."""
  LIST = "list"
  TABLE = "table"
  IMAGE = "image"
  PAGE_PREVIEW = "page_preview"
  MARKDOWN_TABLE = "markdown_table"

class UIComponentData(BaseModel):
  """Data for a UI component to be rendered by the frontend."""
  component_type: UIComponentType = Field(
    description='Type of UI component to render'
  )
  data: Dict[str, Any] = Field(
    description='Component-specific data payload'
  )
  metadata: Optional[Dict[str, Any]] = Field(
    default=None,
    description='Optional metadata about the component'
  )

# =====
# State
# =====
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

__all__ = ["RAGState", "UIComponentData", "UIComponentType"]
