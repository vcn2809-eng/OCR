"""
Table Detection Agent — detects tables in PDF page images by locating grid lines (primary)
or clustering word bounding boxes by position (fallback when no visible lines exist).
"""
import logging
from typing import Optional

import cv2
import numpy as np

from app.ocr.models import OCRResult, WordResult
from app.table_detection.models import BoundingBox
from app.table_detection.exceptions import TableDetectionError

logger = logging.getLogger(__name__)


def _words_in_region(words: list[WordResult], region: BoundingBox) -> list[WordResult]:
    """Filter words whose center point falls inside the given bounding box."""
    result = []
    for w in words:
        bb = w.bounding_box
        cx = bb['x'] + bb['width'] // 2
        cy = bb['y'] + bb['height'] // 2
        if (region.x <= cx <= region.x + region.width and
                region.y <= cy <= region.y + region.height):
            result.append(w)
    return result


def _cluster_by_coordinate(values: list[float], tolerance: float) -> list[int]:
    """Assign each value a cluster index by greedy proximity grouping."""
    centers: list[float] = []
    assignments: list[int] = []
    for v in values:
        matched = False
        for idx, center in enumerate(centers):
            if abs(v - center) <= tolerance:
                assignments.append(idx)
                centers[idx] = (center + v) / 2  # update center
                matched = True
                break
        if not matched:
            assignments.append(len(centers))
            centers.append(v)
    return assignments


def detect_table_regions(image: np.ndarray) -> list[BoundingBox]:
    """Detect grid-line-based table regions using HoughLinesP.
    Returns empty list if no clear grid is found.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
        short_dim = min(image.shape[:2])
        min_length = int(short_dim * 0.3)
        lines = cv2.HoughLinesP(
            binary, 1, np.pi / 180, threshold=80,
            minLineLength=min_length, maxLineGap=20
        )
        if lines is None:
            return []

        h_lines, v_lines = [], []
        for line in lines:
            pts = line.flatten()[:4]
            x1, y1, x2, y2 = pts
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if angle < 10:
                h_lines.append(pts)
            elif angle > 80:
                v_lines.append(pts)

        if len(h_lines) < 2 or len(v_lines) < 2:
            return []

        all_pts = h_lines + v_lines
        xs = [pt[0] for pt in all_pts] + [pt[2] for pt in all_pts]
        ys = [pt[1] for pt in all_pts] + [pt[3] for pt in all_pts]
        x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        return [BoundingBox(x=x, y=y, width=w, height=h)]
    except Exception as exc:
        logger.error("detect_table_regions failed: %s", exc)
        return []


def cluster_words_into_rows_and_columns(
    ocr_result: OCRResult,
    table_region: BoundingBox,
) -> list[list[str]]:
    """Cluster OCR words into a 2D grid using position proximity."""
    words = _words_in_region(ocr_result.words, table_region)
    if not words:
        return []

    Y_TOLERANCE = 10
    X_TOLERANCE = 20

    # Assign row clusters by y-coordinate
    y_centers = [w.bounding_box['y'] + w.bounding_box['height'] // 2 for w in words]
    row_ids = _cluster_by_coordinate(y_centers, Y_TOLERANCE)
    num_rows = max(row_ids) + 1 if row_ids else 0

    # Assign col clusters by x-coordinate
    x_centers = [w.bounding_box['x'] + w.bounding_box['width'] // 2 for w in words]
    col_ids = _cluster_by_coordinate(x_centers, X_TOLERANCE)
    num_cols = max(col_ids) + 1 if col_ids else 0

    if num_rows == 0 or num_cols == 0:
        return []

    # Build grid
    grid: list[list[str]] = [['' for _ in range(num_cols)] for _ in range(num_rows)]
    for word, row_id, col_id in zip(words, row_ids, col_ids):
        existing = grid[row_id][col_id]
        grid[row_id][col_id] = (existing + ' ' + word.text).strip() if existing else word.text

    return grid


def extract_tables_from_page(
    document_id: str,
    page_number: int,
    image: np.ndarray,
    ocr_result: OCRResult,
) -> list[list[list[str]]]:
    """Extract all tables from a single page.
    Uses line detection first; falls back to position clustering.
    """
    try:
        regions = detect_table_regions(image)

        if regions:
            tables = []
            for region in regions:
                table = cluster_words_into_rows_and_columns(ocr_result, region)
                if table:
                    tables.append(table)
            logger.info("Document %s page %d: %d table(s) found via line detection",
                        document_id, page_number, len(tables))
            return tables

        # Fallback: try full-page position clustering
        h, w = image.shape[:2]
        full_region = BoundingBox(x=0, y=0, width=w, height=h)
        table = cluster_words_into_rows_and_columns(ocr_result, full_region)

        # Only return if it looks like a real table (>= 2 rows AND >= 2 cols with content)
        if table and len(table) >= 2 and any(len(row) >= 2 for row in table):
            logger.info("Document %s page %d: 1 table found via position clustering",
                        document_id, page_number)
            return [table]

        logger.info("Document %s page %d: no tables detected", document_id, page_number)
        return []
    except Exception as exc:
        logger.error("extract_tables_from_page failed for doc %s page %d: %s",
                     document_id, page_number, exc)
        return []
