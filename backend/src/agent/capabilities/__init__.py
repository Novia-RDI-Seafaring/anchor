"""Agent capabilities.

This branch currently runs a small live capability set while keeping several
in-progress capability modules in the tree for later activation.
"""
from .context import ContextCapability
from .canvas import CanvasCapability

LIVE_CAPABILITY_NAMES = (
    "ContextCapability",
    "CanvasCapability",
)

DORMANT_CAPABILITY_NAMES = (
    "ProductDataCapability",
    "KnowledgeCapability",
    "DocumentVisionCapability",
    "FmuCapability",
    "EngineeringKnowledgeCapability",
    "RouterCapability",
)

CAPABILITIES = [
    ContextCapability(),
    CanvasCapability(),
]

__all__ = [
    "CAPABILITIES",
    "LIVE_CAPABILITY_NAMES",
    "DORMANT_CAPABILITY_NAMES",
    "ContextCapability",
    "CanvasCapability",
]
