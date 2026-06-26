"""CLI page-argument consistency (issue #185).

Every per-page read command must accept the page number BOTH as a
positional argument and as --page/-p. Old call forms must keep working;
new option-form must work on commands that previously only accepted a
positional, and vice versa.

Commands under test:
  anchor page-text  SLUG PAGE          (was positional-only; --page/-p added)
  anchor page-text  SLUG --page PAGE   (new option form)
  anchor page-image SLUG PAGE          (was positional-only; --page/-p added)
  anchor page-image SLUG --page PAGE   (new option form)
  anchor regions    SLUG PAGE          (was --page-only; positional added)
  anchor regions    SLUG --page PAGE   (was the only form; still works)
  anchor regions    SLUG -p PAGE       (short option; still works)
"""

from __future__ import annotations

import asyncio
import json

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.cli.services import _build_real_services


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Isolated data dir with HOME-isolation so no real anchor.toml is picked up."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    return tmp_path / "data"


def _seed(data_dir) -> None:
    """Seed a minimal two-page doc into the real FsDocStore at data_dir."""
    _, _, _, _, doc_store = _build_real_services(data_dir)

    async def run():
        await doc_store.write_silver_artifact(
            "testdoc", "index.json",
            json.dumps({
                "document": {"title": "Test Doc", "filename": "testdoc.pdf", "page_count": 2},
                "outline": [],
            }),
        )
        await doc_store.write_silver_artifact("testdoc", "pages/1.md", "Page one text.")
        await doc_store.write_silver_artifact("testdoc", "pages/2.md", "Page two text.")
        await doc_store.write_gold_region_file("testdoc", 1, [
            {"id": "r1", "kind": "text", "title": "Region one", "page": 1,
             "bbox": [0, 100, 200, 80], "tags": [], "entities": []},
        ])
        await doc_store.write_gold_region_file("testdoc", 2, [
            {"id": "r2", "kind": "text", "title": "Region two", "page": 2,
             "bbox": [0, 200, 200, 180], "tags": [], "entities": []},
        ])
        await doc_store.mark_gold_complete("testdoc", {"mode": "keyed"})

    asyncio.run(run())


def _run(data_dir, *args):
    return CliRunner().invoke(cli_app, [*args, "--data-dir", str(data_dir)])


# ---------------------------------------------------------------------------
# anchor page-text
# ---------------------------------------------------------------------------


def test_page_text_positional_form(data_dir):
    """anchor page-text SLUG PAGE -- original positional form still works."""
    _seed(data_dir)
    result = _run(data_dir, "page-text", "testdoc", "1")
    assert result.exit_code == 0, result.output
    assert "Page one text." in result.output


def test_page_text_option_form(data_dir):
    """anchor page-text SLUG --page PAGE -- new option form works."""
    _seed(data_dir)
    result = _run(data_dir, "page-text", "testdoc", "--page", "1")
    assert result.exit_code == 0, result.output
    assert "Page one text." in result.output


def test_page_text_short_option_form(data_dir):
    """anchor page-text SLUG -p PAGE -- short option works."""
    _seed(data_dir)
    result = _run(data_dir, "page-text", "testdoc", "-p", "1")
    assert result.exit_code == 0, result.output
    assert "Page one text." in result.output


def test_page_text_both_forms_return_same_page(data_dir):
    """Positional and --page return the same content for the same page."""
    _seed(data_dir)
    r_pos = _run(data_dir, "page-text", "testdoc", "2")
    r_opt = _run(data_dir, "page-text", "testdoc", "--page", "2")
    assert r_pos.exit_code == 0, r_pos.output
    assert r_opt.exit_code == 0, r_opt.output
    assert r_pos.output == r_opt.output
    assert "Page two text." in r_pos.output


def test_page_text_missing_page_exits_nonzero(data_dir):
    """Omitting the page entirely must exit with an error code."""
    _seed(data_dir)
    result = _run(data_dir, "page-text", "testdoc")
    assert result.exit_code != 0


def test_page_text_both_positional_and_option_is_error(data_dir):
    """Supplying page twice (positional + --page) must be rejected."""
    _seed(data_dir)
    result = _run(data_dir, "page-text", "testdoc", "1", "--page", "1")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# anchor page-image
# ---------------------------------------------------------------------------


def test_page_image_positional_form(data_dir):
    """anchor page-image SLUG PAGE -- original positional form still works."""
    _seed(data_dir)
    # page-image returns a path (or an error for in-memory store); exit 0
    # when the file is absent but the page arg was resolved correctly the
    # FsDocStore will return None and _emit_bytes will exit 1.  We just verify
    # the command does NOT error with 'No such option' or an arg parse error
    # (exit code 2), which is the regression from the issue.
    result = _run(data_dir, "page-image", "testdoc", "1")
    assert result.exit_code != 2, (
        "exit 2 means argument-parse failure, which is what we are fixing"
    )


def test_page_image_option_form(data_dir):
    """anchor page-image SLUG --page PAGE -- new option form works."""
    _seed(data_dir)
    result = _run(data_dir, "page-image", "testdoc", "--page", "1")
    assert result.exit_code != 2, (
        "exit 2 means argument-parse failure, which is what we are fixing"
    )


def test_page_image_short_option_form(data_dir):
    """anchor page-image SLUG -p PAGE -- short option works."""
    _seed(data_dir)
    result = _run(data_dir, "page-image", "testdoc", "-p", "1")
    assert result.exit_code != 2


def test_page_image_missing_page_exits_nonzero(data_dir):
    """Omitting the page entirely must exit with an error code."""
    _seed(data_dir)
    result = _run(data_dir, "page-image", "testdoc")
    assert result.exit_code != 0


def test_page_image_both_positional_and_option_is_error(data_dir):
    """Supplying page twice must be rejected."""
    _seed(data_dir)
    result = _run(data_dir, "page-image", "testdoc", "1", "--page", "1")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# anchor regions
# ---------------------------------------------------------------------------


def test_regions_option_form(data_dir):
    """anchor regions SLUG --page PAGE -- original option form still works."""
    _seed(data_dir)
    result = _run(data_dir, "regions", "testdoc", "--page", "1")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["slug"] == "testdoc"
    pages = data["pages"]
    # Only page 1 regions returned.
    assert "1" in pages or 1 in pages


def test_regions_short_option_form(data_dir):
    """anchor regions SLUG -p PAGE -- short option still works."""
    _seed(data_dir)
    result = _run(data_dir, "regions", "testdoc", "-p", "1")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    pages = data["pages"]
    assert "1" in pages or 1 in pages


def test_regions_positional_form(data_dir):
    """anchor regions SLUG PAGE -- new positional form works."""
    _seed(data_dir)
    result = _run(data_dir, "regions", "testdoc", "1")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    pages = data["pages"]
    assert "1" in pages or 1 in pages


def test_regions_both_forms_return_same_page(data_dir):
    """Positional and --page return the same regions for the same page."""
    _seed(data_dir)
    r_pos = _run(data_dir, "regions", "testdoc", "2")
    r_opt = _run(data_dir, "regions", "testdoc", "--page", "2")
    assert r_pos.exit_code == 0, r_pos.output
    assert r_opt.exit_code == 0, r_opt.output
    assert json.loads(r_pos.output) == json.loads(r_opt.output)


def test_regions_no_page_returns_all(data_dir):
    """anchor regions SLUG with no page returns regions for all pages."""
    _seed(data_dir)
    result = _run(data_dir, "regions", "testdoc")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    pages = data["pages"]
    # Both pages seeded.
    assert len(pages) == 2


def test_regions_both_positional_and_option_is_error(data_dir):
    """Supplying page twice (positional + --page) must be rejected."""
    _seed(data_dir)
    result = _run(data_dir, "regions", "testdoc", "1", "--page", "1")
    assert result.exit_code != 0
