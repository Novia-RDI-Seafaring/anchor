"""Agent capabilities — minimal setup: context injection + reading + canvas editing."""
from .context import ContextCapability
from .canvas import CanvasCapability

# Minimal capability set:
# 1. ContextCapability — injects canvas state + doc list into context, provides read_document_page
#    Also auto-loads gold-layer product data for documents on the canvas.
# 2. CanvasCapability — CRUD tools for canvas nodes and relations
#
# Disabled for now (can re-enable as needed):
# - ProductDataCapability (now folded into ContextCapability as auto-loaded context)
# - KnowledgeCapability (resolve_technical_query, search_knowledge_base, etc.)
# - DocumentVisionCapability (get_document_tree, get_document_full_text, analyze_pdf_page, etc.)
# - FmuCapability
# - EngineeringKnowledgeCapability
# - RouterCapability (dynamic tool filtering and prompt routing)

CAPABILITIES = [
    ContextCapability(),
    CanvasCapability(),
]

__all__ = [
    "CAPABILITIES",
    "ContextCapability",
    "CanvasCapability",
]
