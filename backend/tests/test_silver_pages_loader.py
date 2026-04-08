"""Tests for the silver per-page md loader used by the agent context fallback."""
from src.agent.tools.product_data import (
    _find_silver_pages_by_filename,
    _load_all_silver_pages,
    _silver_pages_cache,
)


def setup_function(_):
    _silver_pages_cache.clear()


def test_loads_alfa_laval_pages():
    pages = _load_all_silver_pages()
    assert "alfa-laval-lkh-centrifugal-pump.pdf" in pages
    md_by_page = pages["alfa-laval-lkh-centrifugal-pump.pdf"]
    assert set(md_by_page.keys()) == {1, 2, 3, 4}
    assert "Alfa Laval LKH" in md_by_page[1]
    assert "TECHNICAL DATA" in md_by_page[2]


def test_find_silver_pages_by_filename_flexible_match():
    pages = _find_silver_pages_by_filename("alfa-laval-lkh-centrifugal-pump.pdf")
    assert pages is not None and len(pages) == 4

    # case-insensitive
    pages_ci = _find_silver_pages_by_filename("ALFA-LAVAL-LKH-CENTRIFUGAL-PUMP.PDF")
    assert pages_ci is not None


def test_find_silver_pages_returns_none_for_unknown():
    assert _find_silver_pages_by_filename("zzz-not-a-doc.pdf") is None
