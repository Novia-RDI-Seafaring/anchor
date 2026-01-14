"""UI component types and builder logic.

This module is the single source of truth for:
- UIComponentType enum
- UIComponentData model
- Component formatting functions
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .content_parsers import has_bullet_points, has_table_structure
from .ui_formatters import (
    format_as_list,
    format_as_table,
    format_as_image,
    format_as_page_preview,
)


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
    TOC = "toc"


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
# Component Type Detection
# =====
def determine_component_type(query: str, results: list) -> UIComponentType:
    """
    Intelligently determine which UI component to use based on query and results.
    
    Priority:
    1. Check for images in metadata
    2. Check actual content structure (bullets, tables) across all results
    3. Check query keywords
    4. Fall back to result count
    """
    query_lower = query.lower()
    
    # First, check if any results contain extracted document images (diagrams, figures)
    if results:
        for r in results:
            if r.get("document_images") and len(r.get("document_images", [])) > 0:
                return UIComponentType.IMAGE
            metadata = r.get("metadata", {})
            if "image_url" in metadata or "image_base64" in metadata:
                return UIComponentType.IMAGE
    
    # Image keywords in query (diagram, figure, chart, illustration)
    if any(kw in query_lower for kw in ['image', 'picture', 'photo', 'diagram', 'figure', 'chart', 'illustration', 'graphic']):
        return UIComponentType.IMAGE
    
    # Analyze content structure across all results
    if results and len(results) > 0:
        bullet_count = 0
        table_count = 0
        
        for r in results:
            content = r.get("content", "")
            if has_bullet_points(content):
                bullet_count += 1
            if has_table_structure(content):
                table_count += 1
        
        if table_count > len(results) / 2:
            return UIComponentType.TABLE
        if bullet_count > len(results) / 2:
            return UIComponentType.LIST
        
        first_content = results[0].get("content", "")
        if has_table_structure(first_content):
            return UIComponentType.TABLE
        if has_bullet_points(first_content):
            return UIComponentType.LIST
    
    # Table keywords in query
    if any(kw in query_lower for kw in ['table', 'compare', 'comparison', 'columns', 'rows', 'versus', 'vs']):
        return UIComponentType.TABLE
    
    # Page preview keywords
    if any(kw in query_lower for kw in ['preview', 'show page', 'full document', 'source page']):
        return UIComponentType.PAGE_PREVIEW
    
    # List keywords or multiple results
    if 'list' in query_lower or len(results) > 3:
        return UIComponentType.LIST
    
    # For single result with substantial content, use page preview
    if len(results) == 1 and results[0].get("content", ""):
        content_len = len(results[0].get("content", ""))
        if content_len > 500:
            return UIComponentType.PAGE_PREVIEW
    
    return UIComponentType.LIST


# =====
# Format for Component
# =====
def format_for_component(component_type: UIComponentType, results: list) -> dict:
    """Format search results for specific component type."""
    if component_type == UIComponentType.LIST:
        return format_as_list(results)
    elif component_type == UIComponentType.TABLE:
        return format_as_table(results)
    elif component_type == UIComponentType.IMAGE:
        return format_as_image(results)
    elif component_type == UIComponentType.PAGE_PREVIEW:
        return format_as_page_preview(results)
    elif component_type == UIComponentType.MARKDOWN_TABLE:
        return format_as_table(results)
    else:
        return format_as_list(results)


__all__ = [
    "UIComponentType",
    "UIComponentData",
    "determine_component_type",
    "format_for_component",
]
