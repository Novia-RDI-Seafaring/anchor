"""Shared OIP manifest discovery for adapter entry points.

The host centralizes manifest lookup and validation. It does not load
third-party runtime code.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
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
    return project_producers_dir(data_dir) if scope == "project" else system_producers_dir()


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

    if "oip_version" not in data or "producer" not in data:
        if on_error is not None:
            on_error(f"{path}: not an OIP manifest (missing oip_version/producer)")
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
