"""`anchor demo` + `anchor canvas placeholders` — first-day smoke tests.

`anchor demo` is hard to exercise end-to-end without ingesting a real PDF
(Docling + ML deps), so we patch the IngestService.ingest_pdf away and rely
on `--no-serve` to skip the uvicorn boot. What we DO verify:

  - the demo runs with `--no-serve` and exits cleanly
  - the `demo` workspace is created
  - six placeholder nodes appear (one per hint)
  - `anchor canvas placeholders demo` lists them with hints
  - re-running is idempotent (still six placeholders, not twelve)
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from anchor.adapters.cli.main import _DEMO_PLACEHOLDER_HINTS, app


def _runner() -> CliRunner:
    return CliRunner()


def _invoke_demo_with_no_pdf(tmp_path, monkeypatch):
    """Set up so the PDF lookup misses + uvicorn is skipped."""
    # No real PDF: the demo logs a friendly note and skips ingestion.
    # `_find_sample_pdf` walks up from the CLI module to v2/data/bronze; pointing
    # HOME at tmp_path doesn't isolate that. We monkey-patch the resolver.
    monkeypatch.setattr(
        "anchor.adapters.cli.demo._find_sample_pdf",
        lambda: None,
    )
    monkeypatch.setenv("HOME", str(tmp_path))


def test_demo_seeds_workspace_with_six_placeholders(tmp_path, monkeypatch):
    _invoke_demo_with_no_pdf(tmp_path, monkeypatch)
    data_dir = tmp_path / "anchor-data"

    result = _runner().invoke(
        app,
        ["demo", "--data-dir", str(data_dir), "--no-serve"],
    )
    assert result.exit_code == 0, result.output
    assert "demo" in result.output

    # Workspace exists on disk
    assert (data_dir / "canvases" / "demo" / "state.json").is_file()
    state = json.loads((data_dir / "canvases" / "demo" / "state.json").read_text())

    placeholder_nodes = [
        n for n in state["nodes"].values() if (n.get("data") or {}).get("placeholder") is True
    ]
    assert len(placeholder_nodes) == 6
    hints = {(n["data"] or {}).get("placeholder_hint") for n in placeholder_nodes}
    assert hints == set(_DEMO_PLACEHOLDER_HINTS)


def test_demo_idempotent_on_rerun(tmp_path, monkeypatch):
    _invoke_demo_with_no_pdf(tmp_path, monkeypatch)
    data_dir = tmp_path / "anchor-data"

    r1 = _runner().invoke(app, ["demo", "--data-dir", str(data_dir), "--no-serve"])
    r2 = _runner().invoke(app, ["demo", "--data-dir", str(data_dir), "--no-serve"])
    assert r1.exit_code == 0 and r2.exit_code == 0

    state = json.loads((data_dir / "canvases" / "demo" / "state.json").read_text())
    placeholders = [
        n for n in state["nodes"].values() if (n.get("data") or {}).get("placeholder") is True
    ]
    assert len(placeholders) == 6, "re-running shouldn't duplicate placeholders"


def test_canvas_placeholders_cli_lists_seeded_nodes(tmp_path, monkeypatch):
    _invoke_demo_with_no_pdf(tmp_path, monkeypatch)
    data_dir = tmp_path / "anchor-data"

    _runner().invoke(app, ["demo", "--data-dir", str(data_dir), "--no-serve"])
    result = _runner().invoke(
        app,
        ["canvas", "placeholders", "demo", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 0, result.output
    for hint in _DEMO_PLACEHOLDER_HINTS:
        assert hint in result.output


def test_canvas_placeholders_json_format(tmp_path, monkeypatch):
    _invoke_demo_with_no_pdf(tmp_path, monkeypatch)
    data_dir = tmp_path / "anchor-data"

    _runner().invoke(app, ["demo", "--data-dir", str(data_dir), "--no-serve"])
    result = _runner().invoke(
        app,
        ["canvas", "placeholders", "demo", "--data-dir", str(data_dir), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert len(items) == 6
    assert all("hint" in it and "id" in it and "node_type" in it for it in items)
