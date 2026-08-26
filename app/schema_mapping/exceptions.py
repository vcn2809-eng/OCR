"""Custom exceptions for the Schema Mapping Agent."""

class SchemaMappingError(Exception):
    """Base exception for schema mapping failures."""

class MappingNotFoundError(SchemaMappingError):
    """Raised when no mapping exists for the requested document type."""
