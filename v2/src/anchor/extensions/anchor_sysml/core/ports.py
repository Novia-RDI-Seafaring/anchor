"""Ports for the SysML extension — protocols implemented by ``infra``.

The service depends on these abstractions so the parser/mapper can be swapped
(for example to a SysML v2 API client in Phase 2) without touching ``services.py``.
"""
from __future__ import annotations

from typing import Protocol

from anchor.extensions.anchor_sysml.core.schemas import (
    CanvasBatch,
    IrModel,
)


class SysmlParser(Protocol):
    """Lex + parse a SysML v2 textual document into the IR."""

    def parse(self, text: str, *, filename: str | None = None) -> IrModel: ...


class CanvasMapper(Protocol):
    """Project an IR model into canvas node/edge specs."""

    def map(
        self,
        ir: IrModel,
        *,
        x_offset: float = 0,
        y_offset: float = 0,
    ) -> CanvasBatch: ...


class SysmlRenderer(Protocol):
    """Serialise a canvas state back into SysML v2 text (Phase 2+).

    Phase 1 implementation returns a stub-text + a TODO diagnostic in the
    service. The protocol exists so the service can later be backed by a
    real round-trip renderer without touching its public surface.
    """

    def render(self, workspace_state: dict) -> str: ...
