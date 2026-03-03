from src.knowledge_base.doc_service2 import DocService2
from pydantic_ai.ag_ui import StateDeps
from .state import RAGState

from pydantic import BaseModel
class AgentDeps(BaseModel):
    state: RAGState
    doc_service: DocService2


    model_config = {
        "arbitrary_types_allowed": True
    }
