"""
Formatters for HTML and Markdown output using Docling's built-in export methods.

This module provides thin wrappers around Docling's native export_to_markdown()
and export_to_html() methods, with HybridChunker for intelligent chunking.
"""

from typing import List, Dict, Any
from docling.chunking import HybridChunker # type: ignore


class HTMLFormatter:
    """Formatter for HTML output using Docling's built-in export."""

    def format(self, conversion_result) -> str:
        """Convert Docling result to HTML using built-in export method."""
        return conversion_result.document.export_to_html()

    def create_chunks(self, conversion_result, chunk_size: int) -> List[Dict]:
        """Create chunks using Docling's HybridChunker with page provenance."""
        chunker = HybridChunker(max_tokens=chunk_size)
        chunk_iter = chunker.chunk(dl_doc=conversion_result.document)
        
        chunks = []
        for chunk in chunk_iter:
            enriched_text = chunker.contextualize(chunk=chunk)
            
            # Extract page numbers and bounding boxes from chunk provenance
            page_numbers = set()
            bboxes = []
            if hasattr(chunk, 'meta') and hasattr(chunk.meta, 'doc_items'):
                for doc_item in chunk.meta.doc_items:
                    if hasattr(doc_item, 'prov') and doc_item.prov:
                        for prov in doc_item.prov:
                            if hasattr(prov, 'page_no'):
                                page_numbers.add(prov.page_no)
                            if hasattr(prov, 'bbox'):
                                bboxes.append({
                                    'page_no': prov.page_no if hasattr(prov, 'page_no') else None,
                                    'bbox': list(prov.bbox.as_tuple()) if hasattr(prov.bbox, 'as_tuple') else None
                                })
            
            chunks.append({
                "content": enriched_text,
                "mime_type": "text/html",
                "metadata": {
                    "chunk_type": "hybrid_chunk",
                    "content_length": len(enriched_text),
                    "page_numbers": sorted(page_numbers) if page_numbers else [],
                    "bboxes": bboxes,
                }
            })
        return chunks

    def get_document_structure(self, conversion_result) -> Dict[str, Any]:
        """Get document structure information."""
        document = conversion_result.document
        structure = {
            'format': 'html',
            'pages': [{'page_index': i, 'size': page.size} for i, page in enumerate(document.pages)],
            'elements': []
        }

        for item, level in document.iterate_items():
            if hasattr(item, 'prov') and item.prov:
                for prov in item.prov:
                    element_info = {
                        'type': str(item.label) if hasattr(item, 'label') else 'unknown',
                        'level': level,
                        'bbox': list(prov.bbox.as_tuple()) if hasattr(prov, 'bbox') else None,
                        'page_index': prov.page_no - 1,
                        'text': item.text if hasattr(item, 'text') else None,
                    }
                    structure['elements'].append(element_info)
                    break

        return structure



class MarkdownFormatter:
    """Formatter for Markdown output using Docling's built-in export."""

    def format(self, conversion_result) -> str:
        """Convert Docling result to Markdown using built-in export method."""
        return conversion_result.document.export_to_markdown()

    def create_chunks(self, conversion_result, chunk_size: int) -> List[Dict]:
        """Create chunks using Docling's HybridChunker with page provenance."""
        chunker = HybridChunker(max_tokens=chunk_size)
        chunk_iter = chunker.chunk(dl_doc=conversion_result.document)
        
        chunks = []
        for chunk in chunk_iter:
            enriched_text = chunker.contextualize(chunk=chunk)
            
            # Extract page numbers and bounding boxes from chunk provenance
            page_numbers = set()
            bboxes = []
            if hasattr(chunk, 'meta') and hasattr(chunk.meta, 'doc_items'):
                for doc_item in chunk.meta.doc_items:
                    if hasattr(doc_item, 'prov') and doc_item.prov:
                        for prov in doc_item.prov:
                            if hasattr(prov, 'page_no'):
                                page_numbers.add(prov.page_no)
                            if hasattr(prov, 'bbox'):
                                bboxes.append({
                                    'page_no': prov.page_no if hasattr(prov, 'page_no') else None,
                                    'bbox': list(prov.bbox.as_tuple()) if hasattr(prov.bbox, 'as_tuple') else None
                                })
            
            chunks.append({
                "content": enriched_text,
                "mime_type": "text/plain",
                "metadata": {
                    "chunk_type": "hybrid_chunk",
                    "content_length": len(enriched_text),
                    "page_numbers": sorted(page_numbers) if page_numbers else [],
                    "bboxes": bboxes,
                }
            })
        return chunks

    def get_document_structure(self, conversion_result) -> Dict[str, Any]:
        """Get document structure information."""
        document = conversion_result.document
        structure = {
            'format': 'markdown',
            'pages': [{'page_index': i, 'size': page.size} for i, page in enumerate(document.pages)],
            'elements': []
        }

        for item, level in document.iterate_items():
            if hasattr(item, 'prov') and item.prov:
                for prov in item.prov:
                    element_info = {
                        'type': str(item.label) if hasattr(item, 'label') else 'unknown',
                        'level': level,
                        'bbox': list(prov.bbox.as_tuple()) if hasattr(prov, 'bbox') else None,
                        'page_index': prov.page_no - 1,
                        'text': item.text if hasattr(item, 'text') else None,
                    }
                    structure['elements'].append(element_info)
                    break

        return structure
