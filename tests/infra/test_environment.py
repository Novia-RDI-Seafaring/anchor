"""Environment + project resolution and config layering (anchor#120)."""
from __future__ import annotations

from pathlib import Path

import pytest

from anchor.core.ids import InvalidProjectNameError
from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    DEFAULT_PROJECT,
    Environment,
    NoEnvironmentError,
    NoProjectError,
    create_project,
    environment_meta,
    init_environment,
    project_meta,
    resolve_environment,
    resolve_project,
    resolve_project_config,
    set_project_description,
)

_CLEAR = (
    "ANCHOR_ENV",
    "ANCHOR_CONFIG",
    "ANCHOR_DATA_DIR",
    "ANCHOR_EMBED_MODEL",
    "ANCHOR_POLISH_MODEL",
    "ANCHOR_PROVIDER",
    "ANCHOR_DOCLING_DEVICE",
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    # Keep walk-up and the global-default fallback off real $HOME during tests.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", tmp_path / "_global_unused")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def test_explicit_env_with_config_is_initialized(tmp_path):
    root = tmp_path / "envA"
    init_environment(root, settings={"provider": "local"})
    env = resolve_environment(root)
    assert env.initialized
    assert not env.legacy
    assert env.root == root
    assert env.projects_dir == root / "projects"


def test_walk_up_finds_environment(tmp_path, monkeypatch):
    root = tmp_path / "envB"
    init_environment(root)
    nested = root / "projects" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    env = resolve_environment()
    assert env.root == root
    assert env.initialized


def test_anchor_env_var_pins_environment(tmp_path, monkeypatch):
    root = tmp_path / "envC"
    init_environment(root)
    monkeypatch.setenv("ANCHOR_ENV", str(root))
    assert resolve_environment().root == root


def test_uninitialized_env_is_reported(tmp_path):
    env = resolve_environment(tmp_path / "nope")
    assert not env.initialized
    assert not env.legacy


def test_legacy_anchor_toml_env(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    data_dir = tmp_path / "legacy-data"
    (root / "anchor.toml").write_text(f'data_dir = "{data_dir}"\nprovider = "local"\n')
    env = resolve_environment(root)
    assert env.initialized
    assert env.legacy
    assert env.project_dir(DEFAULT_PROJECT) == data_dir


def test_global_default_falls_back_to_legacy_data_dir(tmp_path, monkeypatch):
    legacy = tmp_path / "anchor-data"
    legacy.mkdir()
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", legacy)
    env = resolve_environment()  # nothing pinned, no walk-up hit
    assert env.legacy
    assert env.project_dir(DEFAULT_PROJECT) == legacy
    assert env.list_project_names() == [DEFAULT_PROJECT]


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
def test_create_and_list_projects(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root)
    create_project(env, "pumps", description="LKH pump datasheets")
    create_project(env, "paper")
    env = resolve_environment(root)  # reload from disk
    assert env.list_project_names() == ["paper", "pumps"]
    for sub in ("bronze", "silver", "gold", "canvases"):
        assert (root / "projects" / "pumps" / sub).is_dir()


def test_project_metadata_roundtrip(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root)
    create_project(env, "pumps", description="LKH pump datasheets", tags=("pumps",))
    meta = project_meta(env, "pumps")
    assert meta.description == "LKH pump datasheets"
    assert meta.tags == ("pumps",)


def test_set_project_description_preserves_settings(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root)
    create_project(env, "pumps")
    # hand-write an override setting alongside metadata
    (root / "projects" / "pumps" / "project.toml").write_text(
        'embed_model = "custom-embed"\n\n[meta]\ndescription = "old"\n'
    )
    set_project_description(env, "pumps", "new description")
    assert project_meta(env, "pumps").description == "new description"
    assert resolve_project_config(env, "pumps").embed_model == "custom-embed"


def test_environment_metadata(tmp_path):
    root = tmp_path / "env"
    init_environment(
        root,
        settings={"provider": "azure"},
        meta=env_mod.Meta(description="Company Azure tenant, confidential"),
    )
    env = resolve_environment(root)
    assert environment_meta(env).description == "Company Azure tenant, confidential"


def test_invalid_project_name_rejected(tmp_path):
    env = init_environment(tmp_path / "env")
    with pytest.raises(InvalidProjectNameError):
        env.project_dir("../escape")
    with pytest.raises(InvalidProjectNameError):
        create_project(env, "..")


def test_create_project_requires_initialized_env(tmp_path):
    env = resolve_environment(tmp_path / "bare")  # not initialized
    with pytest.raises(NoEnvironmentError):
        create_project(env, "pumps")


# --------------------------------------------------------------------------- #
# Config layering
# --------------------------------------------------------------------------- #
def test_layering_env_then_project_then_envvar(tmp_path, monkeypatch):
    root = tmp_path / "env"
    env = init_environment(root, settings={"embed_model": "env-model", "provider": "local"})
    create_project(env, "pumps")
    # project overrides the environment value
    (root / "projects" / "pumps" / "project.toml").write_text('embed_model = "proj-model"\n')

    cfg = resolve_project_config(env, "pumps")
    assert cfg.embed_model == "proj-model"
    assert cfg.provider == "local"  # inherited from the environment
    # data_dir is forced to the project directory, not the env root
    assert cfg.data_dir == root / "projects" / "pumps"

    # an ANCHOR_* env var still wins over both toml layers
    monkeypatch.setenv("ANCHOR_EMBED_MODEL", "env-var-model")
    assert resolve_project_config(env, "pumps").embed_model == "env-var-model"


def test_data_dir_in_toml_is_ignored_for_storage(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root, settings={"data_dir": "/somewhere/else"})
    create_project(env, "pumps")
    cfg = resolve_project_config(env, "pumps")
    # storage is structural: the project dir wins over any toml data_dir
    assert cfg.data_dir == root / "projects" / "pumps"


def test_resolve_project_require_exists(tmp_path):
    root = tmp_path / "env"
    init_environment(root)
    with pytest.raises(NoProjectError):
        resolve_project(root, "ghost", require_exists=True)
    # path-only resolution does not require the dir to exist yet
    rp = resolve_project(root, "ghost")
    assert rp.data_dir == root / "projects" / "ghost"


def test_resolve_project_default_in_legacy_env(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    data_dir = tmp_path / "legacy-data"
    data_dir.mkdir()
    (root / "anchor.toml").write_text(f'data_dir = "{data_dir}"\n')
    # the default project always resolves in a legacy env, even with require_exists
    rp = resolve_project(root, DEFAULT_PROJECT, require_exists=True)
    assert rp.data_dir == data_dir


def test_direct_anchorconfig_unaffected_by_resolver(tmp_path, monkeypatch):
    # AnchorConfig() with no active layers keeps the legacy walk-up behavior.
    from anchor.infra.config import AnchorConfig

    (tmp_path / "anchor.toml").write_text('embed_model = "walkup-model"\n')
    monkeypatch.chdir(tmp_path)
    assert AnchorConfig().embed_model == "walkup-model"
