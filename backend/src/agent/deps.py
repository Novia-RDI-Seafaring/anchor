from dataclasses import dataclass

from .state import Canvas
from src.kb_engine.rag_engine import RagEngine

@dataclass
class AgentDeps:
    state: Canvas
    rag: RagEngine


    model_config = {
        "arbitrary_types_allowed": True
    }
