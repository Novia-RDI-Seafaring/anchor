from src.knowledge_base.doc_service2 import DocService2
from pydantic_ai.ag_ui import StateDeps, StateHandler
from .state import RAGState


from dataclasses import dataclass
@dataclass
class AgentDeps:
    state: RAGState
    doc_service: DocService2


    model_config = {
        "arbitrary_types_allowed": True
    }
