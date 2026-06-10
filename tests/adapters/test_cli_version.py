"""`anchor version` must track the installed distribution, not a hardcoded string.

Regression guard: `__version__` was pinned at "0.2.0" in source and shipped stale
through both the 0.2.1 and 0.2.2 releases, so `anchor version` lied about which
wheel was installed. It now derives from package metadata.
"""
from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

import anchor
from anchor.adapters.cli.main import app

runner = CliRunner()


def test_dunder_version_matches_distribution_metadata():
    assert anchor.__version__ == version("anchor-kb")


def test_version_command_prints_installed_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0, result.output
    assert version("anchor-kb") in result.output
