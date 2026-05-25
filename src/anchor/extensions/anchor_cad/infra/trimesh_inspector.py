"""TrimeshCadInspector — real geometry parsing for STL / OBJ / glTF / 3MF / PLY.

Backed by `trimesh`. Reads the file, computes triangle count, vertex
count, bounding box, and (where the format carries it) units. Falls back
to filename-based defaults if trimesh can't open the file.

STEP / IGES / native parametric (.jscad / .scad) are NOT handled here —
STEP needs OpenCascade (a separate, much heavier dependency); parametric
formats need their own evaluators. Those keep the NaiveCadInspector
fallback path.
"""
from __future__ import annotations

from pathlib import Path

from anchor.core.ids import slugify
from anchor.extensions.anchor_cad.core.schemas import (
    CadGeometryStats,
    CadModel,
)
from anchor.extensions.anchor_cad.infra.naive_inspector import NaiveCadInspector

_TRIMESH_KINDS = {"stl", "obj", "gltf", "glb", "3mf", "ply", "off"}


class TrimeshCadInspector:
    """Real geometry stats for the formats trimesh handles natively."""

    def __init__(self) -> None:
        self._fallback = NaiveCadInspector()

    async def inspect(self, cad_path: Path, *, kind: str | None = None) -> CadModel:
        # trimesh handles a finite set of mesh formats; everything else
        # falls back to the naive inspector (STEP, JSCAD, OpenSCAD, etc.).
        if kind not in _TRIMESH_KINDS:
            return await self._fallback.inspect(cad_path, kind=kind)

        try:
            import trimesh  # local import to keep import-time cost off the cold path
        except ImportError:
            return await self._fallback.inspect(cad_path, kind=kind)

        try:
            mesh = trimesh.load(str(cad_path), force="mesh", process=False)
        except Exception:
            return await self._fallback.inspect(cad_path, kind=kind)

        # Some files load as a Scene instead of a Trimesh; coerce to mesh.
        if hasattr(mesh, "geometry") and not hasattr(mesh, "faces"):
            try:
                mesh = mesh.dump(concatenate=True)  # type: ignore[attr-defined]
            except Exception:
                return await self._fallback.inspect(cad_path, kind=kind)

        triangle_count = int(getattr(mesh, "faces", []).__len__()) if hasattr(mesh, "faces") else None
        vertex_count = int(getattr(mesh, "vertices", []).__len__()) if hasattr(mesh, "vertices") else None
        bbox: list[float] | None = None
        bounds = getattr(mesh, "bounds", None)
        if bounds is not None:
            try:
                lo, hi = bounds[0], bounds[1]
                bbox = [float(lo[0]), float(lo[1]), float(lo[2]),
                        float(hi[0]), float(hi[1]), float(hi[2])]
            except Exception:
                bbox = None

        units = getattr(mesh, "units", None)

        return CadModel(
            slug=slugify(cad_path.stem),
            filename=cad_path.name,
            kind=kind,  # type: ignore[arg-type]
            geometry=CadGeometryStats(
                triangle_count=triangle_count,
                vertex_count=vertex_count,
                bounding_box=bbox,
                units=units,
            ),
        )
