"""Custom exceptions for the OCR Agent."""

class OCRError(Exception):
    """Base exception for OCR failures."""

class OCRFailureError(OCRError):
    """Raised when OCR processing fails on an image."""

class TesseractNotFoundError(OCRFailureError):
    """Raised when Tesseract is not installed or not found on PATH."""
