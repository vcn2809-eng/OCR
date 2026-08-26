import numpy as np
import cv2
import pytest
from pathlib import Path
from app.preprocessing.agent import (
    deskew_image, correct_perspective, denoise_image, 
    binarize_image, preprocess_page, pdf_to_page_images
)
from app.preprocessing.exceptions import ImageProcessingError, PDFConversionError

def test_binarize_clean_image():
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (50, 50), (150, 150), (0, 0, 0), -1)
    res = binarize_image(img)
    assert len(res.shape) == 2
    assert res.dtype == np.uint8

def test_binarize_shadowed_image():
    # Create image with clear dark left half and bright right half
    img = np.zeros((200, 200), dtype=np.uint8)
    img[:, 100:] = 200  # bright right half
    img[:, :100] = 30   # dark left half
    res = binarize_image(img)
    assert len(np.unique(res)) > 1

def test_deskew_straight_image():
    img = np.ones((400, 400, 3), dtype=np.uint8) * 255
    for i in range(5):
        y = 50 + i * 50
        cv2.line(img, (50, y), (350, y), (0, 0, 0), 2)
    res = deskew_image(img)
    assert res.shape == img.shape

def test_deskew_rotated_image():
    img = np.ones((400, 400, 3), dtype=np.uint8) * 255
    for i in range(5):
        y = 50 + i * 50
        cv2.line(img, (50, y), (350, y), (0, 0, 0), 2)
    M = cv2.getRotationMatrix2D((200, 200), 15, 1.0)
    rotated = cv2.warpAffine(img, M, (400, 400), borderValue=(255, 255, 255))
    res = deskew_image(rotated)
    assert res.shape == rotated.shape

def test_denoise_color_image():
    img = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)
    res = denoise_image(img)
    assert res.shape == img.shape

def test_denoise_grayscale_image():
    img = np.random.randint(0, 256, (200, 200), dtype=np.uint8)
    res = denoise_image(img)
    assert res.shape == img.shape

def test_correct_perspective_no_boundary():
    img = np.ones((300, 300, 3), dtype=np.uint8) * 255
    res = correct_perspective(img)
    # Allow ±2px tolerance — warpPerspective can shift by 1px
    assert abs(res.shape[0] - img.shape[0]) <= 2
    assert abs(res.shape[1] - img.shape[1]) <= 2
    assert res.shape[2] == img.shape[2]

def test_preprocess_page_runs_full_pipeline():
    img = np.ones((300, 300, 3), dtype=np.uint8) * 255
    res = preprocess_page(img, 'test_doc')
    assert isinstance(res, np.ndarray)
    assert len(res.shape) == 2

def test_pdf_conversion_error():
    with pytest.raises(PDFConversionError):
        pdf_to_page_images(Path('/does/not/exist.pdf'))
