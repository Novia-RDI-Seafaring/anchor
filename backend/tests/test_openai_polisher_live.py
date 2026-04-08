"""Live integration test for OpenAIPageMdPolisher.

Skipped unless `OPENAI_API_KEY` is set. Hits the real OpenAI API on a single
page of the alfa-laval leaflet and asserts the model returns sensible markdown
grounded in the actual page content.

Run explicitly with:
    uv run pytest tests/test_openai_polisher_live.py -q -s
"""
import json
import os
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.silver import render_pages_md, render_pages_png

Docling = dict[str, Any]

TESTS_DIR = Path(__file__).resolve().parent
PDF = TESTS_DIR / "alfa-laval-lkh-centrifugal-pump.pdf"
SILVER = TESTS_DIR.parents[0] / "data" / "silver" / "alfa-laval-lkh-centrifugal-pump"

# Persisted test outputs — gitignored, safe to inspect after a run.
TEST_DATA = TESTS_DIR / "test_data" / "polisher_live"

pytestmark = [
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"),
    pytest.mark.skipif(not PDF.exists(), reason="alfa-laval pdf missing"),
    pytest.mark.skipif(not (SILVER / "docling.json").exists(), reason="silver dir missing"),
]


@pytest.fixture(scope="module")
def docling() -> Docling:
    return json.loads((SILVER / "docling.json").read_text())


@pytest.fixture(scope="module")
def page2_png() -> Path:
    TEST_DATA.mkdir(parents=True, exist_ok=True)
    target = TEST_DATA / "2.png"
    if not target.exists():
        render_pages_png(PDF, TEST_DATA, dpi=150)
    return target


def test_polisher_returns_grounded_markdown_for_page_2(docling: Docling, page2_png: Path):
    """Page 2 has all the spec tables — the polished output must contain the
    real values, not invented ones, and must be structured as markdown."""
    from src.ingestion.openai_clients import OpenAIPageMdPolisher

    polisher = OpenAIPageMdPolisher()
    seed_md = render_pages_md(docling)[2]
    page2_items = [it for it in docling["items"] if it.get("page") == 2]

    out = polisher.polish_page(
        page_image=page2_png,
        page_no=2,
        deterministic_md=seed_md,
        docling_items=page2_items,
        model=os.environ.get("LLM_MODEL", "gpt-5.4"),
    )

    (TEST_DATA / "2.raw.md").write_text(seed_md, encoding="utf-8")
    (TEST_DATA / "2.polished.md").write_text(out, encoding="utf-8")

    # Shape: non-trivial markdown
    assert len(out) > 200
    assert out.count("\n") > 10
    assert "|" in out  # at least one table

    # Grounding: real values from page 2 must appear (not hallucinated).
    # These are the canonical signals the deterministic walker fails on but
    # are unambiguously present in the source.
    must_contain_any = [
        "TECHNICAL DATA",
        "Materials",
        "Max inlet pressure",
    ]
    assert any(s in out for s in must_contain_any), f"none of {must_contain_any} in output"

    # Per-model values for max inlet pressure
    assert "LKH-5" in out
    assert "LKH-10" in out or "LKH-10 - 70" in out

    # Material grounding
    assert "316L" in out or "1.4404" in out

    # Negative checks: model must not invent obvious nonsense
    forbidden = ["lorem ipsum", "TODO", "I cannot", "as an AI"]
    for f in forbidden:
        assert f.lower() not in out.lower()


def test_polisher_emits_value_for_safety_factor_warning(docling: Docling, page2_png: Path):
    """Page 2 has 'Extended 3-years warranty' text — the polisher should
    preserve this kind of narrative line, not strip it."""
    from src.ingestion.openai_clients import OpenAIPageMdPolisher

    polisher = OpenAIPageMdPolisher()
    seed_md = render_pages_md(docling)[2]
    page2_items = [it for it in docling["items"] if it.get("page") == 2]

    out = polisher.polish_page(
        page_image=page2_png,
        page_no=2,
        deterministic_md=seed_md,
        docling_items=page2_items,
        model=os.environ.get("LLM_MODEL", "gpt-5.4"),
    )
    (TEST_DATA / "2.polished.md").write_text(out, encoding="utf-8")
    assert "warranty" in out.lower()
