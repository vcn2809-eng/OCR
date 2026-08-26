"""Custom exceptions for the Ingestion Agent."""

class IngestionError(Exception):
    """Base exception for ingestion failures."""

class DuplicateFileError(IngestionError):
    """Raised when a file's hash already exists in the system."""

class UnsupportedFileTypeError(IngestionError):
    """Raised when the detected file type is not supported."""

class FileReadError(IngestionError):
    """Raised when a file cannot be read or hashed."""
