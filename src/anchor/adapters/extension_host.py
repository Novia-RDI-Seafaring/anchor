"""Discover OIP manifests and start bundled ANCHOR extensions.

The host owns first-party extension composition at the adapter seam. Registered
third-party OIP manifests remain data and process contracts; this module never
imports arbitrary code from them.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload

if TYPE_CHECKING:
    from anchor.core.ports.event_bus import EventBus
    from anchor.core.services.workspace_service import WorkspaceService
    from anchor.extensions.anchor_cad.core.services import CadService
    from anchor.extensions.anchor_fmus.core.services import FmuService
    from anchor.extensions.anchor_sysml.core.services import SysmlService

Manifest = dict[str, Any]
ManifestGroups = dict[str, list[Manifest]]
BundledRuntimeName = Literal["cad", "fmu", "sysml"]

SOURCE_ORDER = ("bundled", "system", "project")
_BUNDLED_MANIFEST_MODULES = (
    "anchor_pdfs",
    "anchor_fmus",
    "anchor_cad",
    "anchor_sysml",
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


def extension_runtime_status_payload(
    statuses: Mapping[str, ExtensionRuntimeStatus],
) -> dict[str, object]:
    """Return the adapter-neutral extension runtime diagnostic payload."""
    extensions = [
        {
            "name": status.name,
            "source": status.source,
            "available": status.available,
            "reason": status.reason,
            "error_type": status.error_type,
        }
        for _name, status in sorted(statuses.items())
    ]
    available = sum(1 for item in extensions if item["available"])
    return {
        "extensions": extensions,
        "summary": {
            "available": available,
            "unavailable": len(extensions) - available,
        },
    }


@dataclass(frozen=True)
class BundledExtensionRuntimes:
    """First-party extension modules started for one project runtime."""

    cad: CadService
    sysml: SysmlService
    fmu: FmuService | None
    status: dict[str, ExtensionRuntimeStatus]


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


class ExtensionHost:
    """Compose extension discovery and bundled runtime startup for a project.

    The interface intentionally separates manifest discovery from runtime
    startup. OIP manifests describe producers but do not authorize ANCHOR to
    import third-party code. Only bundled extension modules are started here.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else None

    def bundled_manifests(self) -> list[Manifest]:
        """Return manifests for first-party producers bundled in this wheel."""
        manifests: list[Manifest] = []
        for module_name in _BUNDLED_MANIFEST_MODULES:
            module = import_module(f"anchor.extensions.{module_name}.extension")
            manifests.append(module.manifest(self.data_dir))
        return manifests

    def discover(
        self,
        *,
        on_error: Callable[[str], None] | None = None,
    ) -> ManifestGroups:
        """Discover OIP manifests grouped by source."""
        found: ManifestGroups = {
            "bundled": self.bundled_manifests(),
            "system": [],
            "project": [],
        }

        sys_dir = system_producers_dir()
        if sys_dir.is_dir():
            for path in sorted(sys_dir.glob("*.json")):
                manifest = load_manifest(path, on_error=on_error)
                if manifest is not None:
                    found["system"].append(manifest)

        if self.data_dir is not None:
            proj_dir = project_producers_dir(self.data_dir)
            if proj_dir.is_dir():
                for path in sorted(proj_dir.glob("*.json")):
                    manifest = load_manifest(path, on_error=on_error)
                    if manifest is not None:
                        found["project"].append(manifest)

        return found

    def third_party_manifest_paths(self) -> list[Path]:
        """Return registered third-party manifest paths in stable order."""
        found: list[Path] = []
        sys_dir = system_producers_dir()
        if sys_dir.is_dir():
            found.extend(sorted(sys_dir.glob("*.json")))

        if self.data_dir is not None:
            proj_dir = project_producers_dir(self.data_dir)
            if proj_dir.is_dir():
                found.extend(sorted(proj_dir.glob("*.json")))
        return found

    @overload
    def start(
        self,
        name: Literal["cad"],
        *,
        bus: EventBus,
        workspace: WorkspaceService | None = None,
    ) -> CadService: ...

    @overload
    def start(
        self,
        name: Literal["fmu"],
        *,
        bus: EventBus,
        workspace: WorkspaceService | None = None,
    ) -> FmuService: ...

    @overload
    def start(
        self,
        name: Literal["sysml"],
        *,
        bus: EventBus,
        workspace: WorkspaceService | None = None,
    ) -> SysmlService: ...

    def start(
        self,
        name: BundledRuntimeName,
        *,
        bus: EventBus,
        workspace: WorkspaceService | None = None,
    ) -> CadService | FmuService | SysmlService:
        """Start one bundled extension without starting unrelated modules."""
        if self.data_dir is None:
            raise RuntimeError("ExtensionHost.start requires a project data_dir")
        if name == "cad":
            from anchor.extensions.anchor_cad import extension as cad_ext

            return cad_ext.build_service(self.data_dir, bus)
        if name == "fmu":
            from anchor.extensions.anchor_fmus import extension as fmu_ext

            return fmu_ext.build_service(self.data_dir, bus)
        if name == "sysml":
            if workspace is None:
                raise RuntimeError("ExtensionHost.start('sysml') requires WorkspaceService")
            from anchor.extensions.anchor_sysml import extension as sysml_ext

            return sysml_ext.build_service(self.data_dir, bus, workspace=workspace)
        raise ValueError(f"unknown bundled runtime: {name!r}")

    def start_bundled(
        self,
        *,
        bus: EventBus,
        workspace: WorkspaceService,
        fmu_warning: Callable[[Exception], None] | None = None,
    ) -> BundledExtensionRuntimes:
        """Start bundled CAD, FMU, and SysML modules for this project.

        CAD and SysML are required bundled modules and propagate startup
        failures. FMU is optional because its real runtime is an extra; its
        failure is recorded and reported while the rest of ANCHOR starts.
        """
        if self.data_dir is None:
            raise RuntimeError("ExtensionHost.start_bundled requires a project data_dir")

        from anchor.extensions.anchor_fmus import extension as fmu_ext

        cad = self.start("cad", bus=bus)
        status = {
            "anchor-cad": ExtensionRuntimeStatus(
                name="anchor-cad",
                source="bundled",
                available=True,
            )
        }

        fmu = None
        try:
            fmu = self.start("fmu", bus=bus)
            status[fmu_ext.NAME] = ExtensionRuntimeStatus(
                name=fmu_ext.NAME,
                source="bundled",
                available=True,
            )
        except Exception as exc:  # noqa: BLE001 - optional extension
            status[fmu_ext.NAME] = ExtensionRuntimeStatus(
                name=fmu_ext.NAME,
                source="bundled",
                available=False,
                reason=str(exc),
                error_type=exc.__class__.__name__,
            )
            if fmu_warning is None:
                print(f"Warning: FMU extension disabled: {exc}", file=sys.stderr)
            else:
                fmu_warning(exc)

        sysml = self.start("sysml", bus=bus, workspace=workspace)
        status["anchor-sysml"] = ExtensionRuntimeStatus(
            name="anchor-sysml",
            source="bundled",
            available=True,
        )
        return BundledExtensionRuntimes(
            cad=cad,
            sysml=sysml,
            fmu=fmu,
            status=status,
        )


def bundled_manifests(data_dir: Path | None = None) -> list[Manifest]:
    """Return manifests for first-party producers bundled in this wheel."""
    return ExtensionHost(data_dir).bundled_manifests()


def discover_manifests(
    data_dir: Path | None = None,
    *,
    on_error: Callable[[str], None] | None = None,
) -> ManifestGroups:
    """Discover OIP manifests grouped by their source."""
    return ExtensionHost(data_dir).discover(on_error=on_error)


def discover_third_party_manifest_paths(data_dir: Path | None = None) -> list[Path]:
    """Return registered third-party manifest paths in a stable order."""
    return ExtensionHost(data_dir).third_party_manifest_paths()
