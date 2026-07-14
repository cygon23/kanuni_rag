"""OCR stage: runs Tesseract (eng+swa) on scanned pages and records per-page confidence."""

from typing import Protocol

import pytesseract
import structlog
from PIL import Image
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from kanuni_ingest.exceptions import ProviderTimeoutError

logger = structlog.get_logger()

_MAX_ATTEMPTS = 3
_TIMEOUT_SECONDS = 30


class OCREngine(Protocol):
    """Recognizes text in a page image, per PROJECT_SPEC.md §7 stage 2, §4.2."""

    async def recognize(self, image: Image.Image, languages: str) -> tuple[str, float]:
        """Run OCR on a single page image.

        Args:
            image: The rendered page image.
            languages: Tesseract language codes, e.g. `"eng+swa"`.

        Returns:
            A tuple of `(recognized_text, mean_confidence_percent)`.
        """
        ...


class TesseractOCREngine:
    """OCR engine backed by the `tesseract` CLI via `pytesseract`."""

    @retry(
        retry=retry_if_exception_type(RuntimeError),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    async def recognize(self, image: Image.Image, languages: str) -> tuple[str, float]:
        """Run Tesseract OCR on a single page image, retrying transient failures.

        Args:
            image: The rendered page image.
            languages: Tesseract language codes, e.g. `"eng+swa"`.

        Returns:
            A tuple of `(recognized_text, mean_confidence_percent)`.

        Raises:
            ProviderTimeoutError: If Tesseract does not finish within the
                configured timeout after all retries are exhausted.
        """
        try:
            text = pytesseract.image_to_string(image, lang=languages, timeout=_TIMEOUT_SECONDS)
            data = pytesseract.image_to_data(
                image,
                lang=languages,
                timeout=_TIMEOUT_SECONDS,
                output_type=pytesseract.Output.DICT,
            )
        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                raise ProviderTimeoutError("Tesseract OCR timed out") from exc
            raise

        confidences = [float(c) for c in data["conf"] if c not in ("-1", -1)]
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return text, mean_confidence
