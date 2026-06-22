"""`anchor-mcp --project <folder>` resolves that folder's layered config."""
from __future__ import annotations

import pytest

from anchor.adapters.mcp import stdio_main
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env, create_project


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_EMBED_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_project_folder_layers_env_and_marker(tmp_path):
    env = create_env("work", settings={"provider": "local", "embed_model": "ENVMODEL"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    # an override in the project's own marker wins over the env profile
    (folder / "anchor.toml").write_text(
        'env = "work"\nname = "pumps"\nembed_model = "MARK"\n'
    )

    cfg = stdio_main._config_for_project(folder)
    assert cfg.data_dir == folder / ".anchor_data"
    assert cfg.embed_model == "MARK"
    assert cfg.provider == "local"  # inherited from the env profile


def test_project_inherits_env_when_no_override(tmp_path):
    env = create_env("work", settings={"provider": "local", "embed_model": "ENVMODEL"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    cfg = stdio_main._config_for_project(folder)
    assert cfg.embed_model == "ENVMODEL"


def test_project_without_marker_warns_and_defaults(tmp_path, capsys):
    cfg = stdio_main._config_for_project(tmp_path)  # no anchor.toml here
    assert "no anchor.toml" in capsys.readouterr().err
    assert cfg.data_dir is not None  # plain AnchorConfig defaults
