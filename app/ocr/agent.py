import logging
from typing import Optional

import numpy as np

from app.ocr.engine import OCREngine, TesseractEngine
from app.ocr.models import OCRResult, WordResult
from app.ocr.exceptions import OCRFailureError
from app.config.settings import OCR_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


def run_ocr(image: np.ndarray, engine: Optional[OCREngine] = None) -> OCRResult:
    """Run OCR on a single page image. Uses TesseractEngine by default."""
    if engine is None:
        engine = TesseractEngine()
    result = engine.run(image)
    logger.info("Page OCR complete. Confidence: %.2f", result.page_confidence)
    if result.page_confidence < OCR_CONFIDENCE_THRESHOLD:
        logger.warning(
            "Low OCR confidence %.2f (threshold %.2f)",
            result.page_confidence, OCR_CONFIDENCE_THRESHOLD,
        )
    return result


def run_ocr_on_document(
    document_id: str,
    images: list[np.ndarray],
    engine: Optional[OCREngine] = None,
) -> list[OCRResult]:
    """Run OCR on every page of a document, returning results in page order.
    If a single page fails, an empty OCRResult is inserted for that page.
    """
    if engine is None:
        try:
            engine = TesseractEngine()
        except Exception as exc:
            logger.error("Cannot initialise OCR engine for document %s: %s", document_id, exc)
            raise OCRFailureError(str(exc)) from exc

    logger.info("Starting OCR on document %s (%d pages)", document_id, len(images))
    results: list[OCRResult] = []
    for page_num, image in enumerate(images):
        try:
            result = run_ocr(image, engine)
            result.page_number = page_num
            results.append(result)
        except OCRFailureError as exc:
            logger.error("OCR failed on page %d of document %s: %s", page_num, document_id, exc)
            results.append(OCRResult(full_text='', words=[], page_confidence=0.0, page_number=page_num))
    return results


def get_document_text(ocr_results: list[OCRResult]) -> str:
    """Join full_text from all pages with page-break separators."""
    return '\n\n--- Page Break ---\n\n'.join(r.full_text for r in ocr_results)


def get_low_confidence_pages(
    ocr_results: list[OCRResult],
    threshold: Optional[float] = None,
) -> list[int]:
    """Return indices of pages whose confidence is below the threshold."""
    if threshold is None:
        threshold = OCR_CONFIDENCE_THRESHOLD
    return [r.page_number for r in ocr_results if r.page_confidence < threshold]
