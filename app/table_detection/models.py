"""Data models for Table Detection Agent."""
from dataclasses import dataclass


@dataclass
class BoundingBox:
    """Rectangular region on a page."""
    x: int
    y: int
    width: int
    height: int
