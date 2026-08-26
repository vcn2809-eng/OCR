import numpy as np
import cv2
import pytest
from app.ocr.models import OCRResult, WordResult
from app.table_detection.models import BoundingBox
from app.table_detection.agent import (
    detect_table_regions, cluster_words_into_rows_and_columns,
    extract_tables_from_page, _words_in_region, _cluster_by_coordinate
)


def test_detect_table_regions_with_grid():
    img = np.ones((400, 400, 3), dtype=np.uint8) * 255
    cv2.line(img, (50, 50), (350, 50), (0, 0, 0), 2)
    cv2.line(img, (50, 200), (350, 200), (0, 0, 0), 2)
    cv2.line(img, (50, 350), (350, 350), (0, 0, 0), 2)
    cv2.line(img, (50, 50), (50, 350), (0, 0, 0), 2)
    cv2.line(img, (200, 50), (200, 350), (0, 0, 0), 2)
    cv2.line(img, (350, 50), (350, 350), (0, 0, 0), 2)
    
    regions = detect_table_regions(img)
    assert len(regions) > 0


def test_detect_table_regions_no_grid():
    img = np.ones((400, 400, 3), dtype=np.uint8) * 255
    regions = detect_table_regions(img)
    assert len(regions) == 0


def test_cluster_by_coordinate():
    values = [10, 12, 50, 52, 100]
    tolerance = 5
    clusters = _cluster_by_coordinate(values, tolerance)
    assert len(set(clusters)) == 3
    assert clusters[0] == clusters[1]
    assert clusters[2] == clusters[3]


def test_cluster_words_into_rows_and_columns():
    words = []
    for y in [50, 100, 150]:
        for x in [50, 150, 250]:
            words.append(WordResult(
                text=f"{x}-{y}",
                confidence=0.9,
                bounding_box={"x": x-10, "y": y-10, "width": 20, "height": 20}
            ))
    ocr_result = OCRResult(full_text="", words=words, page_confidence=0.9, page_number=1)
    region = BoundingBox(x=0, y=0, width=300, height=300)
    
    table = cluster_words_into_rows_and_columns(ocr_result, region)
    assert len(table) == 3
    assert len(table[0]) == 3


def test_words_in_region():
    words = [
        WordResult(text="1", confidence=0.9, bounding_box={"x": 10, "y": 10, "width": 10, "height": 10}),
        WordResult(text="2", confidence=0.9, bounding_box={"x": 50, "y": 50, "width": 10, "height": 10}),
        WordResult(text="3", confidence=0.9, bounding_box={"x": 90, "y": 90, "width": 10, "height": 10}),
        WordResult(text="4", confidence=0.9, bounding_box={"x": 200, "y": 200, "width": 10, "height": 10}),
        WordResult(text="5", confidence=0.9, bounding_box={"x": 250, "y": 250, "width": 10, "height": 10})
    ]
    region = BoundingBox(x=0, y=0, width=150, height=150)
    in_region = _words_in_region(words, region)
    assert len(in_region) == 3


def test_extract_tables_from_page_no_table():
    img = np.ones((400, 400, 3), dtype=np.uint8) * 255
    words = [WordResult(text="hello", confidence=0.9, bounding_box={"x": 10, "y": 10, "width": 20, "height": 10})]
    ocr_result = OCRResult(full_text="hello", words=words, page_confidence=0.9, page_number=1)
    tables = extract_tables_from_page("doc1", 1, img, ocr_result)
    assert len(tables) == 0


def test_extract_tables_from_page_with_grid():
    img = np.ones((400, 400, 3), dtype=np.uint8) * 255
    cv2.line(img, (50, 50), (350, 50), (0, 0, 0), 2)
    cv2.line(img, (50, 200), (350, 200), (0, 0, 0), 2)
    cv2.line(img, (50, 350), (350, 350), (0, 0, 0), 2)
    cv2.line(img, (50, 50), (50, 350), (0, 0, 0), 2)
    cv2.line(img, (200, 50), (200, 350), (0, 0, 0), 2)
    cv2.line(img, (350, 50), (350, 350), (0, 0, 0), 2)
    
    words = []
    for y in [100, 250]:
        for x in [100, 250]:
            words.append(WordResult(
                text=f"cell",
                confidence=0.9,
                bounding_box={"x": x, "y": y, "width": 20, "height": 10}
            ))
    ocr_result = OCRResult(full_text="cell cell cell cell", words=words, page_confidence=0.9, page_number=1)
    tables = extract_tables_from_page("doc1", 1, img, ocr_result)
    assert len(tables) > 0


def test_bounding_box_model():
    bb = BoundingBox(x=10, y=20, width=30, height=40)
    assert bb.x == 10
    assert bb.y == 20
    assert bb.width == 30
    assert bb.height == 40
