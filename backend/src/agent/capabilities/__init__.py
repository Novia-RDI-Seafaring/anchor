"""Agent capabilities — assemble the routing registry and export all capabilities."""
from .base import RoutingRegistry
from .canvas import CanvasCapability, LOW_LEVEL_TOOLS as _CANVAS_LOW_LEVEL
from .knowledge import KnowledgeCapability, LIST_ONLY_TOOLS, RAW_SEARCH_TOOLS, HIGH_LEVEL_TOOLS as _KNOWLEDGE_HIGH_LEVEL
from .fmu import FmuCapability, HIGH_LEVEL_TOOLS as _FMU_HIGH_LEVEL
from .document_vision import DocumentVisionCapability, HIGH_LEVEL_TOOLS as _DOC_HIGH_LEVEL
from .router import RouterCapability

# Assemble the routing registry from each capability's declared tool names.
# canvas.check_canvas lives in both low-level and high-level sets by design.
_registry = RoutingRegistry(
    list_only_tools=LIST_ONLY_TOOLS,
    raw_search_tools=RAW_SEARCH_TOOLS,
    low_level_canvas_tools=_CANVAS_LOW_LEVEL,
    high_level_technical_tools=(
        _KNOWLEDGE_HIGH_LEVEL
        | _FMU_HIGH_LEVEL
        | _DOC_HIGH_LEVEL
        | _CANVAS_LOW_LEVEL  # check_canvas is available even in high-level mode
    ),
)

# Ready-to-use capability instances — pass directly to Agent(capabilities=[...]).
CAPABILITIES = [
    CanvasCapability(),
    KnowledgeCapability(),
    FmuCapability(),
    DocumentVisionCapability(),
    RouterCapability(registry=_registry),
]

__all__ = [
    "CAPABILITIES",
    "RoutingRegistry",
    "CanvasCapability",
    "KnowledgeCapability",
    "FmuCapability",
    "DocumentVisionCapability",
    "RouterCapability",
]
