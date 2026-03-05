from __future__ import annotations

from typing import Sequence

from PIL import Image
from llama_index.core.base.response.schema import NodeWithScore

from src.kb_engine.utils.pdf_rendering import (
    render_node_to_image,
    render_node_to_image_bytes,
    render_nodes_to_image,
    render_nodes_to_image_bytes,
)


def _to_image(
    self: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
    phrases: Sequence[str] | None = None,
    use_metadata_phrases: bool = True,
) -> Image.Image:
    return render_node_to_image(
        node=self,
        scale=scale,
        page_no=page_no,
        relevance_weighted=relevance_weighted,
        phrases=phrases,
        use_metadata_phrases=use_metadata_phrases,
    )


def _to_image_bytes(
    self: NodeWithScore,
    scale: int = 2,
    page_no: int | None = None,
    relevance_weighted: bool = True,
    phrases: Sequence[str] | None = None,
    use_metadata_phrases: bool = True,
) -> bytes:
    return render_node_to_image_bytes(
        node=self,
        scale=scale,
        page_no=page_no,
        relevance_weighted=relevance_weighted,
        phrases=phrases,
        use_metadata_phrases=use_metadata_phrases,
    )


NodeWithScore.to_image = _to_image  # type: ignore[attr-defined]
NodeWithScore.to_image_bytes = _to_image_bytes  # type: ignore[attr-defined]

__all__ = [
    "NodeWithScore",
    "render_nodes_to_image",
    "render_nodes_to_image_bytes",
]
