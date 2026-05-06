"""NaiveCadInspector — fills a CadModel from filename + bytes only.

No actual geometry parsing. STL triangle counts are estimated by file size
when the file is binary STL (84-byte header + 50 bytes/triangle); the
estimate is a placeholder until a real parser lands. JSCAD/OpenSCAD source
is opened for very crude parameter extraction (regex for `param = value`).

Goal: ship a CadModel that's truthful about *what we know* and silent
about everything else, so consumers can be written against the schema
before the heavy parsers are integrated.
"""
from __future__ import annotations

import re
from pathlib import Path

from anchor.core.ids import slugify
from anchor.extensions.anchor_cad.core.schemas import (
    CadGeometryStats,
    CadModel,
    CadParameter,
)


_PARAM_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([\-\+]?[0-9]*\.?[0-9]+)\s*;?",
    flags=re.MULTILINE,
)


class NaiveCadInspector:
    async def inspect(self, cad_path: Path, *, kind: str | None = None) -> CadModel:
        slug = slugify(cad_path.stem)
        filename = cad_path.name
        size = cad_path.stat().st_size if cad_path.exists() else 0

        params: list[CadParameter] = []
        geometry = CadGeometryStats()
        if kind == "stl" and size > 84:
            # Binary STL: 84-byte header, 50 bytes per triangle facet.
            # Real binary STL has UINT32 count at offset 80; trust that
            # only when the file is large enough to look binary.
            triangle_estimate = (size - 84) // 50
            if triangle_estimate > 0:
                geometry = CadGeometryStats(triangle_count=triangle_estimate)
        elif kind in ("jscad", "openscad") and cad_path.exists():
            try:
                src = cad_path.read_text(errors="replace")
                for m in _PARAM_RE.finditer(src[:4000]):
                    name, value = m.group(1), m.group(2)
                    try:
                        v = float(value) if "." in value else int(value)
                    except ValueError:
                        continue
                    params.append(CadParameter(name=name, value=v))
            except OSError:
                pass

        return CadModel(
            slug=slug,
            filename=filename,
            kind=kind or "unknown",  # type: ignore[arg-type]
            parameters=params,
            geometry=geometry,
        )
