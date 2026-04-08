"""Tests for the LLM-driven silver page md polisher (mocked client)."""
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.silver import (
    needs_polish,
    polish_pages_md,
    render_pages_md,
)


# ── needs_polish heuristic ───────────────────────────────────────────────────


def test_needs_polish_skips_short_text_only_page():
    docling: dict[str, Any] = {"items": [
        {"label": "section_header", "page": 1, "bbox": [0, 100, 50, 90], "text": "h"},
        {"label": "text", "page": 1, "bbox": [0, 80, 50, 60], "text": "para"},
    ]}
    assert needs_polish(docling, page=1) is False


def test_needs_polish_triggers_on_table():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 100, 50, 90], "text": "x"},
        {"label": "table", "page": 1, "bbox": [0, 80, 50, 60], "cells": []},
    ]}
    assert needs_polish(docling, page=1) is True


def test_needs_polish_triggers_on_picture():
    docling: dict[str, Any] = {"items": [
        {"label": "picture", "page": 1, "bbox": [0, 0, 1, 1]},
    ]}
    assert needs_polish(docling, page=1) is True


def test_needs_polish_triggers_on_many_items():
    items = [
        {"label": "text", "page": 1, "bbox": [0, i, 1, i - 1], "text": str(i)}
        for i in range(40)
    ]
    assert needs_polish({"items": items}, page=1) is True


def test_needs_polish_false_for_missing_page():
    assert needs_polish({"items": []}, page=1) is False


# ── polish_pages_md with mocked client ───────────────────────────────────────


class _MockPolisher:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def polish_page(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"# polished page {kwargs['page_no']}\n\n{kwargs['deterministic_md'].strip()}"


def test_polish_pages_md_invokes_client_only_on_complex_pages(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        # Page 1: simple narrative (skipped)
        {"label": "section_header", "page": 1, "bbox": [0, 100, 50, 90], "text": "Intro"},
        {"label": "text", "page": 1, "bbox": [0, 80, 50, 60], "text": "Hello."},
        # Page 2: has a table (polished)
        {"label": "table", "page": 2, "bbox": [0, 100, 50, 80], "cells": [
            {"row": 0, "col": 0, "text": "h"},
            {"row": 1, "col": 0, "text": "v"},
        ]},
    ]}
    seed = render_pages_md(docling)
    client = _MockPolisher()
    out = polish_pages_md(
        docling,
        pages_png_dir=tmp_path,
        deterministic_md=seed,
        client=client,
    )
    # Page 1 was skipped → unchanged
    assert out[1] == seed[1]
    # Page 2 was polished → mock prefix appears
    assert out[2].startswith("# polished page 2")
    # Client was called exactly once (page 2)
    assert len(client.calls) == 1
    assert client.calls[0]["page_no"] == 2
    assert client.calls[0]["page_image"] == tmp_path / "2.png"


def test_polish_pages_md_only_pages_override(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 100, 50, 90], "text": "narrative only"},
    ]}
    seed = render_pages_md(docling)
    client = _MockPolisher()
    out = polish_pages_md(
        docling,
        pages_png_dir=tmp_path,
        deterministic_md=seed,
        client=client,
        only_pages=[1],
    )
    assert out[1].startswith("# polished page 1")
    assert len(client.calls) == 1


def test_polish_pages_md_default_client_raises(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        {"label": "table", "page": 1, "bbox": [0, 100, 50, 80], "cells": []},
    ]}
    seed = render_pages_md(docling)
    with pytest.raises(RuntimeError, match="No PageMdPolisherClient"):
        polish_pages_md(docling, pages_png_dir=tmp_path, deterministic_md=seed)


def test_polish_pages_md_no_polish_needed_returns_seed_unchanged(tmp_path: Path):
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 100, 50, 90], "text": "short"},
    ]}
    seed = render_pages_md(docling)
    # No client passed — should still succeed because nothing needs polishing.
    out = polish_pages_md(docling, pages_png_dir=tmp_path, deterministic_md=seed)
    assert out == seed
