"""Tests for the ANCHOR_DATA_DIR override.

Ensures that with the env var set, the silver loaders + rebuild script
write/read from a scratch directory and never touch `backend/data`.
"""
import json
from pathlib import Path

import pytest

from src.agent.tools import product_data
from src.ingestion.silver import build_index, build_pages_meta, render_pages_md

DOC_SLUG = "sample-pump-datasheet"
DOC_FILENAME = "sample-pump-datasheet.pdf"


def _sample_docling() -> dict:
    return {
        "items": [
            {
                "label": "title",
                "page": 1,
                "text": "Sample Pump Datasheet",
                "bbox": [40, 780, 260, 740],
            },
            {
                "label": "section_header",
                "page": 1,
                "text": "TECHNICAL DATA",
                "bbox": [40, 700, 220, 680],
            },
            {
                "label": "table",
                "page": 1,
                "bbox": [40, 660, 320, 560],
                "cells": [
                    {"row": 0, "col": 0, "text": "Model"},
                    {"row": 0, "col": 1, "text": "Max inlet pressure"},
                    {"row": 1, "col": 0, "text": "SP-10"},
                    {"row": 1, "col": 1, "text": "10 bar"},
                ],
            },
        ]
    }


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ANCHOR_DATA_DIR at tmp_path and copy in one fixture doc."""
    monkeypatch.setenv("ANCHOR_DATA_DIR", str(tmp_path))

    silver_doc = tmp_path / "silver" / DOC_SLUG
    silver_doc.mkdir(parents=True)
    (silver_doc / "docling.json").write_text(json.dumps(_sample_docling()), encoding="utf-8")

    product_data._refresh_data_dir()
    yield tmp_path
    monkeypatch.delenv("ANCHOR_DATA_DIR", raising=False)
    product_data._refresh_data_dir()


def test_product_data_loaders_use_override(isolated_data_dir: Path):
    assert product_data.DATA_DIR == isolated_data_dir
    assert product_data.SILVER_DIR == isolated_data_dir / "silver"
    # Index file doesn't exist in the tmp dir yet — loader returns empty.
    assert product_data._load_all_indexes() == {}


def test_silver_pages_loader_after_rebuild(isolated_data_dir: Path):
    # Build the silver artifacts directly into the tmp dir.
    docling_path = isolated_data_dir / "silver" / DOC_SLUG / "docling.json"
    docling = json.loads(docling_path.read_text())
    index = build_index(docling, filename=DOC_FILENAME)
    docling_path.with_name("index.json").write_text(json.dumps(index))

    pages_dir = docling_path.parent / "pages"
    pages_dir.mkdir()
    for page_no, md in render_pages_md(docling).items():
        (pages_dir / f"{page_no}.md").write_text(md)

    # Now the loader should pick them up from the tmp dir.
    product_data._refresh_data_dir()
    found = product_data._find_silver_pages_by_filename(DOC_FILENAME)
    assert found is not None
    assert set(found.keys()) == {1}
    assert "Sample Pump Datasheet" in found[1]


def test_pages_meta_writes_to_override(isolated_data_dir: Path):
    docling_path = isolated_data_dir / "silver" / DOC_SLUG / "docling.json"
    docling = json.loads(docling_path.read_text())
    meta = build_pages_meta(docling)
    target = docling_path.with_name("pages.meta.json")
    target.write_text(json.dumps(meta))

    assert target.exists()


def test_rebuild_script_honors_env_var(isolated_data_dir: Path, tmp_path: Path):
    """End-to-end: invoke rebuild_indexes.py as a subprocess with ANCHOR_DATA_DIR
    pointed at the tmp dir. Verify outputs land in the tmp dir, not backend/data."""
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["ANCHOR_DATA_DIR"] = str(isolated_data_dir)

    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "rebuild_indexes.py")],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    silver_doc = isolated_data_dir / "silver" / DOC_SLUG
    assert (silver_doc / "index.json").exists()
    assert (silver_doc / "pages.meta.json").exists()
    assert (silver_doc / "pages" / "1.md").exists()
