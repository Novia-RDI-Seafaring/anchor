"""Environments and projects — named-env profiles + folder-based projects.

## Terms

- **environment** (env): a *named, reusable configuration profile* — provider,
  models, and the data **zone**. The trust / egress boundary. Lives at
  ``~/.anchor/envs/<name>/`` (``env.toml`` + a ``projects.toml`` registry).

- **project**: a *folder* that holds one corpus (its documents) and canvases.
  It carries an ``anchor.toml`` marker (``env`` + ``name`` + optional overrides
  / metadata) and keeps its artifacts in a hidden ``.anchor_data/`` subfolder,
  so the working folder stays clean. A project can live anywhere (created with
  ``anchor init`` in a folder) or in a managed location under the env (created
  by the agent, which has no working folder). Either way it is registered in
  its env's ``projects.toml`` (name → folder), so both are addressed by name.

- **documents** — a project's ingested corpus (bronze/silver/gold).
- **canvas** — a board inside a project.
- **zone** — the data egress / privacy boundary; a property of the environment.

## On disk

```
~/.anchor/
├── default                      # the default environment's name (one line)
├── use.toml                     # optional CLI session selection (env + project)
└── envs/
    └── <env>/
        ├── env.toml             # the profile: provider, models, zone, [meta]
        ├── .env                 # gitignored API key (never the profile)
        ├── projects.toml        # registry: project name -> folder path
        └── projects/            # managed projects created by the agent
            └── <name>/ { anchor.toml, .anchor_data/ }

~/work/pumps/                    # a project created with `anchor init` here
├── anchor.toml                  # env = "<env>", name = "pumps", [meta]
└── .anchor_data/
    ├── bronze/ silver/ gold/
    └── canvases/<slug>/
```

## Resolution

```
project marker : run inside a project folder -> its anchor.toml (the corpus + env)
env name       : --env > ANCHOR_ENV > `anchor use` > default env
project name   : --project > ANCHOR_PROJECT > `anchor use` > "default"
config         : env env.toml < project anchor.toml overrides < ANCHOR_* / flags
data_dir       : <project folder>/.anchor_data/
```
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anchor.core.ids import validate_env_name, validate_project_name
from anchor.infra.config import AnchorConfig, _load_toml_tolerant

#: Root of the environment registry. Monkeypatched in tests.
ANCHOR_HOME = Path.home() / ".anchor"

#: Environments live under ``<ANCHOR_HOME>/envs/<name>/``.
ENVS_DIRNAME = "envs"

#: The environment profile file (provider/models/zone + metadata).
ENV_CONFIG_FILENAME = "env.toml"

#: Managed projects (agent-created) live under ``<env>/projects/``.
PROJECTS_DIRNAME = "projects"

#: The project marker dropped in a project folder (``env`` + ``name`` + meta).
PROJECT_MARKER_FILENAME = "anchor.toml"

#: The per-env registry mapping project name -> folder path.
REGISTRY_FILENAME = "projects.toml"

#: A project's artifacts live in this hidden subfolder of the project folder.
DATA_DIRNAME = ".anchor_data"

#: One-line file under ANCHOR_HOME holding the default environment's name.
DEFAULT_ENV_FILE = "default"

#: Optional CLI session selection (env + project) under ANCHOR_HOME.
USE_FILE = "use.toml"

#: The environment / project used when a call names neither.
DEFAULT_ENV = "local"
DEFAULT_PROJECT = "default"

#: Environment variable overrides (peers of ``--env`` / ``--project``).
ENV_VAR = "ANCHOR_ENV"
PROJECT_VAR = "ANCHOR_PROJECT"

#: Today's pre-rework single data directory. Honored as the default env's
#: default project location until ``anchor migrate`` runs. Monkeypatched in tests.
LEGACY_DATA_DIR = Path.home() / "anchor-data"

#: The per-project storage sub-directories created under ``.anchor_data/``.
PROJECT_SUBDIRS = ("bronze", "silver", "gold", "canvases")


class NoEnvironmentError(Exception):
    """The named environment is not set up (no ``env.toml``)."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"environment {name!r} is not set up. Create it with "
            f"`anchor env create {name}`."
        )


class NoProjectError(Exception):
    """A project was required but is missing or unnamed."""

    def __init__(self, name: str | None, available: list[str]) -> None:
        self.name = name
        self.available = available
        if name:
            msg = f"project {name!r} does not exist in this environment. "
        else:
            msg = "this call needs a project. "
        if available:
            msg += f"Create one with create_project(name), or pick one: {available}."
        else:
            msg += "Create one with create_project(name)."
        super().__init__(msg)


class ProjectNotEmptyError(Exception):
    """A project still holds documents/canvases and was removed without force."""

    def __init__(self, name: str, documents: int, canvases: int) -> None:
        self.name = name
        self.documents = documents
        self.canvases = canvases
        super().__init__(
            f"project {name!r} still has {documents} document(s) and "
            f"{canvases} canvas(es). Pass force=True to remove it anyway."
        )


@dataclass(frozen=True)
class Meta:
    """User-editable metadata for an environment or a project."""

    name: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Small IO helpers
# --------------------------------------------------------------------------- #
def _safe_toml(path: Path) -> dict[str, Any]:
    try:
        return _load_toml_tolerant(path)
    except Exception:  # noqa: BLE001 — a broken config must not brick resolution
        return {}


def _expand(value: Any) -> Path:
    return Path(os.path.expandvars(str(value))).expanduser()


def _flat_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Top-level scalar/list settings only — drops ``[meta]`` and other tables."""
    return {k: v for k, v in data.items() if not isinstance(v, dict)}


def anchor_home() -> Path:
    return ANCHOR_HOME


def envs_dir() -> Path:
    return ANCHOR_HOME / ENVS_DIRNAME


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Environment:
    """A resolved environment: a named profile = the trust boundary."""

    name: str
    root: Path
    config_path: Path | None = None

    @property
    def initialized(self) -> bool:
        return self.config_path is not None

    @property
    def projects_dir(self) -> Path:
        """Managed location for agent-created projects."""
        return self.root / PROJECTS_DIRNAME

    @property
    def registry_path(self) -> Path:
        return self.root / REGISTRY_FILENAME

    def _registry(self) -> dict[str, Path]:
        return _read_registry(self.root)

    def project_root(self, project: str) -> Path:
        """The project's folder (holds its ``anchor.toml`` marker)."""
        validate_project_name(project)
        reg = self._registry()
        if project in reg:
            return reg[project]
        return self.projects_dir / project

    def project_dir(self, project: str) -> Path:
        """The project's data directory (bronze/.../canvases live here)."""
        validate_project_name(project)
        reg = self._registry()
        if project in reg:
            return reg[project] / DATA_DIRNAME
        # Back-compat: the default env's default project keeps using today's
        # ~/anchor-data until `anchor migrate` folds it in.
        if (
            project == DEFAULT_PROJECT
            and self.name == DEFAULT_ENV
            and not (self.projects_dir / project).is_dir()
            and LEGACY_DATA_DIR.is_dir()
        ):
            return LEGACY_DATA_DIR
        return self.projects_dir / project / DATA_DIRNAME

    def project_exists(self, project: str) -> bool:
        try:
            validate_project_name(project)
        except ValueError:
            return False
        if project in self._registry():
            return True
        return self.project_dir(project).is_dir()

    def list_project_names(self) -> list[str]:
        """Registry entries + managed projects/ + the legacy default. Sorted."""
        names: list[str] = list(self._registry().keys())
        if self.projects_dir.is_dir():
            for child in sorted(self.projects_dir.iterdir()):
                if not child.is_dir() or child.name in names:
                    continue
                try:
                    validate_project_name(child.name)
                except ValueError:
                    continue
                names.append(child.name)
        if (
            self.name == DEFAULT_ENV
            and DEFAULT_PROJECT not in names
            and self.project_dir(DEFAULT_PROJECT) == LEGACY_DATA_DIR
            and LEGACY_DATA_DIR.is_dir()
        ):
            names.append(DEFAULT_PROJECT)
        return sorted(names)


@dataclass(frozen=True)
class ResolvedProject:
    """A project resolved to its concrete data dir and layered config."""

    environment: Environment
    name: str
    data_dir: Path
    config: AnchorConfig


# --------------------------------------------------------------------------- #
# Registry (project name -> folder path, per environment)
# --------------------------------------------------------------------------- #
def _read_registry(env_root: Path) -> dict[str, Path]:
    table = _safe_toml(_expand(env_root) / REGISTRY_FILENAME).get("projects", {})
    if not isinstance(table, dict):
        return {}
    return {str(k): _expand(v) for k, v in table.items() if isinstance(v, str)}


def _write_registry(env_root: Path, mapping: dict[str, Path]) -> None:
    env_root = _expand(env_root)
    env_root.mkdir(parents=True, exist_ok=True)
    lines = ["[projects]"]
    for name, path in sorted(mapping.items()):
        lines.append(f"{_toml_scalar(name)} = {_toml_scalar(str(path))}")
    (env_root / REGISTRY_FILENAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def register_project(env: Environment, name: str, root: Path | str) -> None:
    validate_project_name(name)
    reg = _read_registry(env.root)
    reg[name] = _expand(root)
    _write_registry(env.root, reg)


def unregister_project(env: Environment, name: str) -> None:
    reg = _read_registry(env.root)
    if reg.pop(name, None) is not None:
        _write_registry(env.root, reg)


# --------------------------------------------------------------------------- #
# Project marker (anchor.toml in the project folder)
# --------------------------------------------------------------------------- #
def _write_project_marker(
    root: Path, env_name: str, name: str, settings: dict[str, Any], meta: Meta | None
) -> None:
    root = _expand(root)
    root.mkdir(parents=True, exist_ok=True)
    fields: dict[str, Any] = {"env": env_name, "name": name, **settings}
    _write_toml(root / PROJECT_MARKER_FILENAME, fields, meta)


def _read_project_marker(root: Path) -> dict[str, Any]:
    return _safe_toml(_expand(root) / PROJECT_MARKER_FILENAME)


def _walk_up_for_project(start: Path | None = None) -> Path | None:
    """Find the nearest ancestor folder holding an ``anchor.toml`` marker."""
    cwd = start or Path.cwd()
    for directory in (cwd, *cwd.parents):
        if (directory / PROJECT_MARKER_FILENAME).is_file():
            return directory
    return None


# --------------------------------------------------------------------------- #
# Defaults + session selection
# --------------------------------------------------------------------------- #
def default_env_name() -> str:
    f = ANCHOR_HOME / DEFAULT_ENV_FILE
    if f.is_file():
        name = f.read_text(encoding="utf-8").strip()
        if name:
            return name
    return DEFAULT_ENV


def set_default_env(name: str) -> None:
    validate_env_name(name)
    ANCHOR_HOME.mkdir(parents=True, exist_ok=True)
    (ANCHOR_HOME / DEFAULT_ENV_FILE).write_text(name + "\n", encoding="utf-8")


def get_use() -> dict[str, str]:
    data = _safe_toml(ANCHOR_HOME / USE_FILE)
    return {k: str(v) for k, v in data.items() if k in ("env", "project")}


def set_use(env: str, project: str | None = None) -> None:
    validate_env_name(env)
    if project is not None:
        validate_project_name(project)
    ANCHOR_HOME.mkdir(parents=True, exist_ok=True)
    lines = [f'env = "{env}"']
    if project is not None:
        lines.append(f'project = "{project}"')
    (ANCHOR_HOME / USE_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def _load_env(name: str) -> Environment:
    root = envs_dir() / name
    cfg = root / ENV_CONFIG_FILENAME
    return Environment(name=name, root=root, config_path=cfg if cfg.is_file() else None)


def resolve_environment(env: str | None = None) -> Environment:
    """Resolve the active environment by name."""
    name = env or os.environ.get(ENV_VAR) or get_use().get("env") or default_env_name()
    validate_env_name(name)
    return _load_env(name)


def _load_env_dotenv(env: Environment) -> None:
    """Load ``<env>/.env`` into the process env (ANCHOR_* keys, if unset)."""
    if env.config_path is None:
        return
    dotenv = env.root / ".env"
    if not dotenv.is_file():
        return
    for raw in dotenv.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("ANCHOR_") and key not in os.environ:
            os.environ[key] = value.strip()


def _layered_config(env: Environment, data_dir: Path, marker: dict[str, Any]) -> AnchorConfig:
    _load_env_dotenv(env)
    layers: dict[str, Any] = {}
    if env.config_path is not None:
        layers.update(_flat_settings(_safe_toml(env.config_path)))
    overrides = _flat_settings(marker)
    overrides.pop("env", None)
    overrides.pop("name", None)
    layers.update(overrides)
    layers.pop("data_dir", None)
    return AnchorConfig.from_layers(layer_values=layers, data_dir=data_dir)


def resolve_project_config(env: Environment, project: str) -> AnchorConfig:
    """Layer config for ``project``: env env.toml < project anchor.toml < ANCHOR_*."""
    data_dir = env.project_dir(project)
    marker = _read_project_marker(env.project_root(project))
    return _layered_config(env, data_dir, marker)


def resolve_project(
    env: str | None = None,
    project: str | None = None,
    *,
    require_exists: bool = False,
) -> ResolvedProject:
    """Resolve ``(environment, project)`` to a data dir + layered config.

    With neither ``env`` nor ``project`` given, a project ``anchor.toml`` found
    by walking up from the current directory wins (run Anchor inside a project
    folder). Otherwise resolve by name.
    """
    if env is None and project is None:
        root = _walk_up_for_project()
        if root is not None:
            marker = _read_project_marker(root)
            env_name = str(marker.get("env") or default_env_name())
            validate_env_name(env_name)
            environment = _load_env(env_name)
            name = str(marker.get("name") or root.name)
            data_dir = root / DATA_DIRNAME
            return ResolvedProject(
                environment, name, data_dir, _layered_config(environment, data_dir, marker)
            )
    environment = resolve_environment(env)
    name = project or os.environ.get(PROJECT_VAR) or get_use().get("project") or DEFAULT_PROJECT
    validate_project_name(name)
    if require_exists and not environment.project_exists(name):
        raise NoProjectError(name, environment.list_project_names())
    return ResolvedProject(
        environment, name, environment.project_dir(name),
        resolve_project_config(environment, name),
    )


def config_for_data_dir(data_dir: Path | str) -> AnchorConfig:
    """Layer config for a project data dir (``<root>/.anchor_data``).

    Reads the project's ``anchor.toml`` marker (at ``<root>/``) to find the
    environment and overrides. Falls back to a plain :class:`AnchorConfig` for
    an unmarked / external dir.
    """
    dd = _expand(data_dir)
    if dd.name == DATA_DIRNAME:
        marker_path = dd.parent / PROJECT_MARKER_FILENAME
        if marker_path.is_file():
            marker = _safe_toml(marker_path)
            env_name = marker.get("env")
            if env_name:
                env = _load_env(str(env_name))
                if env.initialized:
                    return _layered_config(env, dd, marker)
    return AnchorConfig(data_dir=dd)


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def _meta_from_table(table: Any) -> Meta:
    if not isinstance(table, dict):
        return Meta()
    tags = table.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return Meta(
        name=str(table.get("name", "") or ""),
        description=str(table.get("description", "") or ""),
        tags=tuple(str(t) for t in tags),
    )


def environment_meta(env: Environment) -> Meta:
    if env.config_path is None:
        return Meta()
    return _meta_from_table(_safe_toml(env.config_path).get("meta", {}))


def project_meta(env: Environment, project: str) -> Meta:
    return _meta_from_table(_read_project_marker(env.project_root(project)).get("meta", {}))


# --------------------------------------------------------------------------- #
# Minimal TOML writer (flat scalars + one [meta] table)
# --------------------------------------------------------------------------- #
def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _render_toml(settings: dict[str, Any], meta: Meta | None) -> str:
    lines: list[str] = []
    for key, value in settings.items():
        if value is None:
            continue
        lines.append(f"{key} = {_toml_scalar(value)}")
    if meta is not None and (meta.name or meta.description or meta.tags):
        if lines:
            lines.append("")
        lines.append("[meta]")
        if meta.name:
            lines.append(f"name = {_toml_scalar(meta.name)}")
        if meta.description:
            lines.append(f"description = {_toml_scalar(meta.description)}")
        if meta.tags:
            lines.append(f"tags = {_toml_scalar(list(meta.tags))}")
    return "\n".join(lines) + "\n"


def _write_toml(path: Path, settings: dict[str, Any], meta: Meta | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_toml(settings, meta), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def create_env(
    name: str,
    *,
    settings: dict[str, Any] | None = None,
    meta: Meta | None = None,
) -> Environment:
    """Create environment ``name`` (writes ``env.toml`` + ``projects/``)."""
    validate_env_name(name)
    root = envs_dir() / name
    root.mkdir(parents=True, exist_ok=True)
    (root / PROJECTS_DIRNAME).mkdir(exist_ok=True)
    config_path = root / ENV_CONFIG_FILENAME
    if not config_path.exists():
        _write_toml(config_path, dict(settings or {}), meta)
    return _load_env(name)


def list_env_names() -> list[str]:
    base = envs_dir()
    if not base.is_dir():
        return []
    names: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        try:
            validate_env_name(child.name)
        except ValueError:
            continue
        if (child / ENV_CONFIG_FILENAME).is_file():
            names.append(child.name)
    return names


def create_project(
    env: Environment,
    name: str,
    *,
    root: Path | str | None = None,
    description: str = "",
    tags: tuple[str, ...] = (),
) -> str:
    """Create project ``name`` in ``env``.

    ``root`` is the project folder; defaults to a managed location under the env
    (used by the agent, which has no working folder). ``anchor init`` passes the
    user's folder. Writes the ``anchor.toml`` marker + ``.anchor_data/`` and
    registers ``name`` -> folder.
    """
    validate_project_name(name)
    if not env.initialized:
        raise NoEnvironmentError(env.name)
    project_root = _expand(root) if root is not None else (env.projects_dir / name)
    data_dir = project_root / DATA_DIRNAME
    for sub in PROJECT_SUBDIRS:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    _write_project_marker(
        project_root, env.name, name, {}, Meta(name=name, description=description, tags=tuple(tags))
    )
    register_project(env, name, project_root)
    return name


def ensure_project(env: Environment, name: str) -> Path:
    """Return ``name``'s data dir, creating its subdirs (and marker) if absent."""
    data_dir = env.project_dir(name)
    for sub in PROJECT_SUBDIRS:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    marker = env.project_root(name) / PROJECT_MARKER_FILENAME
    if env.initialized and not marker.is_file() and data_dir != LEGACY_DATA_DIR:
        _write_project_marker(env.project_root(name), env.name, name, {}, None)
        register_project(env, name, env.project_root(name))
    return data_dir


def set_environment_description(env: Environment, description: str) -> None:
    """Update an environment's description (announced to agents for routing)."""
    if not env.initialized:
        raise NoEnvironmentError(env.name)
    settings = _flat_settings(_safe_toml(env.config_path))
    existing = environment_meta(env)
    meta = Meta(name=existing.name or env.name, description=description, tags=existing.tags)
    _write_toml(env.config_path, settings, meta)


def set_project_description(env: Environment, name: str, description: str) -> None:
    """Update a project's description in its ``anchor.toml`` marker."""
    validate_project_name(name)
    root = env.project_root(name)
    marker = _read_project_marker(root)
    settings = _flat_settings(marker)
    settings.setdefault("env", env.name)
    settings.setdefault("name", name)
    existing = _meta_from_table(marker.get("meta", {}))
    bind = {k: v for k, v in settings.items() if k in ("env", "name")}
    overrides = {k: v for k, v in settings.items() if k not in ("env", "name")}
    _write_toml(
        root / PROJECT_MARKER_FILENAME,
        {**bind, **overrides},
        Meta(name=existing.name or name, description=description, tags=existing.tags),
    )


def move_project(from_env: Environment, name: str, to_env: Environment) -> dict[str, Any]:
    """Rebind project ``name`` from one environment to another.

    A *managed* project (folder under the env's ``projects/``) is physically
    relocated into the new env's ``projects/``; an *external* project (a folder
    anywhere, created with ``anchor init``) stays put and only its
    ``anchor.toml`` marker + registry entry are rebound. Crossing a trust
    boundary is deliberate; callers should confirm the zone change first.
    """
    validate_project_name(name)
    if not to_env.initialized:
        raise NoEnvironmentError(to_env.name)
    if not from_env.project_exists(name):
        raise NoProjectError(name, from_env.list_project_names())
    if to_env.project_exists(name):
        raise FileExistsError(
            f"project {name!r} already exists in environment {to_env.name!r}"
        )
    root = from_env.project_root(name)
    is_managed = _expand(root).parent == _expand(from_env.projects_dir)
    new_root = (to_env.projects_dir / name) if is_managed else root
    marker = _read_project_marker(root)
    settings = {k: v for k, v in _flat_settings(marker).items() if k not in ("env", "name")}
    meta = _meta_from_table(marker.get("meta", {}))
    if is_managed and _expand(new_root) != _expand(root):
        _expand(new_root).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_expand(root)), str(_expand(new_root)))
    _write_project_marker(new_root, to_env.name, name, settings, meta)
    unregister_project(from_env, name)
    register_project(to_env, name, new_root)
    return {"project": name, "from": from_env.name, "to": to_env.name, "folder": str(new_root)}


def _count_documents(data_dir: Path) -> int:
    """Count ingested documents in a project's data dir.

    A document is one ingested PDF (its ``bronze/<file>``); ``silver``/``gold``
    are derived. Counted from the filesystem so this stays in ``infra`` and does
    not import the ``anchor_pdfs`` extension (the canvas/infra layering rule).
    """
    bronze = _expand(data_dir) / "bronze"
    if not bronze.is_dir():
        return 0
    return sum(1 for child in bronze.iterdir() if child.is_file())


def _count_canvases(data_dir: Path) -> int:
    """Count canvases in a project's data dir (one ``canvases/<slug>/`` each)."""
    canvases = _expand(data_dir) / "canvases"
    if not canvases.is_dir():
        return 0
    return sum(1 for child in canvases.iterdir() if child.is_dir())


def project_contents(env: Environment, name: str) -> dict[str, int]:
    """Return ``{"documents": N, "canvases": M}`` for project ``name``."""
    validate_project_name(name)
    data_dir = env.project_dir(name)
    return {
        "documents": _count_documents(data_dir),
        "canvases": _count_canvases(data_dir),
    }


def _is_managed(env: Environment, root: Path) -> bool:
    """True when ``root`` is a folder Anchor manages under the env's ``projects/``.

    A managed project's folder name *is* its project name (it is auto-discovered
    by scanning ``projects/``), so removing/renaming it touches the folder. An
    external project (created with ``anchor init`` in the user's own folder) is
    addressed only through the registry + marker; its folder is the user's.
    """
    return _expand(root).parent == _expand(env.projects_dir)


def remove_project(
    env: Environment,
    name: str,
    *,
    delete_data: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Remove project ``name`` from ``env``. Never touches any other project.

    Always deregisters the project from the env's ``projects.toml``. A *managed*
    project (its folder lives under the env's ``projects/``) is auto-discovered
    from disk, so its folder is removed too — otherwise it would re-appear in
    ``list_projects``. An *external* ``anchor init`` project keeps its folder by
    default (it is the user's working directory); ``delete_data=True`` then also
    wipes that folder's ``.anchor_data/`` and its ``anchor.toml`` marker. Refuses
    a project that still has documents/canvases unless ``force=True``.
    """
    validate_project_name(name)
    if not env.initialized:
        raise NoEnvironmentError(env.name)
    if not env.project_exists(name):
        raise NoProjectError(name, env.list_project_names())
    contents = project_contents(env, name)
    if not force and (contents["documents"] or contents["canvases"]):
        raise ProjectNotEmptyError(name, contents["documents"], contents["canvases"])

    root = _expand(env.project_root(name))
    data_dir = _expand(env.project_dir(name))
    managed = _is_managed(env, root)
    # Never delete the legacy ~/anchor-data via a project remove; that is
    # `anchor migrate` territory, not a per-project cleanup.
    is_legacy = data_dir == _expand(LEGACY_DATA_DIR)
    deleted_data = False
    if managed:
        # The managed folder exists only to hold this project; drop it whole so
        # the disk scan no longer re-discovers it. (Empty by default, or
        # non-empty under --force.)
        if not is_legacy and root.is_dir():
            shutil.rmtree(root)
            deleted_data = True
    elif delete_data and not is_legacy:
        # External project: leave the user's folder, wipe only Anchor's bits.
        if data_dir.is_dir():
            shutil.rmtree(data_dir)
            deleted_data = True
        marker = root / PROJECT_MARKER_FILENAME
        if marker.is_file():
            marker.unlink()
    unregister_project(env, name)
    return {
        "removed": name,
        "environment": env.name,
        "deleted_data": deleted_data,
        "folder": str(root),
    }


def rename_project(env: Environment, old: str, new: str) -> dict[str, Any]:
    """Rename project ``old`` to ``new`` in ``env``.

    Updates the registry key and the project's ``anchor.toml`` (its ``name`` and
    ``[meta].name`` when that still mirrors ``old``). A *managed* project's
    folder is renamed under ``projects/`` to match (its folder name is its
    identity); an *external* ``anchor init`` project keeps its folder path and
    only its marker + registry entry are rebound. Errors if ``new`` exists.
    """
    validate_project_name(old)
    validate_project_name(new)
    if not env.initialized:
        raise NoEnvironmentError(env.name)
    if not env.project_exists(old):
        raise NoProjectError(old, env.list_project_names())
    if new == old:
        return {"renamed": old, "to": new, "folder": str(_expand(env.project_root(old)))}
    if env.project_exists(new):
        raise FileExistsError(
            f"project {new!r} already exists in environment {env.name!r}"
        )

    root = _expand(env.project_root(old))
    marker = _read_project_marker(root)
    settings = {k: v for k, v in _flat_settings(marker).items() if k not in ("env", "name")}
    existing = _meta_from_table(marker.get("meta", {}))
    # Carry description/tags forward; rename the meta name only when it still
    # mirrors the old project name (a user-set display name is left untouched).
    meta_name = new if (not existing.name or existing.name == old) else existing.name
    meta = Meta(name=meta_name, description=existing.description, tags=existing.tags)

    new_root = (env.projects_dir / new) if _is_managed(env, root) else root
    if _expand(new_root) != root:
        _expand(new_root).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), str(_expand(new_root)))
    _write_project_marker(new_root, env.name, new, settings, meta)
    unregister_project(env, old)
    register_project(env, new, new_root)
    return {"renamed": old, "to": new, "folder": str(_expand(new_root))}


__all__ = [
    "ANCHOR_HOME",
    "ENVS_DIRNAME",
    "ENV_CONFIG_FILENAME",
    "PROJECT_MARKER_FILENAME",
    "REGISTRY_FILENAME",
    "DATA_DIRNAME",
    "PROJECTS_DIRNAME",
    "DEFAULT_ENV",
    "DEFAULT_PROJECT",
    "DEFAULT_ENV_FILE",
    "LEGACY_DATA_DIR",
    "ENV_VAR",
    "PROJECT_VAR",
    "Environment",
    "ResolvedProject",
    "Meta",
    "NoEnvironmentError",
    "NoProjectError",
    "ProjectNotEmptyError",
    "anchor_home",
    "envs_dir",
    "default_env_name",
    "set_default_env",
    "get_use",
    "set_use",
    "resolve_environment",
    "resolve_project",
    "resolve_project_config",
    "config_for_data_dir",
    "environment_meta",
    "project_meta",
    "create_env",
    "list_env_names",
    "create_project",
    "ensure_project",
    "register_project",
    "unregister_project",
    "set_project_description",
    "set_environment_description",
    "move_project",
    "remove_project",
    "rename_project",
    "project_contents",
]
