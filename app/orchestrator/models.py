"""State machine models for the Orchestrator Agent."""
from dataclasses import dataclass, field
from enum import Enum


class PipelineStage(str, Enum):
    """All possible pipeline stages, including terminal states."""
    QUEUED = 'QUEUED'
    CLASSIFIED = 'CLASSIFIED'
    EXTRACTED = 'EXTRACTED'
    NORMALIZED = 'NORMALIZED'
    MAPPED = 'MAPPED'
    VALIDATED = 'VALIDATED'
    STORED = 'STORED'
    QUARANTINED = 'QUARANTINED'
    DONE = 'DONE'
    FAILED = 'FAILED'


@dataclass
class ProcessingOutcome:
    """Result of processing a single document through the pipeline."""
    document_id: str
    final_stage: PipelineStage
    success: bool
    error_message: str = ''
    accepted_count: int = 0
    quarantined_count: int = 0
