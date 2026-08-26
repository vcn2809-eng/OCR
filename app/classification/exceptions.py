"""Custom exceptions for the Classification Agent."""

class ClassificationError(Exception):
    """Base exception for classification failures."""

class LLMClassificationError(ClassificationError):
    """Raised when the LLM fallback call fails."""
