"""Extraction stage: native text via PyMuPDF, OCR fallback for pages without a text layer."""

import io

import fitz
import structlog
from PIL import Image

from kanuni_ingest.models import ExtractedDocument, ExtractedPage, ExtractionMethod
from kanuni_ingest.stages.ocr import OCREngine

logger = structlog.get_logger()

_NATIVE_TEXT_MIN_CHARS = 50
_OCR_RENDER_DPI = 300


async def extract_document(
    pdf_bytes: bytes, *, ocr_engine: OCREngine, ocr_languages: str
) -> ExtractedDocument:
    """Extract text from every page of a PDF, routing scanned pages through OCR.

    A page is treated as scanned when its native text layer yields fewer
    than 50 characters but the page contains at least one image
    (PROJECT_SPEC.md §7 stage 2's heuristic); a page with neither text nor
    images is left as an (empty) native page rather than sent to OCR.

    Args:
        pdf_bytes: The raw PDF file content.
        ocr_engine: OCR engine used for pages without a usable text layer.
        ocr_languages: Tesseract language codes to pass to the OCR engine.

    Returns:
        The per-page extraction result, in page order.
    """
    pages: list[ExtractedPage] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index in range(document.page_count):
            page = document[page_index]
            page_number = page_index + 1
            native_text = page.get_text()

            if len(native_text.strip()) >= _NATIVE_TEXT_MIN_CHARS or not page.get_images():
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=native_text,
                        extraction_method=ExtractionMethod.NATIVE,
                    )
                )
                continue

            logger.info("routing_page_to_ocr", page_number=page_number)
            pixmap = page.get_pixmap(dpi=_OCR_RENDER_DPI)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            ocr_text, confidence = await ocr_engine.recognize(image, ocr_languages)
            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    text=ocr_text,
                    extraction_method=ExtractionMethod.OCR,
                    ocr_confidence=confidence,
                )
            )

    return ExtractedDocument(pages=pages)
