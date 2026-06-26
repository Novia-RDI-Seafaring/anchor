"""Named-environment + folder-based project resolution and config layering."""
from __future__ import annotations

import pytest

from anchor.core.ids import InvalidEnvNameError, InvalidProjectNameError
from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    DEFAULT_ENV,
    DEFAULT_PROJECT,
    Meta,
    NoEnvironmentError,
    NoProjectError,
    ProjectNotEmptyError,
    config_for_data_dir,
    create_env,
    create_project,
    default_env_name,
    environment_meta,
    list_env_names,
    move_project,
    project_contents,
    project_meta,
    remove_project,
    rename_project,
    resolve_environment,
    resolve_project,
    resolve_project_config,
    set_default_env,
    set_project_description,
    set_use,
)

_CLEAR = (
    "ANCHOR_ENV",
    "ANCHOR_PROJECT",
    "ANCHOR_CONFIG",
    "ANCHOR_DATA_DIR",
    "ANCHOR_EMBED_MODEL",
    "ANCHOR_PROVIDER",
    "ANCHOR_OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


# --------------------------------------------------------------------------- #
# Environments
# --------------------------------------------------------------------------- #
def test_create_and_resolve_env(tmp_path):
    create_env("local", settings={"provider": "local"})
    env = resolve_environment("local")
    assert env.initialized
    assert env.name == "local"
    assert env.root == tmp_path / ".anchor" / "envs" / "local"


def test_default_env_name_and_set(tmp_path):
    assert default_env_name() == DEFAULT_ENV  # "local" fallback
    create_env("work")
    set_default_env("work")
    assert default_env_name() == "work"
    assert resolve_environment().name == "work"  # no arg -> default


def test_env_precedence_envvar_and_use(tmp_path, monkeypatch):
    create_env("a")
    create_env("b")
    monkeypatch.setenv("ANCHOR_ENV", "b")
    assert resolve_environment().name == "b"  # env var wins over default
    monkeypatch.delenv("ANCHOR_ENV")
    set_use("a")
    assert resolve_environment().name == "a"  # use selection


def test_list_env_names(tmp_path):
    create_env("local")
    create_env("work")
    assert list_env_names() == ["local", "work"]


def test_invalid_env_name_rejected(tmp_path):
    with pytest.raises(InvalidEnvNameError):
        create_env("../escape")


# --------------------------------------------------------------------------- #
# Projects (folder-based; managed projects live under <env>/projects/<name>/)
# --------------------------------------------------------------------------- #
def test_create_and_list_projects(tmp_path):
    env = create_env("local")
    create_project(env, "pumps", description="LKH pump datasheets")
    create_project(env, "paper")
    env = resolve_environment("local")
    assert env.list_project_names() == ["paper", "pumps"]
    for sub in ("bronze", "silver", "gold", "canvases"):
        assert (env.root / "projects" / "pumps" / ".anchor_data" / sub).is_dir()
    # the project folder carries an anchor.toml marker
    assert (env.root / "projects" / "pumps" / "anchor.toml").is_file()


def test_managed_project_dir_holds_data_subfolder(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    assert env.project_root("pumps") == env.root / "projects" / "pumps"
    assert env.project_dir("pumps") == env.root / "projects" / "pumps" / ".anchor_data"


def test_create_project_in_external_folder(tmp_path):
    """`anchor init` path: a project folder anywhere, data in .anchor_data."""
    env = create_env("local")
    folder = tmp_path / "work" / "pumps"
    create_project(env, "pumps", root=folder)
    assert env.project_root("pumps") == folder
    assert env.project_dir("pumps") == folder / ".anchor_data"
    assert (folder / "anchor.toml").is_file()
    assert (folder / ".anchor_data" / "bronze").is_dir()
    # registry binds the name to the external folder
    assert env.project_exists("pumps")
    assert resolve_project_config(env, "pumps").data_dir == folder / ".anchor_data"


def test_create_project_requires_env(tmp_path):
    env = resolve_environment("ghost")  # not created
    with pytest.raises(NoEnvironmentError):
        create_project(env, "pumps")


def test_invalid_project_name_rejected(tmp_path):
    env = create_env("local")
    with pytest.raises(InvalidProjectNameError):
        env.project_dir("../escape")


def test_project_metadata_roundtrip(tmp_path):
    env = create_env("local")
    create_project(env, "pumps", description="LKH datasheets", tags=("pumps",))
    meta = project_meta(env, "pumps")
    assert meta.description == "LKH datasheets"
    assert meta.tags == ("pumps",)


def test_environment_metadata(tmp_path):
    create_env("work", settings={"provider": "azure"},
               meta=Meta(description="Company Azure tenant"))
    assert environment_meta(resolve_environment("work")).description == "Company Azure tenant"


def test_set_project_description_preserves_overrides(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    # overrides live in the project's anchor.toml marker (at the project root)
    (env.project_root("pumps") / "anchor.toml").write_text(
        'env = "local"\nname = "pumps"\nembed_model = "custom"\n\n[meta]\ndescription = "old"\n'
    )
    set_project_description(env, "pumps", "new")
    assert project_meta(env, "pumps").description == "new"
    assert resolve_project_config(env, "pumps").embed_model == "custom"


# --------------------------------------------------------------------------- #
# Move (cross-boundary)
# --------------------------------------------------------------------------- #
def test_move_project_between_envs(tmp_path):
    local = create_env("local")
    work = create_env("work")
    create_project(local, "pumps")
    (local.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")

    move_project(local, "pumps", work)

    assert not local.project_exists("pumps")
    assert work.project_exists("pumps")
    assert (work.project_dir("pumps") / "bronze" / "d.pdf").is_file()


def test_move_refuses_existing_target(tmp_path):
    local = create_env("local")
    work = create_env("work")
    create_project(local, "pumps")
    create_project(work, "pumps")
    with pytest.raises(FileExistsError):
        move_project(local, "pumps", work)


# --------------------------------------------------------------------------- #
# Remove
# --------------------------------------------------------------------------- #
def test_remove_external_deregisters_but_keeps_data(tmp_path):
    env = create_env("local")
    folder = tmp_path / "work" / "pumps"
    create_project(env, "pumps", root=folder)

    result = remove_project(env, "pumps")

    assert result["removed"] == "pumps"
    assert result["deleted_data"] is False
    assert not resolve_environment("local").project_exists("pumps")
    # an external project's folder + data are left on disk by default
    assert (folder / ".anchor_data").is_dir()
    assert "pumps" not in resolve_environment("local").list_project_names()


def test_remove_managed_drops_folder(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    root = env.project_root("pumps")

    result = remove_project(env, "pumps")

    # a managed project is auto-discovered from disk, so remove drops its folder
    assert result["deleted_data"] is True
    assert not root.exists()
    env = resolve_environment("local")
    assert not env.project_exists("pumps")
    assert "pumps" not in env.list_project_names()


def test_remove_external_delete_data_wipes_anchor_bits(tmp_path):
    env = create_env("local")
    folder = tmp_path / "work" / "pumps"
    create_project(env, "pumps", root=folder)

    result = remove_project(env, "pumps", delete_data=True)

    assert result["deleted_data"] is True
    # the external `anchor init` folder stays; only data + marker are gone
    assert folder.is_dir()
    assert not (folder / ".anchor_data").exists()
    assert not (folder / "anchor.toml").exists()


def test_remove_refuses_nonempty_without_force(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    (env.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")

    with pytest.raises(ProjectNotEmptyError):
        remove_project(env, "pumps")
    # still registered — nothing was touched
    assert resolve_environment("local").project_exists("pumps")


def test_remove_force_removes_nonempty(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    (env.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")

    remove_project(env, "pumps", delete_data=True, force=True)
    assert not resolve_environment("local").project_exists("pumps")


def test_remove_counts_canvases_as_content(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    (env.project_dir("pumps") / "canvases" / "board").mkdir(parents=True)

    assert project_contents(env, "pumps") == {"documents": 0, "canvases": 1}
    with pytest.raises(ProjectNotEmptyError):
        remove_project(env, "pumps")


def test_remove_unknown_project_raises(tmp_path):
    env = create_env("local")
    with pytest.raises(NoProjectError):
        remove_project(env, "ghost")


def test_remove_only_touches_named_project(tmp_path):
    env = create_env("local")
    create_project(env, "keep")
    create_project(env, "drop")

    remove_project(env, "drop", delete_data=True)

    env = resolve_environment("local")
    assert env.project_exists("keep")
    assert env.project_dir("keep").is_dir()
    assert not env.project_exists("drop")


# --------------------------------------------------------------------------- #
# Rename
# --------------------------------------------------------------------------- #
def test_rename_updates_registry_and_marker(tmp_path):
    env = create_env("local")
    create_project(env, "day1-test", description="throwaway")

    result = rename_project(env, "day1-test", "agentic-engineering")

    assert result["renamed"] == "day1-test"
    assert result["to"] == "agentic-engineering"
    env = resolve_environment("local")
    assert env.project_exists("agentic-engineering")
    assert not env.project_exists("day1-test")
    # a managed folder tracks the name; the old folder is gone
    new_root = env.project_root("agentic-engineering")
    assert new_root == env.root / "projects" / "agentic-engineering"
    assert not (env.root / "projects" / "day1-test").exists()
    marker = env_mod._read_project_marker(new_root)
    assert marker["name"] == "agentic-engineering"
    assert marker["meta"]["name"] == "agentic-engineering"
    # description carried forward
    assert project_meta(env, "agentic-engineering").description == "throwaway"


def test_rename_external_keeps_folder_path(tmp_path):
    env = create_env("local")
    folder = tmp_path / "work" / "pumps"
    create_project(env, "pumps", root=folder)
    (env.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")

    rename_project(env, "pumps", "lkh")

    env = resolve_environment("local")
    # the external folder path is unchanged; only marker + registry are rebound
    assert env.project_root("lkh") == folder
    assert not env.project_exists("pumps")
    assert (folder / ".anchor_data" / "bronze" / "d.pdf").is_file()
    assert env_mod._read_project_marker(folder)["name"] == "lkh"


def test_rename_rejects_existing_target(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    create_project(env, "paper")
    with pytest.raises(FileExistsError):
        rename_project(env, "pumps", "paper")


def test_rename_unknown_project_raises(tmp_path):
    env = create_env("local")
    with pytest.raises(NoProjectError):
        rename_project(env, "ghost", "spook")


def test_rename_rejects_bad_new_name(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    with pytest.raises(InvalidProjectNameError):
        rename_project(env, "pumps", "../escape")


def test_rename_preserves_config_overrides(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    (env.project_root("pumps") / "anchor.toml").write_text(
        'env = "local"\nname = "pumps"\nembed_model = "custom"\n\n[meta]\n'
        'name = "Pumps"\ndescription = "LKH"\n'
    )
    rename_project(env, "pumps", "lkh")
    env = resolve_environment("local")
    # a user-set display name is left untouched; only the project id changes
    assert env_mod._read_project_marker(env.project_root("lkh"))["meta"]["name"] == "Pumps"
    assert resolve_project_config(env, "lkh").embed_model == "custom"


# --------------------------------------------------------------------------- #
# Resolution + config layering
# --------------------------------------------------------------------------- #
def test_resolve_project_precedence(tmp_path, monkeypatch):
    env = create_env("local")
    create_project(env, "pumps")
    # explicit arg
    assert resolve_project("local", "pumps").name == "pumps"
    # ANCHOR_PROJECT
    monkeypatch.setenv("ANCHOR_PROJECT", "pumps")
    assert resolve_project("local").name == "pumps"
    monkeypatch.delenv("ANCHOR_PROJECT")
    # use selection
    set_use("local", "pumps")
    assert resolve_project().name == "pumps"


def test_resolve_project_require_exists(tmp_path):
    create_env("local")
    with pytest.raises(NoProjectError):
        resolve_project("local", "ghost", require_exists=True)


def test_layering_env_then_project_then_envvar(tmp_path, monkeypatch):
    env = create_env("local", settings={"embed_model": "env-model", "provider": "local"})
    create_project(env, "pumps")
    (env.project_root("pumps") / "anchor.toml").write_text(
        'env = "local"\nname = "pumps"\nembed_model = "proj-model"\n'
    )

    cfg = resolve_project_config(env, "pumps")
    assert cfg.embed_model == "proj-model"
    assert cfg.provider == "local"
    assert cfg.data_dir == env.project_dir("pumps")

    monkeypatch.setenv("ANCHOR_EMBED_MODEL", "env-var-model")
    assert resolve_project_config(env, "pumps").embed_model == "env-var-model"


def test_config_for_data_dir_layers_project(tmp_path):
    env = create_env("local", settings={"provider": "azure", "embed_model": "m"})
    create_project(env, "pumps")
    cfg = config_for_data_dir(env.project_dir("pumps"))
    assert cfg.provider == "azure"
    assert cfg.data_dir == env.project_dir("pumps")


def test_config_for_data_dir_external_is_plain(tmp_path):
    external = tmp_path / "scratch"
    assert config_for_data_dir(external).data_dir == external


def test_env_dotenv_is_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    env = create_env("work", settings={"provider": "azure"})
    (env.root / ".env").write_text("ANCHOR_OPENAI_API_KEY=secret-key\n")
    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    assert cfg.openai_api_key is not None
    assert cfg.openai_api_key.get_secret_value() == "secret-key"


# --------------------------------------------------------------------------- #
# Legacy ~/anchor-data shim
# --------------------------------------------------------------------------- #
def test_default_env_default_project_uses_legacy_data_dir(tmp_path, monkeypatch):
    legacy = tmp_path / "anchor-data"
    (legacy / "bronze").mkdir(parents=True)
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", legacy)
    env = resolve_environment("local")  # not created
    assert env.project_dir(DEFAULT_PROJECT) == legacy
    assert env.list_project_names() == [DEFAULT_PROJECT]


def test_legacy_shim_yields_to_real_default_project(tmp_path, monkeypatch):
    legacy = tmp_path / "anchor-data"
    legacy.mkdir()
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", legacy)
    env = create_env("local")
    create_project(env, DEFAULT_PROJECT)  # real projects/default now exists
    assert env.project_dir(DEFAULT_PROJECT) == env.root / "projects" / "default" / ".anchor_data"
