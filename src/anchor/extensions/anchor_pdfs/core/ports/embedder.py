"""Embedder protocol — text → vector."""
from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
