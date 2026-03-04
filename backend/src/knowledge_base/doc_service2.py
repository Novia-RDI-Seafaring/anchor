from pathlib import Path
from ketju.rag.base import BaseRAG
from typing import Optional, Any



class DocService2:
    ingested_files: set[Path]
    rag_service: BaseRAG
    active_document_id: Optional[str] = None

    def __init__(self, rag_service: BaseRAG):
        self.ingested_files = set()
        print("getting rag service")
        print(f"rag service: {rag_service}")
        self.rag_service = rag_service
        self.active_document_id = None
        

    def ingest(self, files: list[Path]):
        for file in files:
            if file not in self.ingested_files:
                try:
                    print("1111")
                    self.rag_service.ingest(files=[file])
                    print("2222")
                    self.ingested_files.add(file)
                     
                except Exception as e:
                    print(f"Error ingesting file {file}: {e}")
                    continue
        return self.ingested_files

    def list_document_toc(self, document_id: Optional[str] = None) -> Any:
        return "not implemented yet"


    def list_files(self) -> list[Path]:
        return list(self.ingested_files)
    
    def list_documents(self) -> list[Path]:
        return list(self.ingested_files)
    
    def delete_document(self, document_id: str):
        print(f"Deleting document {document_id}")
        pass
    
    def delete_file(self, file: Path):
        pass

    def reingest_all(self):
        print(f"Re-ingesting all documents")
        pass

    def query(self, question: str, **kwargs):
        return self.rag_service.query(question, **kwargs)
    
    def reset_knowledge_base(self):
        pass
    

_doc_service: DocService2|None = None

def get_document_service2() -> DocService2:
    global _doc_service
    if _doc_service is None:
        from src.kb_engine.rag_engine import get_rag_engine
        _doc_service = DocService2(rag_service=get_rag_engine())
    return _doc_service



"""
    # Use ANCHOR's settings for KETJU's PgVectorStorageBackend
    storage_backend = PgVectorStorageBackend(
        database_url=settings.database_url,
        table_name=collection_name or f"ketju_{settings.vector_db_collection}",
        schema_name=settings.db_schema,
        embed_dim=settings.embedding_dimension
    )
    
    # Use our new RichDoclingIngestionHandler
    ingestion_handler = RichDoclingIngestionHandler(
        preserve_images=preserve_images,
        preserve_tables=preserve_tables,
        enable_ocr=enable_ocr,
        table_mode=table_mode
    )
    
    # Simple query handler for now
    query_handler = SimpleLlamaIndexQueryHandler()
    
    return LlamaIndexRag(
        name="anchor_ketju_rag",
        docs_dir=Path(settings.uploads_dir),
        storage_backend=storage_backend,
        ingestion_handler=ingestion_handler,
        query_handler=query_handler,
        embedding_model="text-embedding-3-small" # Match KETJU default/ANCHOR dimension
    )


"""