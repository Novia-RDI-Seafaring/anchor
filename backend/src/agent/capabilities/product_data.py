"""Product data capability — load pre-extracted structured data for documents."""
from dataclasses import dataclass
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from ..deps import AgentDeps
from ..tools import product_data as product_data_tools

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
_toolset.tool(product_data_tools.get_product_data)

_INSTRUCTIONS = """
Product Data (Gold Layer)
═════════════════════════
Some documents have pre-extracted structured product data available.
Use get_product_data(filename) to load it — pass the document's filename
as shown in the document list. Returns the full structured JSON with
product family info, per-model specs, operating data, dimensions,
materials, motor data, connections, bounding boxes, etc.

This is faster and more complete than reading pages or RAG search.
Try this first for any document in the workspace, then fall back to
read_document_page if no gold data exists.
""".strip()


@dataclass
class ProductDataCapability(AbstractCapability[Any]):
    """Load pre-extracted structured data for documents."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
