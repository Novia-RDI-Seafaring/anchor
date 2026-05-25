"""In-memory CadStore for tests and demos."""
from __future__ import annotations

from pathlib import Path

from anchor.extensions.anchor_cad.core.ports import CadStore
from anchor.extensions.anchor_cad.core.schemas import CadModel


class MemoryCadStore:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._models: dict[str, CadModel] = {}
        self._paths: dict[str, Path] = {}

    async def stash_cad(self, cad_bytes: bytes, filename: str) -> Path:
        # Slug derivation matches the service: bytes are keyed by filename.
        path = Path(f"/memory/cad/{filename}")
        self._files[filename] = cad_bytes
        self._paths[filename] = path
        return path

    async def get_cad_path(self, slug: str) -> Path | None:
        return self._paths.get(self._models[slug].filename) if slug in self._models else None

    async def list_cads(self) -> list[CadModel]:
        return list(self._models.values())

    async def write_model_summary(self, slug: str, model: CadModel) -> Path:
        self._models[slug] = model
        return Path(f"/memory/cad/{slug}.json")

    async def get_model(self, slug: str) -> CadModel | None:
        return self._models.get(slug)


_: CadStore = MemoryCadStore()  # protocol conformance check
