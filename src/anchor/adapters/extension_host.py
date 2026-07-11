"""Shared OIP manifest discovery for adapter entry points.

The host centralizes manifest lookup and validation. It does not load
third-party runtime code.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

Manifest = dict[str, Any]
ManifestGroups = dict[str, list[Manifest]]

SOURCE_ORDER = ("bundled", "system", "project")
_BUNDLED_MANIFEST_MODULES = (
    "anchor_pdfs",
    "anchor_fmus",
    "anchor_cad",
)

_PRODUCER_NAME_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$")


class InvalidProducerNameError(ValueError):
    """Raised when an OIP producer name is not a safe file stem."""


@dataclass(frozen=True)
class ExtensionRuntimeStatus:
    name: str
    source: str
    available: bool
    reason: str | None = None
    error_type: str | None = None


def system_producers_dir() -> Path:
    """Return the shared OIP producer-registration directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "oip" / "producers.d"


def project_producers_dir(data_dir: Path) -> Path:
    """Return the project-scoped OIP producer-registration directory."""
    return Path(data_dir) / ".oip" / "producers.d"


def registration_dir(scope: str, data_dir: Path) -> Path:
    """Resolve a registration scope to the directory it writes."""
    if scope == "project":
        return project_producers_dir(data_dir)
    if scope == "system":
        return system_producers_dir()
    raise ValueError("registration scope must be 'system' or 'project'")


def validate_producer_name(name: object) -> str:
    """Return a portable producer name or raise ``InvalidProducerNameError``.

    Producer names become ``<name>.json`` registration filenames. Keep them
    to one path segment so a manifest can never redirect registration outside
    the selected OIP directory.
    """
    if not isinstance(name, str) or not name:
        raise InvalidProducerNameError("producer.name must be a non-empty string")
    if name in {".", ".."} or not _PRODUCER_NAME_RE.fullmatch(name):
        raise InvalidProducerNameError(
            f"producer.name {name!r} must match {_PRODUCER_NAME_RE.pattern}"
        )
    return name


def registration_path(scope: str, data_dir: Path, producer_name: object) -> Path:
    """Return the validated registration path for one producer."""
    name = validate_producer_name(producer_name)
    return registration_dir(scope, data_dir) / f"{name}.json"


def load_manifest(
    path: Path,
    *,
    on_error: Callable[[str], None] | None = None,
) -> Manifest | None:
    """Read and minimally validate one OIP manifest."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if on_error is not None:
            on_error(f"{path}: {exc}")
        return None

    if not isinstance(data, dict):
        if on_error is not None:
            on_error(f"{path}: not an OIP manifest (root must be an object)")
        return None
    if "oip_version" not in data or "producer" not in data:
        if on_error is not None:
            on_error(f"{path}: not an OIP manifest (missing oip_version/producer)")
        return None

    if not isinstance(data["oip_version"], str) or not data["oip_version"].strip():
        if on_error is not None:
            on_error(f"{path}: not an OIP manifest (oip_version must be a string)")
        return None

    producer = data["producer"]
    if not isinstance(producer, dict):
        if on_error is not None:
            on_error(f"{path}: not an OIP manifest (producer must be an object)")
        return None
    try:
        validate_producer_name(producer.get("name"))
    except InvalidProducerNameError as exc:
        if on_error is not None:
            on_error(f"{path}: not an OIP manifest ({exc})")
        return None

    data["_manifest_path"] = str(path)
    return data


def bundled_manifests(data_dir: Path | None = None) -> list[Manifest]:
    """Return manifests for first-party producers bundled in this wheel."""
    manifests: list[Manifest] = []
    for module_name in _BUNDLED_MANIFEST_MODULES:
        module = import_module(f"anchor.extensions.{module_name}.extension")
        manifests.append(module.manifest(data_dir))
    return manifests


def discover_manifests(
    data_dir: Path | None = None,
    *,
    on_error: Callable[[str], None] | None = None,
) -> ManifestGroups:
    """Discover OIP manifests grouped by their source."""
    found: ManifestGroups = {
        "bundled": bundled_manifests(data_dir),
        "system": [],
        "project": [],
    }

    sys_dir = system_producers_dir()
    if sys_dir.is_dir():
        for path in sorted(sys_dir.glob("*.json")):
            manifest = load_manifest(path, on_error=on_error)
            if manifest is not None:
                found["system"].append(manifest)

    if data_dir is not None:
        proj_dir = project_producers_dir(data_dir)
        if proj_dir.is_dir():
            for path in sorted(proj_dir.glob("*.json")):
                manifest = load_manifest(path, on_error=on_error)
                if manifest is not None:
                    found["project"].append(manifest)

    return found


def discover_third_party_manifest_paths(data_dir: Path | None = None) -> list[Path]:
    """Return registered third-party manifest paths in a stable order."""
    found: list[Path] = []

    sys_dir = system_producers_dir()
    if sys_dir.is_dir():
        found.extend(sorted(sys_dir.glob("*.json")))

    if data_dir is not None:
        proj_dir = project_producers_dir(data_dir)
        if proj_dir.is_dir():
            found.extend(sorted(proj_dir.glob("*.json")))

    return found
