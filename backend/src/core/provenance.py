'''Helpers for KB provenance and lineage payloads.'''

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

def get_run_id() -> str | None:
    return None

try:
    from opentelemetry import trace as ot_trace
except Exception:  # pragma: no cover
    ot_trace = None


def create_retrieval_id() -> str:
    return f'ret-{uuid4().hex[:12]}'


def get_current_trace_id() -> Optional[str]:
    if ot_trace is None:
        return None
    try:
        span = ot_trace.get_current_span()
        context = span.get_span_context() if span else None
        if not context or not context.trace_id:
            return None
        return format(context.trace_id, '032x')
    except Exception:
        return None


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_page_numbers(metadata: Optional[Dict[str, Any]]) -> List[int]:
    if not isinstance(metadata, dict):
        return []
    pages = set()
    for key in ('page_numbers', 'pages'):
        for item in _as_list(metadata.get(key)):
            if isinstance(item, int):
                pages.add(item)
    for key in ('page_no', 'page_number', 'page'):
        value = metadata.get(key)
        if isinstance(value, int):
            pages.add(value)
    doc_items = metadata.get('doc_items')
    if isinstance(doc_items, list):
        for item in doc_items:
            if not isinstance(item, dict):
                continue
            prov_list = item.get('prov')
            if not isinstance(prov_list, list):
                continue
            for prov in prov_list:
                if not isinstance(prov, dict):
                    continue
                page_no = prov.get('page_no')
                if isinstance(page_no, int):
                    pages.add(page_no)
    return sorted(pages)


def normalize_section_path(metadata: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(metadata, dict):
        return []
    for key in ('headings', 'section_path', 'sections'):
        value = metadata.get(key)
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def normalize_bboxes(metadata: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(metadata, dict):
        return []
    output: List[Dict[str, Any]] = []
    if isinstance(metadata.get('bboxes'), list):
        for item in metadata['bboxes']:
            if not isinstance(item, dict):
                continue
            page_no = item.get('page_no') or item.get('page_number') or item.get('page')
            bbox = item.get('bbox')
            if isinstance(page_no, int) and isinstance(bbox, list):
                output.append({'page_no': page_no, 'bbox': bbox})
    elif isinstance(metadata.get('bbox'), list):
        page_no = metadata.get('page_no') or metadata.get('page_number') or metadata.get('page')
        if isinstance(page_no, int):
            output.append({'page_no': page_no, 'bbox': metadata['bbox']})

    if output:
        return output

    doc_items = metadata.get('doc_items')
    if not isinstance(doc_items, list):
        return output

    for item in doc_items:
        if not isinstance(item, dict):
            continue
        prov_list = item.get('prov')
        if not isinstance(prov_list, list):
            continue
        for prov in prov_list:
            if not isinstance(prov, dict):
                continue
            page_no = prov.get('page_no')
            bbox = prov.get('bbox')
            if not isinstance(page_no, int) or not isinstance(bbox, dict):
                continue
            try:
                output.append(
                    {
                        'page_no': page_no,
                        'bbox': [
                            min(float(bbox.get('l', 0.0)), float(bbox.get('r', 0.0))),
                            max(float(bbox.get('t', 0.0)), float(bbox.get('b', 0.0))),
                            max(float(bbox.get('l', 0.0)), float(bbox.get('r', 0.0))),
                            min(float(bbox.get('t', 0.0)), float(bbox.get('b', 0.0))),
                        ],
                    }
                )
            except (TypeError, ValueError):
                continue
    return output


def build_retrieved_chunk(
    *,
    chunk_id: str,
    content: str,
    metadata: Optional[Dict[str, Any]],
    score: float,
    rank: int,
    query: str,
    top_k: int,
    retrieval_id: str,
    collection_name: str,
    document_id: Optional[str],
    filename: Optional[str],
    trace_id: Optional[str],
) -> Dict[str, Any]:
    normalized_metadata = dict(metadata or {})
    page_numbers = normalize_page_numbers(normalized_metadata)
    section_path = normalize_section_path(normalized_metadata)
    bboxes = normalize_bboxes(normalized_metadata)
    primary_page = page_numbers[0] if page_numbers else None
    primary_bbox = bboxes[0]['bbox'] if bboxes else []

    if document_id and 'document_id' not in normalized_metadata:
        normalized_metadata['document_id'] = document_id
    if filename and 'filename' not in normalized_metadata:
        normalized_metadata['filename'] = filename
    if page_numbers and 'page_numbers' not in normalized_metadata:
        normalized_metadata['page_numbers'] = page_numbers
    if section_path and 'headings' not in normalized_metadata:
        normalized_metadata['headings'] = section_path
    if bboxes and 'bboxes' not in normalized_metadata:
        normalized_metadata['bboxes'] = bboxes

    provenance = {
        'artifact': {
            'document_id': document_id,
            'filename': filename,
            'chunk_id': chunk_id,
            'page_numbers': page_numbers,
            'section_path': section_path,
            'bboxes': bboxes,
        },
        'pipeline': {
            'ingestion': {'extractor': 'docling', 'chunker': 'docling-node-parser'},
            'index': {'backend': 'pgvector', 'collection': collection_name},
            'retrieval': {
                'query': query,
                'top_k': top_k,
                'rank': rank,
                'score': float(score),
                'retrieval_id': retrieval_id,
            },
        },
        'trace': {'trace_id': trace_id, 'run_id': get_run_id()},
    }

    return {
        'id': chunk_id,
        'content': content,
        'filename': filename or 'Unknown',
        'document_id': document_id,
        'similarity': float(score),
        'page_numbers': page_numbers,
        'page_no': primary_page,
        'section_path': section_path,
        'bboxes': bboxes,
        'bbox': primary_bbox,
        'metadata': normalized_metadata,
        'citation': {
            'document_id': document_id,
            'filename': filename,
            'chunk_id': chunk_id,
            'page_numbers': page_numbers,
            'section_path': section_path,
        },
        'provenance': provenance,
    }
