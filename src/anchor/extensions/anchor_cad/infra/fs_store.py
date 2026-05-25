"""Filesystem-backed CadStore.

Layout:
    data_dir/cad/
        bronze/<slug>.<ext>           raw input model files
        artefacts/<slug>/
            document.json              OIP-style document metadata
            model.json                 CadModel summary (parameters, parts, geometry)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiofiles

from anchor.core.ids import slugify
from anchor.extensions.anchor_cad.core.schemas import CadModel


class FsCadStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "cad"
        self.bronze = self.root / "bronze"
        self.artefacts = self.root / "artefacts"
        for p in (self.bronze, self.artefacts):
            p.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _model_path(self, slug: str) -> Path:
        return self.artefacts / slug / "model.json"

    async def stash_cad(self, cad_bytes: bytes, filename: str) -> Path:
        # Preserve extension; slugify the stem for the on-disk name.
        stem, _, ext = filename.rpartition(".")
        if not stem:
            stem, ext = filename, "bin"
        slug = slugify(stem)
        out = self.bronze / f"{slug}.{ext.lower()}"
        async with self._lock:
            out.write_bytes(cad_bytes)
        return out

    async def get_cad_path(self, slug: str) -> Path | None:
        for p in self.bronze.iterdir():
            if p.stem == slug:
                return p
        return None

    async def list_cads(self) -> list[CadModel]:
        out: list[CadModel] = []
        if not self.artefacts.is_dir():
            return out
        for d in sorted(self.artefacts.iterdir()):
            if not d.is_dir():
                continue
            mp = d / "model.json"
            if mp.is_file():
                try:
                    out.append(CadModel.model_validate_json(mp.read_text()))
                except Exception:  # malformed model.json; skip
                    continue
        return out

    async def write_model_summary(self, slug: str, model: CadModel) -> Path:
        out = self._model_path(slug)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(out, "w") as f:
            await f.write(model.model_dump_json(indent=2))
        return out

    async def get_model(self, slug: str) -> CadModel | None:
        mp = self._model_path(slug)
        if not mp.is_file():
            return None
        try:
            return CadModel.model_validate_json(mp.read_text())
        except Exception:
            return None
