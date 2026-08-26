"""Custom exceptions for the Image Preprocessing Agent."""

class PreprocessingError(Exception):
    """Base exception for preprocessing failures."""

class PDFConversionError(PreprocessingError):
    """Raised when PDF-to-image conversion fails."""

class ImageProcessingError(PreprocessingError):
    """Raised when an OpenCV image processing step fails."""
