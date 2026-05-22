"""Tests for the silver per-page md loader used by the agent context fallback."""
import json

import pytest

from src.agent.tools.product_data import (
    _find_silver_pages_by_filename,
    _load_all_silver_pages,
    _refresh_data_dir,
    _silver_pages_cache,
)


def setup_function(_):
    _silver_pages_cache.clear()


@pytest.fixture(autouse=True)
def refresh_product_data_after_test():
    yield
    _refresh_data_dir()


def _write_sample_silver(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_DATA_DIR", str(tmp_path))
    doc_dir = tmp_path / "silver" / "sample-pump-datasheet"
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)
    (doc_dir / "index.json").write_text(
        json.dumps({"document": {"filename": "sample-pump-datasheet.pdf"}}),
        encoding="utf-8",
    )
    (pages_dir / "1.md").write_text("# Sample Pump Datasheet\n\nTECHNICAL DATA", encoding="utf-8")
    (pages_dir / "2.md").write_text("OPERATING DATA", encoding="utf-8")
    _refresh_data_dir()


def test_loads_sample_pages(tmp_path, monkeypatch):
    _write_sample_silver(tmp_path, monkeypatch)
    pages = _load_all_silver_pages()
    assert "sample-pump-datasheet.pdf" in pages
    md_by_page = pages["sample-pump-datasheet.pdf"]
    assert set(md_by_page.keys()) == {1, 2}
    assert "Sample Pump Datasheet" in md_by_page[1]
    assert "OPERATING DATA" in md_by_page[2]


def test_find_silver_pages_by_filename_flexible_match(tmp_path, monkeypatch):
    _write_sample_silver(tmp_path, monkeypatch)
    pages = _find_silver_pages_by_filename("sample-pump-datasheet.pdf")
    assert pages is not None and len(pages) == 2

    # case-insensitive
    pages_ci = _find_silver_pages_by_filename("SAMPLE-PUMP-DATASHEET.PDF")
    assert pages_ci is not None


def test_find_silver_pages_returns_none_for_unknown():
    assert _find_silver_pages_by_filename("zzz-not-a-doc.pdf") is None
