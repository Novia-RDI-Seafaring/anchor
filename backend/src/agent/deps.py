from dataclasses import dataclass

from src.knowledge_base.service import DocumentService

from .state import RAGState


@dataclass
class AgentDeps:
    state: RAGState
    doc_service: DocumentService


    model_config = {
        "arbitrary_types_allowed": True
    }
