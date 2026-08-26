"""Custom exceptions for the Validation Agent."""

class ValidationError(Exception):
    """Raised when the validation pipeline itself fails (not a data validation failure)."""
