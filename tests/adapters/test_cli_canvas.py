"""CLI adapter tests for canvas workspace operations."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from anchor.adapters.cli.main import app


def test_canvas_delete_cli_requires_confirmation_and_removes_workspace(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()

    create = runner.invoke(app, ["canvas", "create", "scratch", "--data-dir", str(data_dir)])
    assert create.exit_code == 0, create.output
    assert (data_dir / "canvases" / "scratch" / "meta.json").is_file()

    refused = runner.invoke(app, ["canvas", "delete", "scratch", "--data-dir", str(data_dir)])
    assert refused.exit_code == 2
    assert (data_dir / "canvases" / "scratch" / "meta.json").is_file()

    deleted = runner.invoke(
        app,
        ["canvas", "delete", "scratch", "--yes", "--data-dir", str(data_dir)],
    )
    assert deleted.exit_code == 0, deleted.output
    assert json.loads(deleted.output) == {"slug": "scratch", "deleted": True}
    assert not (data_dir / "canvases" / "scratch").exists()
