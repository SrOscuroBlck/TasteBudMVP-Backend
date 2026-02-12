from __future__ import annotations
from typing import Optional
from pathlib import Path


class PDFExtractionError(Exception):
    pass


class PDFProcessor:
    def extract_text_from_pdf(self, file_path: str) -> str:
        if not file_path:
            raise ValueError("file_path is required to extract PDF text")
        
        path = Path(file_path)
        if not path.exists():
            raise PDFExtractionError(f"PDF file not found: {file_path}")
        
        if not path.suffix.lower() == ".pdf":
            raise PDFExtractionError(f"File is not a PDF: {file_path}")
        
        extracted_text = self._extract_with_pdfplumber(file_path)
        
        if not extracted_text or len(extracted_text.strip()) < 50:
            raise PDFExtractionError(f"Insufficient text extracted from PDF: {file_path}")
        
        return extracted_text
    
    def _extract_with_pdfplumber(self, file_path: str) -> str:
        try:
            import pdfplumber
        except ImportError:
            raise PDFExtractionError("pdfplumber is not installed. Install it with: pip install pdfplumber")
        
        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    raise PDFExtractionError("PDF has no pages")
                
                text_blocks = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_blocks.append(page_text)
                
                return "\n\n".join(text_blocks)
        except Exception as e:
            raise PDFExtractionError(f"Failed to extract text from PDF: {str(e)}")
    
    def validate_extracted_text(self, text: str) -> bool:
        if not text:
            return False
        
        if len(text.strip()) < 50:
            return False
        
        words = text.split()
        if len(words) < 10:
            return False
        
        return True
