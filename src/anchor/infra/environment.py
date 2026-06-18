"""Environments and projects — the named-profile model.

## Terms (defined once, used everywhere)

- **environment** (env): a *named, reusable configuration profile* — the
  provider, models, and data **zone**. An environment is the **trust / egress
  boundary**: it decides where a corpus's content may go. Environments live in
  a central registry at ``~/.anchor/envs/<name>/`` and are managed with
  ``anchor env``. Mental model: an ``nvm`` version (named, listable, picked by
  name) that also carries a privacy policy.

- **project**: a single *corpus* (its ingested documents) plus its *canvases*.
  A project is **contained inside one environment** at
  ``~/.anchor/envs/<env>/projects/<project>/`` and inherits that environment's
  configuration. Containment is the binding: a project cannot be read under a
  different environment, and moving it across environments is a deliberate,
  zone-confirmed ``anchor project move``.

- **documents**: a project's ingested corpus on disk (``bronze`` / ``silver``
  / ``gold`` stages).

- **canvas**: a board inside a project (the code's "workspace").

- **zone**: the data egress / privacy boundary (on-host / public cloud / your
  tenant). A property of the *environment*, inherited by its projects.

- **default environment / default project**: used when a call names neither.
  The default environment name lives in ``~/.anchor/default`` (falls back to
  ``"local"``); the default project is ``"default"``.

## On disk

```
~/.anchor/
├── default                      # the default environment's name (one line)
├── use.toml                     # optional CLI session selection (env + project)
└── envs/
    └── <env>/
        ├── env.toml             # the profile: provider/models/zone + [meta]
        └── projects/
            └── <project>/        # documents + canvases, inherits env config
                ├── project.toml   # optional: metadata + rare overrides
                ├── bronze/ silver/ gold/
                └── canvases/<slug>/
```

The environment's ``projects/`` directory *is* the project list — there is no
separate registry. Storage location is structural (the project directory); no
``data_dir`` key is written. Secrets are never in a profile — the API key stays
in ``ANCHOR_OPENAI_API_KEY`` / a gitignored ``.env``.

## Resolution

``(environment, project)`` resolves to a concrete ``data_dir`` plus a layered
:class:`~anchor.infra.config.AnchorConfig`:

```
env name : explicit --env > ANCHOR_ENV > `anchor use` selection > default env
project  : explicit --project > ANCHOR_PROJECT > `anchor use` selection > "default"
config   : env env.toml < project project.toml < ANCHOR_* env vars / flags
data_dir : ~/.anchor/envs/<env>/projects/<project>/
```

Back-compat: until ``anchor migrate`` runs, the ``default`` environment's
``default`` project resolves to today's ``~/anchor-data`` when that exists and
``envs/default-env/projects/default/`` does not.
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

#: Projects live under ``<env>/projects/``.
PROJECTS_DIRNAME = "projects"

#: A project's optional per-project config / metadata file.
PROJECT_CONFIG_FILENAME = "project.toml"

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

#: Today's pre-rework single data directory. Folded into
#: ``envs/<default>/projects/default/`` by ``anchor migrate``; honored as the
#: default project's location until then. Monkeypatched in tests.
LEGACY_DATA_DIR = Path.home() / "anchor-data"

#: The per-project storage sub-directories created on ``create_project``.
PROJECT_SUBDIRS = ("bronze", "silver", "gold", "canvases")


class NoEnvironmentError(Exception):
    """The named environment is not set up (no ``env.toml``)."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"environment {name!r} is not set up. Create it with "
            f"`anchor env create {name}` (or `anchor init`)."
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


@dataclass(frozen=True)
class Meta:
    """User-editable metadata for an environment or a project.

    Part of the agent's tool surface: ``list_projects`` returns ``name`` +
    ``description`` so the agent can pick the right project without re-asking.
    An environment's ``description`` should name its trust context ("company
    Azure tenant, confidential").
    """

    name: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Environment:
    """A resolved environment: a named profile = the trust boundary.

    ``root`` is ``~/.anchor/envs/<name>/``. ``config_path`` is its ``env.toml``,
    or ``None`` when the environment is not set up yet.
    """

    name: str
    root: Path
    config_path: Path | None = None

    @property
    def initialized(self) -> bool:
        """True when the environment exists (has an ``env.toml``)."""
        return self.config_path is not None

    @property
    def projects_dir(self) -> Path:
        return self.root / PROJECTS_DIRNAME

    def project_dir(self, project: str) -> Path:
        """Storage root for ``project`` (where its bronze/.../canvases live)."""
        validate_project_name(project)
        explicit = self.projects_dir / project
        # Back-compat: the default env's default project keeps using today's
        # ~/anchor-data until `anchor migrate` folds it in (then projects/ wins).
        if (
            project == DEFAULT_PROJECT
            and self.name == DEFAULT_ENV
            and not explicit.is_dir()
            and LEGACY_DATA_DIR.is_dir()
        ):
            return LEGACY_DATA_DIR
        return explicit

    def project_exists(self, project: str) -> bool:
        try:
            return self.project_dir(project).is_dir()
        except ValueError:
            return False

    def list_project_names(self) -> list[str]:
        """Enumerate projects (an ``ls`` of ``projects/``). Sorted, deduped."""
        names: list[str] = []
        legacy = self.project_dir(DEFAULT_PROJECT)
        if (
            self.name == DEFAULT_ENV
            and legacy == LEGACY_DATA_DIR
            and legacy.is_dir()
        ):
            names.append(DEFAULT_PROJECT)
        if self.projects_dir.is_dir():
            for child in sorted(self.projects_dir.iterdir()):
                if not child.is_dir() or child.name in names:
                    continue
                try:
                    validate_project_name(child.name)
                except ValueError:
                    continue
                names.append(child.name)
        return names


@dataclass(frozen=True)
class ResolvedProject:
    """A project resolved to its concrete storage dir and layered config."""

    environment: Environment
    name: str
    data_dir: Path
    config: AnchorConfig


# --------------------------------------------------------------------------- #
# Paths + small IO helpers
# --------------------------------------------------------------------------- #
def anchor_home() -> Path:
    return ANCHOR_HOME


def envs_dir() -> Path:
    return ANCHOR_HOME / ENVS_DIRNAME


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
    """Read the CLI session selection (``anchor use``), if any."""
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
    """Resolve the active environment by name.

    Precedence: explicit ``env`` (the ``--env`` value) > ``ANCHOR_ENV`` >
    the ``anchor use`` selection > the default environment.
    """
    name = env or os.environ.get(ENV_VAR) or get_use().get("env") or default_env_name()
    validate_env_name(name)
    return _load_env(name)


def _load_env_dotenv(env: Environment) -> None:
    """Load ``<env>/.env`` into the process env (ANCHOR_* keys, if unset).

    Commands are name-addressed, so the gitignored ``.env`` that holds the API
    key lives next to the env profile, not in the cwd. Load it here so a keyed
    provider works from anywhere. Only fills keys that are not already set, so
    an explicit shell ``ANCHOR_OPENAI_API_KEY`` still wins.
    """
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


def resolve_project_config(env: Environment, project: str) -> AnchorConfig:
    """Layer config for ``project``: env env.toml < project.toml < ANCHOR_*.

    ``data_dir`` is forced to the project directory — storage is structural,
    decided by containment, not by an ``ANCHOR_DATA_DIR``.
    """
    _load_env_dotenv(env)
    data_dir = env.project_dir(project)
    layers: dict[str, Any] = {}
    if env.config_path is not None:
        layers.update(_flat_settings(_safe_toml(env.config_path)))
    project_toml = data_dir / PROJECT_CONFIG_FILENAME
    if project_toml.is_file():
        layers.update(_flat_settings(_safe_toml(project_toml)))
    layers.pop("data_dir", None)
    return AnchorConfig.from_layers(layer_values=layers, data_dir=data_dir)


def resolve_project(
    env: str | None = None,
    project: str | None = None,
    *,
    require_exists: bool = False,
) -> ResolvedProject:
    """Resolve ``(environment, project)`` to storage dir + layered config.

    Project precedence: explicit ``project`` > ``ANCHOR_PROJECT`` > the
    ``anchor use`` selection > ``"default"``. With ``require_exists`` a missing
    project raises :class:`NoProjectError`.
    """
    environment = resolve_environment(env)
    name = project or os.environ.get(PROJECT_VAR) or get_use().get("project") or DEFAULT_PROJECT
    validate_project_name(name)
    if require_exists and not environment.project_exists(name):
        raise NoProjectError(name, environment.list_project_names())
    return ResolvedProject(
        environment=environment,
        name=name,
        data_dir=environment.project_dir(name),
        config=resolve_project_config(environment, name),
    )


def config_for_data_dir(data_dir: Path | str) -> AnchorConfig:
    """Layer config for a ``data_dir`` that is a project under an environment.

    A project's storage dir is structurally ``<env>/projects/<name>``. When
    ``data_dir`` matches that shape and the environment has an ``env.toml``,
    return the layered project config. Otherwise (an explicit external dir, or
    today's ``~/anchor-data``) return a plain :class:`AnchorConfig` pinned to
    ``data_dir`` (which still honors a legacy ``anchor.toml`` walk-up). This
    lets every CLI command keep passing a bare ``data_dir`` while environments
    resolve their provider/models correctly.
    """
    dd = _expand(data_dir)
    if dd.parent.name == PROJECTS_DIRNAME:
        env_root = dd.parent.parent
        cfg = env_root / ENV_CONFIG_FILENAME
        if cfg.is_file():
            env = Environment(name=env_root.name, root=env_root, config_path=cfg)
            return resolve_project_config(env, dd.name)
    return AnchorConfig(data_dir=dd)


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def _meta_from_toml(path: Path | None) -> Meta:
    if path is None or not path.is_file():
        return Meta()
    table = _safe_toml(path).get("meta", {})
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
    return _meta_from_toml(env.config_path)


def project_meta(env: Environment, project: str) -> Meta:
    return _meta_from_toml(env.project_dir(project) / PROJECT_CONFIG_FILENAME)


# --------------------------------------------------------------------------- #
# Minimal TOML writer (controlled schema: flat scalars + one [meta] table)
# --------------------------------------------------------------------------- #
def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        inner = ", ".join(_toml_scalar(v) for v in value)
        return f"[{inner}]"
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
# Lifecycle (pure helpers shared by the CLI and MCP adapters)
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
    """Enumerate environments (an ``ls`` of ``envs/``)."""
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
    description: str = "",
    tags: tuple[str, ...] = (),
) -> str:
    """Create project ``name`` under ``env`` (storage subdirs + metadata)."""
    validate_project_name(name)
    if not env.initialized:
        raise NoEnvironmentError(env.name)
    project_dir = env.projects_dir / name
    for sub in PROJECT_SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    if description or tags:
        _write_toml(
            project_dir / PROJECT_CONFIG_FILENAME,
            {},
            Meta(name=name, description=description, tags=tuple(tags)),
        )
    return name


def ensure_project(env: Environment, name: str) -> Path:
    """Return ``name``'s storage dir, creating its subdirs if absent."""
    project_dir = env.project_dir(name)
    for sub in PROJECT_SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


def set_project_description(env: Environment, name: str, description: str) -> None:
    """Update a project's description, preserving its other config/metadata."""
    validate_project_name(name)
    project_toml = env.project_dir(name) / PROJECT_CONFIG_FILENAME
    settings = _flat_settings(_safe_toml(project_toml)) if project_toml.is_file() else {}
    existing = _meta_from_toml(project_toml)
    meta = Meta(name=existing.name or name, description=description, tags=existing.tags)
    _write_toml(project_toml, settings, meta)


def move_project(from_env: Environment, name: str, to_env: Environment) -> dict[str, Any]:
    """Move project ``name`` from one environment to another (a real move).

    Crossing a trust boundary is deliberate: the corpus is physically
    relocated. Callers should confirm the zone change first.
    """
    validate_project_name(name)
    if not to_env.initialized:
        raise NoEnvironmentError(to_env.name)
    src = from_env.project_dir(name)
    if not src.is_dir():
        raise NoProjectError(name, from_env.list_project_names())
    dst = to_env.projects_dir / name
    if dst.exists():
        raise FileExistsError(
            f"project {name!r} already exists in environment {to_env.name!r}"
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"project": name, "from": from_env.name, "to": to_env.name, "data_dir": str(dst)}


__all__ = [
    "ANCHOR_HOME",
    "ENVS_DIRNAME",
    "ENV_CONFIG_FILENAME",
    "PROJECTS_DIRNAME",
    "PROJECT_CONFIG_FILENAME",
    "DEFAULT_ENV",
    "DEFAULT_PROJECT",
    "LEGACY_DATA_DIR",
    "ENV_VAR",
    "PROJECT_VAR",
    "Environment",
    "ResolvedProject",
    "Meta",
    "NoEnvironmentError",
    "NoProjectError",
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
    "set_project_description",
    "move_project",
]
