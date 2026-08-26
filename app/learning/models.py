"""Data models for the Learning Agent."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class AliasMapping:
    """Represents a learned alias mapping."""

    alias: str
    canonical_name: str
    category: str = "header"  # 'header', 'term', 'unit', 'custom'
    confidence: float = 1.0
    occurrence_count: int = 1


@dataclass
class MatchResult:
    """Outcome of resolving an alias or partial value."""

    original_text: str
    canonical_name: str
    match_type: Literal["exact", "alias", "partial", "abbreviation", "fuzzy"]
    similarity_score: float  # 0.0 to 1.0
    category: str = "header"
    start_index: int = 0
    end_index: int = 0
