"""Data models for Classification Agent output."""
from dataclasses import dataclass
from typing import Literal


@dataclass
class ClassificationResult:
    """Result of document classification."""
    document_type: str  # 'invoice', 'resume', 'financial_statement', 'purchase_order', 'generic'
    confidence: float   # 0.0 to 1.0
    method: Literal['heuristic', 'llm_fallback']
