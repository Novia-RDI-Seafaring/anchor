"""UI component formatting logic."""
from __future__ import annotations

from typing import Dict, Any

from .content_parsers import (
    parse_bullet_points,
    parse_key_value_pairs,
    parse_table_from_content,
)


def format_as_list(results: list) -> dict:
    """Format results as a list of bullet points."""
    all_bullet_items = []
    seen_labels = set()
    
    for r in results:
        content = r.get("content", "")
        parsed_items = parse_bullet_points(content)
        
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
        kv_items = parse_key_value_pairs(content)
        
        for item in kv_items:
            label = item["label"].strip().lower()
            if label not in seen_kv_labels:
                all_kv_items.append(item)
                seen_kv_labels.add(label)
    
    if all_kv_items:
        return {"items": [{"items": all_kv_items, "type": "bullets"}]}
    
    return {"items": []}


def format_as_table(results: list) -> dict:
    """Format results as a table."""
    for r in results:
        content = r.get("content", "")
        parsed_table = parse_table_from_content(content)
        if parsed_table and len(parsed_table.get("rows", [])) > 0:
            return parsed_table
    
    # Aggregate key-value pairs from all chunks
    all_kv_pairs = []
    seen_labels = set()
    
    for r in results:
        content = r.get("content", "")
        bullet_items = parse_bullet_points(content)
        if bullet_items:
            for item in bullet_items:
                label = item["label"].strip().lower()
                if label not in seen_labels:
                    all_kv_pairs.append([item["label"], item["value"]])
                    seen_labels.add(label)
        else:
            kv_items = parse_key_value_pairs(content)
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


def format_as_page_preview(results: list) -> dict:
    """Format the top result as a page preview."""
    if not results:
        return {"source": "No results", "content": "No matching documents found.", "metadata": {}, "similarity": 0}
    
    top_result = results[0]
    metadata = top_result.get("metadata", {}) or {}
    provenance = top_result.get("provenance", {}) or {}
    artifact = provenance.get("artifact", {}) if isinstance(provenance, dict) else {}
    pipeline = provenance.get("pipeline", {}) if isinstance(provenance, dict) else {}
    retrieval = pipeline.get("retrieval", {}) if isinstance(pipeline, dict) else {}
    trace = provenance.get("trace", {}) if isinstance(provenance, dict) else {}

    page_numbers = top_result.get("page_numbers") or artifact.get("page_numbers") or metadata.get("page_numbers") or []
    if not page_numbers and metadata.get("page_no") is not None:
        page_numbers = [metadata.get("page_no")]

    section_path = top_result.get("section_path") or artifact.get("section_path") or metadata.get("headings") or []
    bboxes = top_result.get("bboxes") or artifact.get("bboxes") or metadata.get("bboxes") or []

    return {
        "source": top_result.get("filename", "Unknown Source"),
        "document_id": top_result.get("document_id") or artifact.get("document_id") or metadata.get("document_id"),
        "content": top_result.get("content", ""),
        "metadata": metadata,
        "similarity": top_result.get("similarity", 0.0),
        "page_numbers": page_numbers,
        "sections": section_path,
        "bboxes": bboxes,
        "retrieval_id": retrieval.get("retrieval_id"),
        "trace_id": trace.get("trace_id"),
        "citation": top_result.get("citation"),
        "provenance": provenance,
    }


def format_as_image(results: list) -> dict:
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
