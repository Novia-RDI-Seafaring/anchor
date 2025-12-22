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
            if _has_bullet_points(content):
                bullet_count += 1
            if _has_table_structure(content):
                table_count += 1
        
        if table_count > len(results) / 2:
            return UIComponentType.TABLE
        if bullet_count > len(results) / 2:
            return UIComponentType.LIST
        
        first_content = results[0].get("content", "")
        if _has_table_structure(first_content):
            return UIComponentType.TABLE
        if _has_bullet_points(first_content):
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
        return _format_as_list(results)
    elif component_type == UIComponentType.TABLE:
        return _format_as_table(results)
    elif component_type == UIComponentType.IMAGE:
        return _format_as_image(results)
    elif component_type == UIComponentType.PAGE_PREVIEW:
        return _format_as_page_preview(results)
    elif component_type == UIComponentType.MARKDOWN_TABLE:
        return _format_as_table(results)
    else:
        return _format_as_list(results)


# =====
# Internal Helpers
# =====
def _has_bullet_points(content: str) -> bool:
    """Check if content contains bullet point patterns."""
    bullet_pattern = r'^[\-\•\*]\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    bullet_count = sum(1 for line in lines if re.match(bullet_pattern, line.strip()))
    return bullet_count >= 2


def _has_table_structure(content: str) -> bool:
    """Check if content contains table patterns."""
    lines = content.split('\n')
    pipe_lines = [line for line in lines if '|' in line and line.strip()]
    if len(pipe_lines) >= 2:
        return True
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    kv_count = sum(1 for line in lines if re.match(kv_pattern, line.strip()))
    return kv_count >= 4


def _parse_bullet_points(content: str) -> list:
    """Parse bullet points from content."""
    bullet_pattern = r'^[\-\•\*]\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    bullet_items = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(bullet_pattern, line)
        if match:
            label = match.group(1).strip()
            value = match.group(2).strip()
            if label and value:
                bullet_items.append({"label": label, "value": value})
    
    return bullet_items


def _parse_key_value_pairs(content: str) -> list:
    """Parse key-value pairs from content."""
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    kv_items = []
    
    for line in lines:
        line = line.strip()
        if not line or len(line) > 200:
            continue
        match = re.match(kv_pattern, line)
        if match:
            label = match.group(1).strip()
            value = match.group(2).strip()
            if label and value and len(label) < 100 and len(value) < 200:
                if ':' in label or '.' in label or len(label.split()) > 8:
                    continue
                kv_items.append({"label": label, "value": value})
    
    return kv_items


def _format_as_list(results: list) -> dict:
    """Format results as a list of bullet points."""
    all_bullet_items = []
    seen_labels = set()
    
    for r in results:
        content = r.get("content", "")
        parsed_items = _parse_bullet_points(content)
        
        for item in parsed_items:
            label = item["label"].strip().lower()
            if label not in seen_labels:
                all_bullet_items.append(item)
                seen_labels.add(label)
    
    if all_bullet_items:
        return {"items": [{"items": all_bullet_items, "type": "bullets"}]}
    
    # Fallback to key-value pairs
    all_kv_items = []
    seen_kv_labels = set()
    
    for r in results:
        content = r.get("content", "")
        kv_items = _parse_key_value_pairs(content)
        
        for item in kv_items:
            label = item["label"].strip().lower()
            if label not in seen_kv_labels:
                all_kv_items.append(item)
                seen_kv_labels.add(label)
    
    if all_kv_items:
        return {"items": [{"items": all_kv_items, "type": "bullets"}]}
    
    return {"items": []}


def _parse_table_from_content(content: str) -> dict | None:
    """Parse table structure from content."""
    lines = content.split('\n')
    
    # Check for markdown-style pipe tables
    pipe_lines = [line for line in lines if '|' in line and line.strip()]
    if len(pipe_lines) >= 2:
        rows = []
        for line in pipe_lines:
            if re.match(r'^\s*\|[\s\-\:]+\|\s*$', line):
                continue
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            if cells:
                rows.append(cells)
        
        if len(rows) >= 2:
            return {"headers": rows[0], "rows": rows[1:]}
    
    # Check for key-value pairs
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    kv_pairs = []
    for line in lines:
        line = line.strip()
        match = re.match(kv_pattern, line)
        if match:
            kv_pairs.append([match.group(1).strip(), match.group(2).strip()])
    
    if len(kv_pairs) >= 3:
        return {"headers": ["Property", "Value"], "rows": kv_pairs}
    
    return None


def _format_as_table(results: list) -> dict:
    """Format results as a table."""
    for r in results:
        content = r.get("content", "")
        parsed_table = _parse_table_from_content(content)
        if parsed_table and len(parsed_table.get("rows", [])) > 0:
            return parsed_table
    
    # Aggregate key-value pairs from all chunks
    all_kv_pairs = []
    seen_labels = set()
    
    for r in results:
        content = r.get("content", "")
        bullet_items = _parse_bullet_points(content)
        if bullet_items:
            for item in bullet_items:
                label = item["label"].strip().lower()
                if label not in seen_labels:
                    all_kv_pairs.append([item["label"], item["value"]])
                    seen_labels.add(label)
        else:
            kv_items = _parse_key_value_pairs(content)
            for item in kv_items:
                label = item["label"].strip().lower()
                if label not in seen_labels:
                    all_kv_pairs.append([item["label"], item["value"]])
                    seen_labels.add(label)
    
    if all_kv_pairs:
        return {"headers": ["Property", "Value"], "rows": all_kv_pairs}
    
    if results:
        return {"headers": ["Property", "Value"], "rows": [["No structured data found", "Please check the source documents"]]}
    
    return {"headers": ["Property", "Value"], "rows": []}


def _format_as_page_preview(results: list) -> dict:
    """Format the top result as a page preview."""
    if not results:
        return {"source": "No results", "content": "No matching documents found.", "metadata": {}, "similarity": 0}
    
    top_result = results[0]
    return {
        "source": top_result.get("filename", "Unknown Source"),
        "content": top_result.get("content", ""),
        "metadata": top_result.get("metadata", {}),
        "similarity": top_result.get("similarity", 0.0)
    }


def _format_as_image(results: list) -> dict:
    """Format results as image gallery, including extracted diagrams and figures."""
    images = []
    
    for r in results:
        # First, check for extracted document images (diagrams, figures, charts)
        document_images = r.get("document_images", [])
        for img in document_images:
            images.append({
                "url": f"data:image/png;base64,{img['image_base64']}",
                "caption": img.get('caption') or f"{img.get('image_type', 'Figure').title()} from {r.get('filename', 'document')}",
                "source": r.get("filename", ""),
                "similarity": r.get("similarity", 0.0),
                "image_type": img.get('image_type', 'figure'),
                "page_number": img.get('page_number')
            })
        
        # Also check metadata for image_url or image_base64 (legacy support)
        metadata = r.get("metadata", {})
        
        if "image_url" in metadata:
            images.append({
                "url": metadata["image_url"],
                "caption": r.get("filename", ""),
                "source": r.get("filename", ""),
                "similarity": r.get("similarity", 0.0)
            })
        elif "image_base64" in metadata:
            images.append({
                "url": f"data:image/png;base64,{metadata['image_base64']}",
                "caption": r.get("filename", ""),
                "source": r.get("filename", ""),
                "similarity": r.get("similarity", 0.0)
            })
    
    if not images:
        return {"images": [], "message": "No images found in results"}
    
    return {"images": images}


__all__ = [
    "UIComponentType",
    "UIComponentData",
    "determine_component_type",
    "format_for_component",
]
