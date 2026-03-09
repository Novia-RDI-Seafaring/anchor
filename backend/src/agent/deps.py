from dataclasses import dataclass

from src.knowledge_base.doc_service2 import DocService2

from .state import RAGState, Canvas
from src.kb_engine.rag_engine import RagEngine

@dataclass
class AgentDeps:
    state: Canvas
    rag: RagEngine


    model_config = {
        "arbitrary_types_allowed": True
    }
