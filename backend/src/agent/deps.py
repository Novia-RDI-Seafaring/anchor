from dataclasses import dataclass, field
from typing import Any

from .state import Canvas
from src.kb_engine.rag_engine import RagEngine

@dataclass
class AgentDeps:
    state: Canvas
    rag: RagEngine
    last_search_results: list[dict[str, Any]] = field(default_factory=list)
    last_search_run_id: str = ""


    model_config = {
        "arbitrary_types_allowed": True
    }
