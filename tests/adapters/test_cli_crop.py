"""CLI `anchor crop` / `anchor page-image --dpi` against the real renderer.

The crop help's own example form (`anchor crop SLUG <page>/<region_id>.png`)
must resolve: the crop is rendered lazily from the bronze PDF on first request
and cached at gold/<slug>/pages/<page>/<region_id>.png.
"""
from __future__ import annotations

import asyncio
import json

import pymupdf
import pytest
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.cli.services import _build_real_services

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Isolated data dir with HOME-isolation so no real anchor.toml is picked up."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    return tmp_path / "data"


def _seed(data_dir) -> None:
    """Seed a one-page doc with a real bronze PDF and one gold region."""
    _, _, _, _, doc_store = _build_real_services(data_dir)

    pdf = pymupdf.open()
    page = pdf.new_page(width=595.3, height=841.9)
    page.insert_text((72, 144), "Pump curve goes here")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    async def run():
        await doc_store.stash_bronze(pdf_bytes, "testdoc.pdf")
        await doc_store.write_silver_artifact(
            "testdoc", "index.json",
            json.dumps({
                "document": {"title": "Test Doc", "filename": "testdoc.pdf", "page_count": 1},
                "outline": [],
            }),
        )
        await doc_store.write_gold_region_file("testdoc", 1, [
            {"id": "r1", "kind": "chart", "title": "Pump curve", "page": 1,
             "bbox": [60.0, 120.0, 300.0, 200.0], "tags": [], "entities": []},
        ])
        await doc_store.mark_gold_complete("testdoc", {"mode": "keyed"})

    asyncio.run(run())


def _run(data_dir, *args):
    return CliRunner().invoke(cli_app, [*args, "--data-dir", str(data_dir)])


def test_crop_help_example_form_resolves(data_dir):
    """`anchor crop SLUG 1/r1.png` - the help's own example - must work."""
    _seed(data_dir)
    result = _run(data_dir, "crop", "testdoc", "1/r1.png")
    assert result.exit_code == 0, result.output
    path = data_dir / "gold" / "testdoc" / "pages" / "1" / "r1.png"
    assert result.output.strip() == str(path)
    assert path.read_bytes()[:8] == PNG_MAGIC


def test_crop_accepts_inspect_region_token_style(data_dir):
    _seed(data_dir)
    result = _run(data_dir, "crop", "testdoc", "p1/r1")
    assert result.exit_code == 0, result.output
    assert (data_dir / "gold" / "testdoc" / "pages" / "1" / "r1.png").exists()


def test_crop_dpi_flag_rerenders_larger(data_dir):
    _seed(data_dir)
    low = _run(data_dir, "crop", "testdoc", "1/r1.png", "--dpi", "72")
    assert low.exit_code == 0, low.output
    path = data_dir / "gold" / "testdoc" / "pages" / "1" / "r1.png"
    low_size = path.stat().st_size
    high = _run(data_dir, "crop", "testdoc", "1/r1.png", "--dpi", "600")
    assert high.exit_code == 0, high.output
    assert path.stat().st_size > low_size


def test_crop_unknown_region_says_what_exists_and_the_valid_form(data_dir):
    _seed(data_dir)
    result = _run(data_dir, "crop", "testdoc", "1/r9.png")
    assert result.exit_code == 1
    assert "r9" in result.output
    assert "<page>/<region_id>.png" in result.output


def test_page_image_dpi_flag_renders_variant(data_dir):
    _seed(data_dir)
    result = _run(data_dir, "page-image", "testdoc", "1", "--dpi", "300")
    assert result.exit_code == 0, result.output
    path = data_dir / "silver" / "testdoc" / "pages" / "1@300dpi.png"
    assert result.output.strip() == str(path)
    assert path.read_bytes()[:8] == PNG_MAGIC
