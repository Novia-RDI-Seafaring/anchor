"""
Docling Converter for enhanced document processing.

This module handles the Docling-specific conversion logic, adapted from the
existing MERI codebase for use in the enhanced document processor.
"""

from typing import Any
import time

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption # type: ignore
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TableFormerMode # type: ignore
    from docling.datamodel.base_models import InputFormat # type: ignore
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend # type: ignore
    # Try to import faster backend (beta, ~10x faster)
    try:
        from docling.backend.docling_parse_v2_backend import DoclingParseV2DocumentBackend # type: ignore
        FAST_BACKEND_AVAILABLE = True
    except ImportError:
        FAST_BACKEND_AVAILABLE = False
except ImportError as e:
    raise ImportError(
        "Docling dependencies not found. Please install required packages:\n"
        "pip install docling docling-core python-multipart pypdfium2"
    ) from e


class DoclingConverter:
    """Handles document conversion using Docling with enhanced metadata preservation."""

    def __init__(self,
                 preserve_images: bool = True,
                 preserve_tables: bool = True,
                 enable_ocr: bool = False,
                 table_mode: str = "fast",
                 use_fast_backend: bool = True,
                 optimize_for_speed: bool = False):
        """
        Initialize the Docling converter with performance optimizations.

        Args:
            preserve_images: Whether to extract images from documents
            preserve_tables: Whether to preserve table structures
            enable_ocr: Whether to enable OCR for scanned content
            table_mode: Table extraction mode ('accurate' or 'fast') - 'fast' is ~2-3x faster
            use_fast_backend: Use DoclingParseV2DocumentBackend if available (~10x faster PDF loading)
            optimize_for_speed: Enable additional speed optimizations (disables some features)
        """
        # Configure table structure options
        table_mode_map = {
            'accurate': TableFormerMode.ACCURATE,
            'fast': TableFormerMode.FAST
        }

        table_structure_options = TableStructureOptions(
            mode=table_mode_map.get(table_mode, TableFormerMode.FAST),
            do_cell_matching=preserve_tables and not optimize_for_speed
        )

        # Configure pipeline options
        pipeline_options = PdfPipelineOptions(
            generate_picture_images=preserve_images and not optimize_for_speed,
            generate_table_images=preserve_tables and not optimize_for_speed,
            do_ocr=enable_ocr,
            table_structure_options=table_structure_options
        )

        # Select PDF backend
        pdf_backend = PyPdfiumDocumentBackend
        if use_fast_backend and FAST_BACKEND_AVAILABLE:
            pdf_backend = DoclingParseV2DocumentBackend
            print("Using DoclingParseV2DocumentBackend for faster PDF processing (~10x faster)")
        elif use_fast_backend and not FAST_BACKEND_AVAILABLE:
            print("Fast backend not available, using PyPdfiumDocumentBackend. Install docling-parse-v2 for faster processing.")

        # Initialize the document converter
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=pdf_backend
                )
            }
        )

    def convert_document(self, file_path: str) -> Any:
        """
        Convert a document using Docling with performance tracking.

        Args:
            file_path: Path to the document file

        Returns:
            Docling conversion result with full document structure
        """
        start_time = time.time()
        
        try:
            conversion_result = self.converter.convert(file_path)
            conversion_time = time.time() - start_time

            # Validate the conversion
            if not conversion_result or not conversion_result.document:
                raise ValueError(f"Failed to convert document: {file_path}")

            # Log performance metrics
            page_count = len(conversion_result.document.pages) if conversion_result.document else 0
            if page_count > 0:
                time_per_page = conversion_time / page_count
                print(f"DoclingConverter: Processed {page_count} pages in {conversion_time:.2f}s ({time_per_page:.2f}s/page)")
            
            return conversion_result

        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"DoclingConverter: Conversion failed after {elapsed_time:.2f}s: {e}")
            raise RuntimeError(f"Docling conversion failed for {file_path}: {e}") from e
