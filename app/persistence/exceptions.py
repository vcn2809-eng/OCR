"""Custom exceptions for the Persistence Agent."""


class PersistenceError(Exception):
    """Base exception for all persistence-layer errors."""


class RecordNotFoundError(PersistenceError):
    """Raised when a requested record does not exist in the database."""


class UnsupportedDocumentTypeError(PersistenceError):
    """Raised when save_record is called with a document_type that has no normalized table."""
