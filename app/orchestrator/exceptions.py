"""Custom exceptions for the Orchestrator Agent."""

class OrchestratorError(Exception):
    """Base exception for orchestrator failures."""

class DocumentNotFoundError(OrchestratorError):
    """Raised when the requested document_id is not found in the processing queue."""

class PipelineStageError(OrchestratorError):
    """Raised when a pipeline stage fails and cannot be retried."""
