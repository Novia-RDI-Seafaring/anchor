"""Process-local docling JSON cache for demo-time page inspection."""
from __future__ import annotations

from typing import Any

_DOCLING_BY_DOCUMENT_ID: dict[str, dict[str, Any]] = {}
_DOCUMENT_ID_BY_FILENAME: dict[str, str] = {}


def register_docling_json(document_id: str, filename: str, docling_data: dict[str, Any]) -> None:
    if not document_id or not isinstance(docling_data, dict):
        return
    _DOCLING_BY_DOCUMENT_ID[document_id] = docling_data
    if filename:
        _DOCUMENT_ID_BY_FILENAME[filename] = document_id


def get_docling_json(document_id: str) -> dict[str, Any] | None:
    return _DOCLING_BY_DOCUMENT_ID.get(document_id)


def get_docling_json_for_filename(filename: str) -> dict[str, Any] | None:
    document_id = _DOCUMENT_ID_BY_FILENAME.get(filename)
    if not document_id:
        return None
    return _DOCLING_BY_DOCUMENT_ID.get(document_id)


def remove_docling_json(document_id: str, filename: str = "") -> None:
    _DOCLING_BY_DOCUMENT_ID.pop(document_id, None)
    if filename:
        mapped = _DOCUMENT_ID_BY_FILENAME.get(filename)
        if mapped == document_id:
            _DOCUMENT_ID_BY_FILENAME.pop(filename, None)


def clear_docling_cache() -> None:
    _DOCLING_BY_DOCUMENT_ID.clear()
    _DOCUMENT_ID_BY_FILENAME.clear()
