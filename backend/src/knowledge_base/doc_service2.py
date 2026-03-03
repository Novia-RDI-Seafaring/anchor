from pathlib import Path
from ketju.rag.base import BaseRAG




class DocService2:
    ingested_files: set[Path]
    rag_service: BaseRAG

    def __init__(self, rag_service: BaseRAG):
        self.ingested_files = set()
        self.rag_service = rag_service
        pass

    def ingest(self, files: list[Path]):
        for file in files:
            if file not in self.ingested_files:
                try:
                    self.rag_service.ingest(files=[file])
                    self.ingested_files.add(file)
                except Exception as e:
                    print(f"Error ingesting file {file}: {e}")
                    continue

    def list_files(self) -> list[Path]:
        return list(self.ingested_files)
    
    def delete_file(self, file: Path):
        pass

    def query(self, question: str, **kwargs):
        return self.rag_service.query(question)

_doc_service: DocService2|None = None

def get_document_service2() -> DocService2:
    global _doc_service
    if _doc_service is None:
        from src.kb_engine.rich_docling2 import get_rag_handler
        _doc_service = DocService2(rag_service=get_rag_handler())
    return _doc_service