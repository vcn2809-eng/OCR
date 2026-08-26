"""
Abstract strategy interface for table detection approaches.

Current implementations: LineBasedStrategy (grid lines), PositionClusteringStrategy (text alignment).
Future extension: ModelBasedStrategy (Table Transformer, PaddleOCR table model) —
add new class here implementing TableDetectionStrategy without modifying any calling code.
"""
from abc import ABC, abstractmethod
import numpy as np
from app.ocr.models import OCRResult
from app.table_detection.models import BoundingBox


class TableDetectionStrategy(ABC):
    """Interface for table detection. Subclass to add model-based approaches."""

    @abstractmethod
    def detect_regions(self, image: np.ndarray) -> list[BoundingBox]:
        """Detect candidate table bounding boxes on the page."""
        ...

    @abstractmethod
    def extract_table(self, ocr_result: OCRResult, region: BoundingBox) -> list[list[str]]:
        """Extract table grid from within a bounding box region."""
        ...
