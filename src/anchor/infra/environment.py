"""Environments and projects — the two-level resolution model (anchor#120).

An **environment** is the directory you ``anchor init``. It holds the
configuration (provider, privacy, models, ingest mode) and any number of
**projects**, and it is the trust / egress boundary. A **project** is a unit
inside an environment that owns its own *documents* (bronze/silver/gold) and
*canvases*; it inherits the environment config unless it overrides.

```
<environment>/                 # `anchor init`, or the global default ~/.anchor
├── config.toml                # single source of truth: provider, models, env metadata
└── projects/
    └── <name>/                # a project: its own documents + canvases
        ├── project.toml        # optional: metadata + rare config overrides
        ├── bronze/ silver/ gold/
        └── canvases/<slug>/
```

Resolution turns ``(environment, project)`` into a concrete ``data_dir`` plus a
layered :class:`~anchor.infra.config.AnchorConfig`. The existing stores already
take a single ``data_dir`` root, so a project is simply that root pointed at
``projects/<name>/`` — no store changes needed.

**Back-compat.** A legacy ``anchor init`` directory (marked by an
``anchor.toml`` rather than a ``config.toml``) is treated as an environment with
one implicit ``default`` project whose documents live at the ``data_dir`` the
old config named. The global default ``~/.anchor`` falls back to today's
``~/anchor-data`` as its ``default`` project until the user migrates, so an
existing install keeps working with no action.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anchor.core.ids import validate_project_name
from anchor.infra.config import (
    CONFIG_FILENAME,
    AnchorConfig,
    _load_toml_tolerant,
)

#: The global default environment, used when no ``--env`` / ``ANCHOR_ENV`` is
#: given and no environment is found by walking up from the current directory.
GLOBAL_ENV_DIR = Path.home() / ".anchor"

#: An environment is marked by this file at its root.
ENV_CONFIG_FILENAME = "config.toml"

#: A project's optional per-project config / metadata file.
PROJECT_CONFIG_FILENAME = "project.toml"

#: Projects live under ``<environment>/projects/``.
PROJECTS_DIRNAME = "projects"

#: The implicit project used when none is named (and the migration target for a
#: legacy single-corpus install).
DEFAULT_PROJECT = "default"

#: Today's pre-#120 single data directory. Kept working as the global default
#: environment's ``default`` project until ``anchor migrate`` relocates it.
LEGACY_DATA_DIR = Path.home() / "anchor-data"

#: Environment variable that pins the active environment (peer of ``--env``).
ENV_VAR = "ANCHOR_ENV"

#: The per-project storage sub-directories created on ``create_project``.
PROJECT_SUBDIRS = ("bronze", "silver", "gold", "canvases")


class NoEnvironmentError(Exception):
    """The selected environment directory is not an initialized environment."""

    def __init__(self, root: Path) -> None:
        self.root = root
        super().__init__(
            f"{root} is not an Anchor environment (no {ENV_CONFIG_FILENAME}). "
            "Run create_environment to set it up, or point --env at an existing one."
        )


class NoProjectError(Exception):
    """A project was required but is missing or unnamed."""

    def __init__(self, name: str | None, available: list[str]) -> None:
        self.name = name
        self.available = available
        if name:
            msg = f"project {name!r} does not exist. "
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

    It is part of the agent's tool surface: ``list_projects`` returns
    ``name`` + ``description`` so the agent can pick the right project without
    re-asking the user. An environment's ``description`` should name its trust
    context ("company Azure tenant, confidential").
    """

    name: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Environment:
    """A resolved environment: the trust boundary that holds projects.

    ``config_path`` is the file that marks it (``config.toml`` for a #120
    environment, or a legacy ``anchor.toml``); ``None`` means the directory is
    not an initialized environment. ``legacy`` / ``legacy_data_dir`` carry the
    back-compat single ``default`` project.
    """

    root: Path
    config_path: Path | None = None
    legacy: bool = False
    legacy_data_dir: Path | None = None

    @property
    def initialized(self) -> bool:
        """True when the directory is a real environment (has a config file)."""
        return self.config_path is not None

    @property
    def projects_dir(self) -> Path:
        return self.root / PROJECTS_DIRNAME

    def project_dir(self, name: str) -> Path:
        """The storage root for ``name`` (where its bronze/.../canvases live)."""
        validate_project_name(name)
        if self.legacy and name == DEFAULT_PROJECT and self.legacy_data_dir is not None:
            return self.legacy_data_dir
        return self.projects_dir / name

    def project_exists(self, name: str) -> bool:
        try:
            return self.project_dir(name).is_dir()
        except ValueError:
            return False

    def list_project_names(self) -> list[str]:
        """Enumerate projects from disk (no registry). Sorted, deduplicated."""
        names: list[str] = []
        if self.legacy and self.legacy_data_dir is not None and self.legacy_data_dir.is_dir():
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
# Resolution
# --------------------------------------------------------------------------- #
def _safe_toml(path: Path) -> dict[str, Any]:
    try:
        return _load_toml_tolerant(path)
    except Exception:  # noqa: BLE001 — a broken config must not brick resolution
        return {}


def _expand(value: Any) -> Path:
    return Path(os.path.expandvars(str(value))).expanduser()


def _load_environment(root: Path) -> Environment:
    """Inspect ``root`` and classify it as a #120 / legacy / uninitialized env."""
    root = _expand(root)
    cfg = root / ENV_CONFIG_FILENAME
    legacy_cfg = root / CONFIG_FILENAME  # anchor.toml
    if cfg.is_file():
        return Environment(root=root, config_path=cfg)
    if legacy_cfg.is_file():
        data = _safe_toml(legacy_cfg)
        raw = data.get("data_dir")
        legacy_dir = _expand(raw) if raw else root / "anchor-data"
        return Environment(
            root=root, config_path=legacy_cfg, legacy=True, legacy_data_dir=legacy_dir
        )
    if root == GLOBAL_ENV_DIR and LEGACY_DATA_DIR.is_dir():
        # An existing user with ~/anchor-data but no ~/.anchor yet keeps it as
        # the global default's `default` project until `anchor migrate` runs.
        return Environment(
            root=root, config_path=None, legacy=True, legacy_data_dir=LEGACY_DATA_DIR
        )
    return Environment(root=root, config_path=None)


def _walk_up_for_env() -> Path | None:
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        if (directory / ENV_CONFIG_FILENAME).is_file() or (directory / CONFIG_FILENAME).is_file():
            return directory
    return None


def resolve_environment(env: Path | str | None = None) -> Environment:
    """Resolve the active environment.

    Precedence: explicit ``env`` (the ``--env`` flag) > ``ANCHOR_ENV`` >
    walk-up from the current directory to a ``config.toml`` / legacy
    ``anchor.toml`` > the global default ``~/.anchor``.
    """
    if env is not None:
        return _load_environment(Path(env))
    pinned = os.environ.get(ENV_VAR)
    if pinned:
        return _load_environment(Path(pinned))
    found = _walk_up_for_env()
    return _load_environment(found if found is not None else GLOBAL_ENV_DIR)


def _flat_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Top-level scalar/list settings only — drops ``[meta]`` and other tables."""
    return {k: v for k, v in data.items() if not isinstance(v, dict)}


def resolve_project_config(env: Environment, project: str) -> AnchorConfig:
    """Layer the config for ``project``: env config.toml < project.toml < env/flags.

    ``data_dir`` is forced to the resolved project directory — storage location
    is structural, not a setting a stray ``ANCHOR_DATA_DIR`` should move.
    """
    data_dir = env.project_dir(project)
    layers: dict[str, Any] = {}
    if env.config_path is not None:
        layers.update(_flat_settings(_safe_toml(env.config_path)))
    project_toml = env.project_dir(project) / PROJECT_CONFIG_FILENAME
    if project_toml.is_file():
        layers.update(_flat_settings(_safe_toml(project_toml)))
    layers.pop("data_dir", None)
    return AnchorConfig.from_layers(layer_values=layers, data_dir=data_dir)


def resolve_project(
    env: Path | str | None = None,
    project: str = DEFAULT_PROJECT,
    *,
    require_exists: bool = False,
) -> ResolvedProject:
    """Resolve ``(environment, project)`` to storage dir + layered config.

    With ``require_exists`` the project directory must already be present
    (raises :class:`NoProjectError`), otherwise resolution is path-only and the
    caller may create the project on first write. The ``default`` project in a
    legacy / global-default environment always resolves, mirroring today's
    single-corpus behavior.
    """
    environment = resolve_environment(env)
    validate_project_name(project)
    if require_exists and not environment.project_exists(project):
        legacy_default = (
            environment.legacy
            and project == DEFAULT_PROJECT
            and environment.legacy_data_dir is not None
        )
        if not legacy_default:
            raise NoProjectError(project, environment.list_project_names())
    config = resolve_project_config(environment, project)
    return ResolvedProject(
        environment=environment,
        name=project,
        data_dir=environment.project_dir(project),
        config=config,
    )


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
def init_environment(
    root: Path | str,
    *,
    settings: dict[str, Any] | None = None,
    meta: Meta | None = None,
) -> Environment:
    """Create an environment at ``root`` (writes ``config.toml`` + ``projects/``)."""
    env_root = _expand(root)
    env_root.mkdir(parents=True, exist_ok=True)
    (env_root / PROJECTS_DIRNAME).mkdir(exist_ok=True)
    config_path = env_root / ENV_CONFIG_FILENAME
    if not config_path.exists():
        _write_toml(config_path, dict(settings or {}), meta)
    return _load_environment(env_root)


def create_project(
    env: Environment,
    name: str,
    *,
    description: str = "",
    tags: tuple[str, ...] = (),
) -> str:
    """Create ``name`` in ``env`` (storage subdirs + optional metadata)."""
    validate_project_name(name)
    if not env.initialized:
        raise NoEnvironmentError(env.root)
    project_dir = env.project_dir(name)
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


__all__ = [
    "GLOBAL_ENV_DIR",
    "ENV_CONFIG_FILENAME",
    "PROJECT_CONFIG_FILENAME",
    "DEFAULT_PROJECT",
    "LEGACY_DATA_DIR",
    "ENV_VAR",
    "Environment",
    "ResolvedProject",
    "Meta",
    "NoEnvironmentError",
    "NoProjectError",
    "resolve_environment",
    "resolve_project",
    "resolve_project_config",
    "environment_meta",
    "project_meta",
    "init_environment",
    "create_project",
    "ensure_project",
    "set_project_description",
]
