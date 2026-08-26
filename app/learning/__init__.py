"""Learning Agent package."""

from app.learning.agent import (
    learn_alias,
    resolve_alias,
    extract_partial_values,
    learn_from_document,
    get_all_learned_aliases,
    bulk_learn_aliases,
)
from app.learning.exceptions import LearningError, AliasNotFoundError
from app.learning.models import AliasMapping, MatchResult

__all__ = [
    "learn_alias",
    "resolve_alias",
    "extract_partial_values",
    "learn_from_document",
    "get_all_learned_aliases",
    "bulk_learn_aliases",
    "LearningError",
    "AliasNotFoundError",
    "AliasMapping",
    "MatchResult",
]
