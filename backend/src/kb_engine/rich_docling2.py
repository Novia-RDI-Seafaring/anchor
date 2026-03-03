from ketju.rag.llama_index.variants.simple_docling_full_ctx import SimpleDoclingFullCtxRag
from ketju.rag.base import BaseRAG
from pathlib import Path
_rag_handler = None

def get_rag_handler() -> BaseRAG: 
    global _rag_handler
    if _rag_handler is None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            _rag_handler = SimpleDoclingFullCtxRag(
                name="anchor_rag",
                persist_dir=Path(tmpdir)
            )
    return _rag_handler