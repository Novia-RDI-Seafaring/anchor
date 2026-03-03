from __future__ import annotations

import io
import base64
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Dict, List, Optional

try:
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.node_parser.docling import DoclingNodeParser
    from llama_index.readers.docling import DoclingReader
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TableFormerMode
    from docling.datamodel.base_models import InputFormat
    from docling_core.types.doc.labels import DocItemLabel
except ImportError:
    # Handle missing dependencies gracefully
    pass

from .contracts import LlamaIndexIngestionHandler
from .engine import LlamaIndexRag


class RichDoclingIngestionHandler(LlamaIndexIngestionHandler):
    """
    Enhanced Docling ingestion strategy for ANCHOR that extracts structural metadata 
    (TOC, Images) and inserts nodes into the vector store.
    """

    def __init__(
        self,
        preserve_images: bool = True,
        preserve_tables: bool = True,
        enable_ocr: bool = False,
        table_mode: str = "fast",
    ):
        self.preserve_images = preserve_images
        self.preserve_tables = preserve_tables
        self.enable_ocr = enable_ocr
        self.table_mode = table_mode

    def ingest(
        self,
        rag: LlamaIndexRag,
        *,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
        **kwargs: Any,
    ) -> int:
        resolved_files = rag.resolve_pdf_files(files=files, max_files=max_files)
        document_ids = kwargs.get("document_ids", [])
        
        ingested_nodes = 0
        for i, file in enumerate(resolved_files):
            doc_id = document_ids[i] if i < len(document_ids) else None
            ingested_nodes += self._ingest_file(rag, Path(file), document_id=doc_id)
        rag.save()
        return ingested_nodes

    def _ingest_file(self, rag: LlamaIndexRag, file: Path, document_id: Optional[str] = None) -> int:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TableFormerMode
        from docling.datamodel.base_models import InputFormat

        table_mode_map = {
            'accurate': TableFormerMode.ACCURATE,
            'fast': TableFormerMode.FAST
        }

        pipeline_options = PdfPipelineOptions(
            generate_picture_images=self.preserve_images,
            generate_table_images=self.preserve_tables,
            do_ocr=self.enable_ocr,
            table_structure_options=TableStructureOptions(
                mode=table_mode_map.get(self.table_mode, TableFormerMode.FAST)
            )
        )

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        conversion_result = converter.convert(str(file))
        
        toc_items = self._extract_toc(conversion_result)
        images = self._extract_images(conversion_result)

        doc_id = document_id or str(file.name)

        if hasattr(rag.storage_backend, "add_toc"):
            rag.storage_backend.add_toc(doc_id, toc_items)
        if hasattr(rag.storage_backend, "add_images"):
            rag.storage_backend.add_images(doc_id, images)

        reader = DoclingReader()
        pipeline = IngestionPipeline(
            name="rich_docling_rag_ingestion",
            transformations=[DoclingNodeParser(include_metadata=True, include_prev_next_rel=True)],
            documents=reader.load_data(file),
            docstore=rag.docstore,
            vector_store=rag.vector_store,
        )
        nodes = list(pipeline.run())
        
        for node in nodes:
            node.metadata["document_id"] = doc_id
            node.metadata["filename"] = str(file.name)

        if nodes:
            rag.vector_index.insert_nodes(nodes)
        
        return len(nodes)

    def _extract_images(self, conversion_result) -> List[Dict[str, Any]]:
        extracted_images = []
        try:
            document = conversion_result.document
            for item, level in document.iterate_items():
                if hasattr(item, 'label') and str(item.label).lower() in ['picture', 'figure', 'image']:
                    try:
                        image_data = None
                        if hasattr(item, 'image') and item.image:
                            pil_image = item.image.pil_image if hasattr(item.image, 'pil_image') else item.image
                            if pil_image:
                                buffer = io.BytesIO()
                                pil_image.save(buffer, format='PNG', optimize=True)
                                image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                                buffer.close()
                        
                        if not image_data: continue
                        
                        caption = item.text if hasattr(item, 'text') else None
                        page_number = None
                        bbox = None
                        if hasattr(item, 'prov') and item.prov:
                            for prov in item.prov:
                                if hasattr(prov, 'page_no'): page_number = prov.page_no
                                if hasattr(prov, 'bbox') and hasattr(prov.bbox, 'as_tuple'):
                                    bbox = {'coordinates': list(prov.bbox.as_tuple())}
                                break
                        
                        image_type = 'figure'
                        label_lower = str(item.label).lower()
                        if 'diagram' in label_lower: image_type = 'diagram'
                        elif 'chart' in label_lower: image_type = 'chart'
                        
                        extracted_images.append({
                            'image_type': image_type,
                            'page_number': page_number,
                            'image_base64': image_data,
                            'caption': caption,
                            'alt_text': caption,
                            'bbox': bbox,
                            'width': pil_image.width if pil_image else None,
                            'height': pil_image.height if pil_image else None,
                            'metadata': {'label': str(item.label), 'level': level}
                        })
                    except Exception: continue
        except Exception: pass
        return extracted_images

    def _extract_toc(self, conversion_result) -> List[Dict[str, Any]]:
        from docling_core.types.doc.labels import DocItemLabel
        toc_items = []
        try:
            document = conversion_result.document
            for item, level in document.iterate_items():
                if hasattr(item, 'label') and item.label == DocItemLabel.DOCUMENT_INDEX:
                    page_no = None
                    if hasattr(item, 'prov') and item.prov:
                        page_no = item.prov[0].page_no if hasattr(item.prov[0], 'page_no') else None
                    
                    text_content = getattr(item, 'text', '') or getattr(item, 'self_text', '')
                    if not text_content and hasattr(item, 'children'):
                        text_content = ' '.join([c.text for c in item.children if hasattr(c, 'text')]).strip()
                    
                    toc_items.append({
                        "text": text_content,
                        "level": level,
                        "page_no": page_no,
                        "type": "index_item"
                    })
            
            if not toc_items:
                for item, level in document.iterate_items():
                    if hasattr(item, 'label') and item.label in [DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE]:
                        page_no = None
                        if hasattr(item, 'prov') and item.prov:
                            page_no = item.prov[0].page_no if hasattr(item.prov[0], 'page_no') else None
                        
                        text_content = (getattr(item, 'self_text', '') or getattr(item, 'text', '')).strip()
                        if text_content and len(text_content) <= 200:
                            toc_items.append({
                                "text": text_content,
                                "level": level,
                                "page_no": page_no,
                                "type": str(item.label)
                            })
        except Exception: pass
        return toc_items
