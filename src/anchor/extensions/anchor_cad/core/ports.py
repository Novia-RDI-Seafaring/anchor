"""Ports for the CAD extension — protocols implemented by infra."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from anchor.extensions.anchor_cad.core.schemas import CadModel


class CadInspector(Protocol):
    """Read a CAD file and emit a CadModel summary.

    Implementations vary by kind: STL/OBJ are easy (count triangles, compute
    bounding box); STEP needs OpenCascade; JSCAD/OpenSCAD evaluate to extract
    parameters. The default `NaiveCadInspector` only fills filename + kind +
    file size — useful as a manifest-shipping stub before the real parsers
    land.
    """

    async def inspect(self, cad_path: Path, *, kind: str | None = None) -> CadModel: ...


class CadStore(Protocol):
    """Persist CAD bronze (raw model files) + parsed model summaries."""

    async def stash_cad(self, cad_bytes: bytes, filename: str) -> Path: ...

    async def get_cad_path(self, slug: str) -> Path | None: ...

    async def list_cads(self) -> list[CadModel]: ...

    async def write_model_summary(self, slug: str, model: CadModel) -> Path: ...

    async def get_model(self, slug: str) -> CadModel | None: ...
