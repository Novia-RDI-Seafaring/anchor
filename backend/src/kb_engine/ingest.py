from __future__ import annotations
from ketju.rag.llama_index.ingestion.simple_docling_full_ctx import DoclingFullCtxIngestionHandler
from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from pathlib import Path


# pyright: reportMissingTypeStubs=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false

import uuid
from pathlib import Path
from collections.abc import Sequence

from docling_core.types import DoclingDocument as DLDocument
from llama_index.core.ingestion import IngestionPipeline
from llama_index.node_parser.docling import DoclingNodeParser
from llama_index.readers.docling import DoclingReader

from ketju.core.instrumentation import add_span_event
from ketju.rag.llama_index.variants.simple import LlamaIndexRag


def gen_id(doc: DLDocument, file_path: str | Path) -> str:
    add_span_event("docling.gen_id", attributes={"file": str(file_path)})
    return str(uuid.uuid4())



class IngestionHandler(DoclingFullCtxIngestionHandler):

    def _ingest_file(self, rag: LlamaIndexRag, file: Path) -> int:
        reader = DoclingReader(export_type=DoclingReader.ExportType.JSON, id_func=gen_id)
        documents = reader.load_data(file)

        
        documents[0].metadata["filepath"] = str(file)
        print(documents[0].model_dump_json())

        add_span_event("docling.loaded", attributes={"file": str(file)})
        pipeline = IngestionPipeline(
            name="simple_docling_rag_ing estion",
            project_name="simple_docling_rag",
            transformations=[DoclingNodeParser(include_metadata=True, include_prev_next_rel=True)],
            documents=documents,
            vector_store=rag.vector_store,
        )
        nodes = list(pipeline.run())
        
        if nodes:
            rag.vector_index.insert_nodes(nodes)
        return len(nodes)