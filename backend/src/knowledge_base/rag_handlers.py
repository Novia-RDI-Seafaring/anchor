
_handlers = {}
from ketju.rag.base import BaseRAG

def add_handler(name: str, handler: BaseRAG):
    _handlers[name] = handler
