from abc import ABC, abstractmethod
import logging
import numpy as np

from app.ocr.models import OCRResult, WordResult
from app.ocr.exceptions import OCRFailureError, TesseractNotFoundError
from app.config.settings import TESSERACT_LANG, TESSERACT_CONFIG

logger = logging.getLogger(__name__)


class OCREngine(ABC):
    """Abstract interface for OCR engines.
    Implement this to add PaddleOCR, Cloud Vision, etc. without changing calling code.
    """

    @abstractmethod
    def run(self, image: np.ndarray) -> OCRResult:
        """Run OCR on a single image and return structured result."""
        ...


class TesseractEngine(OCREngine):
    """OCR engine backed by Tesseract via pytesseract."""

    def __init__(self) -> None:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._pytesseract = pytesseract
        except Exception as exc:
            raise TesseractNotFoundError(
                f"Tesseract is not installed or not on PATH: {exc}. "
                "Install with: brew install tesseract (macOS) or apt install tesseract-ocr (Ubuntu)"
            ) from exc

    def run(self, image: np.ndarray) -> OCRResult:
        """Run Tesseract OCR on a single image."""
        # Handle blank/uniform images
        if image.std() < 1.0:
            return OCRResult(full_text='', words=[], page_confidence=0.0)

        try:
            data = self._pytesseract.image_to_data(
                image,
                output_type=self._pytesseract.Output.DICT,
                lang=TESSERACT_LANG,
                config=TESSERACT_CONFIG,
            )
        except Exception as exc:
            raise OCRFailureError(f"Tesseract OCR failed: {exc}") from exc

        words: list[WordResult] = []
        for i, text in enumerate(data['text']):
            conf = data['conf'][i]
            if conf < 0 or not str(text).strip():
                continue
            words.append(WordResult(
                text=str(text),
                confidence=float(conf) / 100.0,
                bounding_box={
                    'x': int(data['left'][i]),
                    'y': int(data['top'][i]),
                    'width': int(data['width'][i]),
                    'height': int(data['height'][i]),
                },
            ))

        full_text = ' '.join(w.text for w in words)
        page_confidence = float(sum(w.confidence for w in words) / len(words)) if words else 0.0

        return OCRResult(full_text=full_text, words=words, page_confidence=page_confidence)
