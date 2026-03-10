from __future__ import annotations
from ketju.rag.llama_index.ingestion.simple_docling_full_ctx import DoclingFullCtxIngestionHandler
from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from pathlib import Path


# pyright: reportMissingTypeStubs=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false

import uuid
import re
from pathlib import Path
from typing import Any, List, Sequence

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
    def ingest(
        self,
        rag: LlamaIndexRag,
        *,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> int:
        resolved_files = rag.resolve_pdf_files(files=files, max_files=max_files)
        resolved_document_ids = list(document_ids or [])
        ingested_nodes = 0

        for index, file in enumerate(resolved_files):
            document_id = resolved_document_ids[index] if index < len(resolved_document_ids) else None
            ingested_nodes += self._ingest_file(rag, file, document_id=document_id)

        rag.save()
        return ingested_nodes

    def _extract_highlight_phrases(self, text: str, max_count: int = 12) -> List[str]:
        if not text:
            return []
        # Split on sentence boundaries and keep useful short phrases.
        chunks = [c.strip() for c in re.split(r"[.;\n]+", text) if c.strip()]
        phrases: List[str] = []
        seen = set()
        for chunk in chunks:
            if len(chunk) < 4 or len(chunk) > 120:
                continue
            if chunk.lower() in seen:
                continue
            seen.add(chunk.lower())
            phrases.append(chunk)
            if len(phrases) >= max_count:
                break
        return phrases

    def _origin_metadata(self, file: Path, current_origin: Any) -> dict[str, Any]:
        origin = current_origin if isinstance(current_origin, dict) else {}
        origin.setdefault("filename", file.name)
        if "filepath" not in origin:
            origin["filepath"] = str(file)
        return origin

    def _ingest_file(self, rag: LlamaIndexRag, file: Path, document_id: str | None = None) -> int:
        reader = DoclingReader(export_type=DoclingReader.ExportType.JSON, id_func=gen_id)
        documents = reader.load_data(file)
        if documents:
            documents[0].metadata["filepath"] = str(file)
            documents[0].metadata["filename"] = file.name
            if document_id:
                documents[0].metadata["document_id"] = document_id

        add_span_event("docling.loaded", attributes={"file": str(file)})
        pipeline = IngestionPipeline(
            name="simple_docling_rag_ing estion",
            project_name="simple_docling_rag",
            transformations=[DoclingNodeParser(include_metadata=True, include_prev_next_rel=True)],
            documents=documents,
            vector_store=rag.vector_store,
        )
        nodes = list(pipeline.run())

        for node in nodes:
            node.metadata.setdefault("filepath", str(file))
            node.metadata.setdefault("filename", file.name)
            node.metadata["origin"] = self._origin_metadata(file, node.metadata.get("origin"))
            if document_id:
                node.metadata["document_id"] = document_id
            node_text = str(getattr(node, "text", "") or "")
            phrases = self._extract_highlight_phrases(node_text)
            if phrases:
                node.metadata["highlight_phrases"] = phrases
                if hasattr(node, "excluded_embed_metadata_keys"):
                    node.excluded_embed_metadata_keys.append("highlight_phrases")
                if hasattr(node, "excluded_llm_metadata_keys"):
                    node.excluded_llm_metadata_keys.append("highlight_phrases")
        
        if nodes:
            rag.vector_index.insert_nodes(nodes)
        return len(nodes)
