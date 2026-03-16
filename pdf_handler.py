"""
PDF Handler — Process native and image-based PDFs.
Detects whether a page has selectable text or needs OCR.
"""

import io
from pathlib import Path
from typing import Generator

import fitz  # PyMuPDF
from PIL import Image


def is_image_based_page(page: fitz.Page, min_text_length: int = 20) -> bool:
    """
    Determine if a PDF page is image-based (scanned) or has native text.
    A page with very little extractable text is considered image-based.
    """
    text = page.get_text("text").strip()
    return len(text) < min_text_length


def extract_text_from_page(page: fitz.Page) -> str:
    """Extract native text from a PDF page."""
    return page.get_text("text")


def page_to_image(page: fitz.Page, dpi: int = 200) -> Image.Image:
    """Render a PDF page to a PIL Image at the given DPI."""
    zoom = dpi / 72  # 72 is the default PDF resolution
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)
    img_bytes = pixmap.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def process_pdf(file_path: str | Path) -> Generator[dict, None, None]:
    """
    Process a PDF file page by page.
    Yields a dict per page:
      - page_num: 1-based page number
      - method: "native_text" or "ocr_needed"
      - text: extracted text (if native) or None
      - image: PIL Image (if OCR needed) or None
    """
    doc = fitz.open(str(file_path))
    try:
        for i, page in enumerate(doc):
            if is_image_based_page(page):
                yield {
                    "page_num": i + 1,
                    "method": "ocr_needed",
                    "text": None,
                    "image": page_to_image(page),
                }
            else:
                yield {
                    "page_num": i + 1,
                    "method": "native_text",
                    "text": extract_text_from_page(page),
                    "image": None,
                }
    finally:
        doc.close()


def process_pdf_from_bytes(file_bytes: bytes) -> Generator[dict, None, None]:
    """
    Process a PDF from raw bytes (for Streamlit file uploader).
    Same output as process_pdf.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        for i, page in enumerate(doc):
            if is_image_based_page(page):
                yield {
                    "page_num": i + 1,
                    "method": "ocr_needed",
                    "text": None,
                    "image": page_to_image(page),
                }
            else:
                yield {
                    "page_num": i + 1,
                    "method": "native_text",
                    "text": extract_text_from_page(page),
                    "image": None,
                }
    finally:
        doc.close()


def get_pdf_page_count(file_bytes: bytes) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
