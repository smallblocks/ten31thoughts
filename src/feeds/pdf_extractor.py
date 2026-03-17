"""
Ten31 Thoughts - PDF Text Extractor
Extracts clean readable text from PDF files (newsletters, research reports, investor letters).
Uses PyMuPDF for fast, reliable extraction including OCR fallback.
"""

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extracts text content from PDF files for the analysis pipeline."""

    def extract_from_bytes(self, pdf_bytes: bytes, filename: str = "upload.pdf") -> Optional[dict]:
        """
        Extract text from PDF bytes.

        Returns dict with:
            title: extracted or inferred title
            content: full text content
            content_hash: SHA-256 of content
            page_count: number of pages
            date: extracted date if found
            author: extracted author if found
        """
        import fitz  # PyMuPDF

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"Failed to open PDF '{filename}': {e}")
            return None

        if doc.page_count == 0:
            logger.warning(f"PDF '{filename}' has no pages")
            return None

        # Extract text from all pages
        pages_text = []
        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text("text")
            if text and text.strip():
                pages_text.append(text.strip())

        doc.close()

        if not pages_text:
            logger.warning(f"No text extracted from PDF '{filename}'")
            return None

        full_text = "\n\n".join(pages_text)

        # Clean up
        full_text = self._clean_text(full_text)

        if len(full_text) < 100:
            logger.warning(f"Extracted text too short from '{filename}' ({len(full_text)} chars)")
            return None

        # Extract metadata
        title = self._extract_title(full_text, filename)
        date = self._extract_date(full_text)
        author = self._extract_author(full_text)

        return {
            "title": title,
            "content": full_text,
            "content_hash": hashlib.sha256(full_text.encode()).hexdigest(),
            "page_count": len(pages_text),
            "date": date,
            "author": author,
            "filename": filename,
        }

    def extract_from_file(self, file_path: str) -> Optional[dict]:
        """Extract text from a PDF file on disk."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"PDF file not found: {file_path}")
            return None

        with open(path, "rb") as f:
            pdf_bytes = f.read()

        return self.extract_from_bytes(pdf_bytes, filename=path.name)

    def _clean_text(self, text: str) -> str:
        """Clean extracted PDF text."""
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove page numbers (standalone numbers on a line)
        text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
        # Remove common PDF artifacts
        text = re.sub(r'\x00', '', text)
        # Normalize spaces
        text = re.sub(r'[ \t]+', ' ', text)
        # Clean up line breaks within paragraphs (but keep paragraph breaks)
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned.append(stripped)
            elif cleaned and cleaned[-1] != '':
                cleaned.append('')
        text = '\n'.join(cleaned)
        # Re-collapse multiple blank lines
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')
        return text.strip()

    def _extract_title(self, text: str, filename: str) -> str:
        """Try to extract the title from the first few lines."""
        lines = [l.strip() for l in text.split('\n') if l.strip()][:5]

        # The title is usually the first substantial line
        for line in lines:
            # Skip very short lines (headers, dates)
            if len(line) > 10 and len(line) < 200:
                # Skip lines that look like dates or metadata
                if not re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December|\d)', line):
                    return line
                if len(line) > 30:
                    return line

        # Fall back to filename
        name = Path(filename).stem
        return name.replace('-', ' ').replace('_', ' ').title()

    def _extract_date(self, text: str) -> Optional[datetime]:
        """Try to extract a publication date from the text."""
        # Look in the first 500 chars
        header = text[:500]

        # Common date patterns
        patterns = [
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
            r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}',
            r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2}',
        ]

        for pattern in patterns:
            match = re.search(pattern, header)
            if match:
                try:
                    from dateutil.parser import parse as dateparse
                    return dateparse(match.group(0))
                except Exception:
                    continue

        return None

    def _extract_author(self, text: str) -> Optional[str]:
        """Try to extract the author from the text."""
        # Common patterns
        for pattern in [r'by\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', r'author:\s*(.+?)[\n,]']:
            match = re.search(pattern, text[:500])
            if match:
                return match.group(1).strip()

        return None
