"""
Page Image Service for generating PDF page images.

Uses pypdfium2 (already installed as Docling dependency) to render PDF pages
as high-quality images for the page preview feature.
"""

import base64
import io
from typing import List, Dict, Optional
from pathlib import Path

try:
    import pypdfium2 as pdfium
except ImportError:
    raise ImportError("pypdfium2 is required. It should be installed with docling.")


class PageImageService:
    """Service for generating and managing PDF page images."""
    
    def __init__(self, scale: float = 4.0):
        """
        Initialize the page image service.
        
        Args:
            scale: Rendering scale factor. 4.0 ≈ 300 DPI for standard PDFs.
        """
        self.scale = scale
    
    def generate_page_images(self, pdf_path: str) -> List[Dict]:
        """
        Generate Base64-encoded PNG images for all pages in a PDF.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of dicts with page_number, image_base64, width, height
        """
        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        pdf = pdfium.PdfDocument(pdf_path)
        result = []
        
        try:
            for i in range(len(pdf)):
                page = pdf[i]
                # Render page to bitmap with specified scale
                bitmap = page.render(scale=self.scale)
                # Convert to PIL image
                pil_image = bitmap.to_pil()
                
                # Convert to Base64 PNG
                buffer = io.BytesIO()
                pil_image.save(buffer, format='PNG', optimize=True)
                base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                result.append({
                    'page_number': i + 1,  # 1-indexed
                    'image_base64': base64_str,
                    'width': pil_image.width,
                    'height': pil_image.height
                })
                
                # Clean up
                buffer.close()
                
        finally:
            pdf.close()
        
        return result
    
    def generate_single_page_image(self, pdf_path: str, page_number: int) -> Optional[Dict]:
        """
        Generate a Base64-encoded PNG image for a single page.
        
        Args:
            pdf_path: Path to the PDF file
            page_number: 1-indexed page number
            
        Returns:
            Dict with page_number, image_base64, width, height or None if page doesn't exist
        """
        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        pdf = pdfium.PdfDocument(pdf_path)
        
        try:
            page_index = page_number - 1  # Convert to 0-indexed
            if page_index < 0 or page_index >= len(pdf):
                return None
            
            page = pdf[page_index]
            bitmap = page.render(scale=self.scale)
            pil_image = bitmap.to_pil()
            
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG', optimize=True)
            base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return {
                'page_number': page_number,
                'image_base64': base64_str,
                'width': pil_image.width,
                'height': pil_image.height
            }
            
        finally:
            pdf.close()
    
    def get_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF."""
        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        pdf = pdfium.PdfDocument(pdf_path)
        try:
            return len(pdf)
        finally:
            pdf.close()


# Singleton instance
_page_image_service: Optional[PageImageService] = None


def get_page_image_service(scale: float = 4.0) -> PageImageService:
    """Get or create the page image service singleton."""
    global _page_image_service
    if _page_image_service is None:
        _page_image_service = PageImageService(scale=scale)
    return _page_image_service
