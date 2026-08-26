"""Custom exceptions for the Learning Agent."""


class LearningError(Exception):
    """Base exception for learning agent errors."""


class AliasNotFoundError(LearningError):
    """Raised when an requested alias is not found."""


class InvalidAliasError(LearningError):
    """Raised when an invalid alias or canonical name is provided."""
