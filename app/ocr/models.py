"""Data models for OCR Agent output."""
from dataclasses import dataclass, field


@dataclass
class WordResult:
    """Represents a single OCR'd word with its position and confidence."""
    text: str
    confidence: float  # 0.0 to 1.0
    bounding_box: dict  # {"x": int, "y": int, "width": int, "height": int}


@dataclass
class OCRResult:
    """Full OCR result for a single page."""
    full_text: str
    words: list[WordResult]
    page_confidence: float  # mean of all word confidences (0.0 if no words)
    page_number: int = 0
