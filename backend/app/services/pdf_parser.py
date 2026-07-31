import re

from annotated_types import doc
import fitz
import pdfplumber
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    """Represents a fully parsed contract document."""
    filename: str
    total_pages: int
    raw_text: str
    pages: list[dict]
    metadata: dict


def parse_pdf(file_path: str | Path) -> ParsedDocument:
    """
    Parse a PDF contract and extract structured text.

    Uses pdfplumber as primary parser with PyMuPDF as fallback
    for pages that return no text.

    Args:
        file_path: Path to the PDF file

    Returns:
        ParsedDocument with full text, per-page breakdown, and metadata

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file isn't a PDF or has no extractable text
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    if file_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {file_path.suffix}")

    pages = []
    raw_text_parts = []

    with pdfplumber.open(file_path) as pdf:
        metadata = _extract_metadata(pdf)
        total_pages = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            # If pdfplumber gets nothing, try PyMuPDF
            if not text.strip():
                text = _extract_page_with_pymupdf(str(file_path), page_num - 1)

            text = _clean_text(text)

            pages.append({
                "page_num": page_num,
                "text": text,
                "char_count": len(text),
            })
            raw_text_parts.append(text)

    full_text = "\n\n".join(raw_text_parts)

    if not full_text.strip():
        raise ValueError(
            "No text could be extracted. "
            "The PDF may be scanned or image-based."
        )

    return ParsedDocument(
        filename=file_path.name,
        total_pages=total_pages,
        raw_text=full_text,
        pages=pages,
        metadata=metadata,
    )


def get_document_stats(doc: ParsedDocument) -> dict:
    """Return human-readable stats about a parsed document."""
    non_empty = [p for p in doc.pages if p["char_count"] > 50]
    avg_chars = (
        sum(p["char_count"] for p in non_empty) / len(non_empty)
        if non_empty else 0
    )
    return {
        "filename": doc.filename,
        "total_pages": doc.total_pages,
        "total_characters": len(doc.raw_text),
        "total_words": len(doc.raw_text.split()),
        "non_empty_pages": len(non_empty),
        "avg_chars_per_page": round(avg_chars),
        "words_per_page": [len(p["text"].split()) for p in doc.pages],
    }
    


def _extract_metadata(pdf) -> dict:
    """Pull document metadata from pdfplumber's PDF object."""
    info = pdf.metadata or {}
    return {
        "title": info.get("Title", ""),
        "author": info.get("Author", ""),
        "subject": info.get("Subject", ""),
        "creator": info.get("Creator", ""),
        "page_count": len(pdf.pages),
    }


def _extract_page_with_pymupdf(file_path: str, page_index: int) -> str:
    """Fallback: extract text from a single page using PyMuPDF."""
    doc = fitz.open(file_path)
    page = doc[page_index]
    text = page.get_text("text")
    doc.close()
    return text


def _clean_text(text: str) -> str:
    """
    Clean raw PDF text:
    - Remove null bytes
    - Normalise line endings
    - Collapse excessive whitespace
    """
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def is_likely_scanned(doc: ParsedDocument) -> bool:
    """
    Returns True if the PDF is probably scanned/image-based.
    We detect this by checking how many pages returned very little text.
    If more than half the pages have under 100 characters, it's likely scanned.
    """

    count = 0
    for page in doc.pages:
        if page["char_count"] < 100:
            count += 1
    if count > doc.total_pages / 2:
        return True
    return False

    