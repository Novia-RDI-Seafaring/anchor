"""On-disk model and codecs for ANCHOR environments and projects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anchor.core.ids import validate_project_name
from anchor.infra.config import AnchorConfig, _load_toml_tolerant, expand_env_vars

ANCHOR_HOME = Path.home() / ".anchor"
ENVS_DIRNAME = "envs"
ENV_CONFIG_FILENAME = "env.toml"
PROJECTS_DIRNAME = "projects"
PROJECT_MARKER_FILENAME = "anchor.toml"
REGISTRY_FILENAME = "projects.toml"
DATA_DIRNAME = ".anchor_data"
DEFAULT_ENV_FILE = "default"
USE_FILE = "use.toml"
DEFAULT_ENV = "local"
DEFAULT_PROJECT = "default"
ENV_VAR = "ANCHOR_ENV"
PROJECT_VAR = "ANCHOR_PROJECT"
LEGACY_DATA_DIR = Path.home() / "anchor-data"
PROJECT_SUBDIRS = ("bronze", "silver", "gold", "canvases")


class NoEnvironmentError(Exception):
    """The named environment is not set up."""

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
        message = (
            f"project {name!r} does not exist in this environment. "
            if name
            else "this call needs a project. "
        )
        if available:
            message += f"Create one with create_project(name), or pick one: {available}."
        else:
            message += "Create one with create_project(name)."
        super().__init__(message)


class ProjectNotEmptyError(Exception):
    """A project still has content and removal was not forced."""

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
    """User-editable metadata for an environment or project."""

    name: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()


def _safe_toml(path: Path) -> dict[str, Any]:
    try:
        return _load_toml_tolerant(path)
    except Exception:  # noqa: BLE001 - broken config must not block discovery
        return {}


def _expand(value: Any) -> Path:
    return Path(expand_env_vars(str(value))).expanduser()


def _flat_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Return top-level scalar and list settings, excluding tables."""
    return {key: value for key, value in data.items() if not isinstance(value, dict)}


@dataclass(frozen=True)
class Environment:
    """A resolved named configuration profile and trust boundary."""

    name: str
    root: Path
    config_path: Path | None = None
    legacy_data_dir: Path = field(
        default_factory=lambda: LEGACY_DATA_DIR,
        repr=False,
        compare=False,
    )

    @property
    def initialized(self) -> bool:
        return self.config_path is not None

    @property
    def projects_dir(self) -> Path:
        return self.root / PROJECTS_DIRNAME

    @property
    def registry_path(self) -> Path:
        return self.root / REGISTRY_FILENAME

    def _registry(self) -> dict[str, Path]:
        return _read_registry(self.root)

    def project_root(self, project: str) -> Path:
        validate_project_name(project)
        return self._registry().get(project, self.projects_dir / project)

    def project_dir(self, project: str) -> Path:
        validate_project_name(project)
        registered = self._registry().get(project)
        if registered is not None:
            return registered / DATA_DIRNAME
        managed = self.projects_dir / project
        if (
            project == DEFAULT_PROJECT
            and self.name == DEFAULT_ENV
            and not managed.is_dir()
            and self.legacy_data_dir.is_dir()
        ):
            return self.legacy_data_dir
        return managed / DATA_DIRNAME

    def project_exists(self, project: str) -> bool:
        try:
            validate_project_name(project)
        except ValueError:
            return False
        return project in self._registry() or self.project_dir(project).is_dir()

    def list_project_names(self) -> list[str]:
        names = list(self._registry())
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
            and self.project_dir(DEFAULT_PROJECT) == self.legacy_data_dir
            and self.legacy_data_dir.is_dir()
        ):
            names.append(DEFAULT_PROJECT)
        return sorted(names)


@dataclass(frozen=True)
class ResolvedProject:
    """A project resolved to its data directory and layered config."""

    environment: Environment
    name: str
    data_dir: Path
    config: AnchorConfig


def _read_registry(env_root: Path) -> dict[str, Path]:
    table = _safe_toml(_expand(env_root) / REGISTRY_FILENAME).get("projects", {})
    if not isinstance(table, dict):
        return {}
    return {
        str(key): _expand(value)
        for key, value in table.items()
        if isinstance(value, str)
    }


def _write_registry(env_root: Path, mapping: dict[str, Path]) -> None:
    root = _expand(env_root)
    root.mkdir(parents=True, exist_ok=True)
    lines = ["[projects]"]
    for name, path in sorted(mapping.items()):
        lines.append(f"{_toml_scalar(name)} = {_toml_scalar(str(path))}")
    (root / REGISTRY_FILENAME).write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def register_project(env: Environment, name: str, root: Path | str) -> None:
    validate_project_name(name)
    registry = _read_registry(env.root)
    registry[name] = _expand(root)
    _write_registry(env.root, registry)


def unregister_project(env: Environment, name: str) -> None:
    registry = _read_registry(env.root)
    if registry.pop(name, None) is not None:
        _write_registry(env.root, registry)


def _write_project_marker(
    root: Path,
    env_name: str,
    name: str,
    settings: dict[str, Any],
    meta: Meta | None,
) -> None:
    project_root = _expand(root)
    project_root.mkdir(parents=True, exist_ok=True)
    fields: dict[str, Any] = {"env": env_name, "name": name, **settings}
    _write_toml(project_root / PROJECT_MARKER_FILENAME, fields, meta)


def _read_project_marker(root: Path) -> dict[str, Any]:
    return _safe_toml(_expand(root) / PROJECT_MARKER_FILENAME)


def _walk_up_for_project(start: Path | None = None) -> Path | None:
    """Find the nearest ancestor containing an ``anchor.toml`` marker."""
    current = start or Path.cwd()
    for directory in (current, *current.parents):
        if (directory / PROJECT_MARKER_FILENAME).is_file():
            return directory
    return None


def _meta_from_table(table: Any) -> Meta:
    if not isinstance(table, dict):
        return Meta()
    tags = table.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return Meta(
        name=str(table.get("name", "") or ""),
        description=str(table.get("description", "") or ""),
        tags=tuple(str(tag) for tag in tags),
    )


def environment_meta(env: Environment) -> Meta:
    if env.config_path is None:
        return Meta()
    return _meta_from_table(_safe_toml(env.config_path).get("meta", {}))


def project_meta(env: Environment, project: str) -> Meta:
    marker = _read_project_marker(env.project_root(project))
    return _meta_from_table(marker.get("meta", {}))


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _render_toml(settings: dict[str, Any], meta: Meta | None) -> str:
    lines = [
        f"{key} = {_toml_scalar(value)}"
        for key, value in settings.items()
        if value is not None
    ]
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
