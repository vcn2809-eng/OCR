import logging
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from app.ocr.models import OCRResult, WordResult
from app.ocr.agent import run_ocr, run_ocr_on_document, get_document_text, get_low_confidence_pages
from app.ocr.exceptions import OCRFailureError, TesseractNotFoundError
from app.ocr.engine import TesseractEngine


def test_ocr_result_fields():
    word = WordResult(text="hello", confidence=0.9, bounding_box={"x": 0, "y": 0, "width": 10, "height": 10})
    res = OCRResult(full_text="hello", words=[word], page_confidence=0.9, page_number=2)
    assert res.full_text == "hello"
    assert len(res.words) == 1
    assert res.page_confidence == 0.9
    assert res.page_number == 2


def test_word_result_bounding_box():
    bbox = {"x": 10, "y": 20, "width": 30, "height": 40}
    word = WordResult(text="test", confidence=0.95, bounding_box=bbox)
    assert word.bounding_box["x"] == 10
    assert word.bounding_box["y"] == 20
    assert word.bounding_box["width"] == 30
    assert word.bounding_box["height"] == 40


def test_run_ocr_with_mock_engine():
    mock_engine = MagicMock()
    expected = OCRResult(full_text="mocked text", words=[], page_confidence=0.99)
    mock_engine.run.return_value = expected
    
    img = np.zeros((10, 10))
    result = run_ocr(img, engine=mock_engine)
    
    assert result == expected
    mock_engine.run.assert_called_once_with(img)


def test_run_ocr_low_confidence_warning(caplog):
    mock_engine = MagicMock()
    expected = OCRResult(full_text="bad text", words=[], page_confidence=0.2)
    mock_engine.run.return_value = expected
    
    img = np.zeros((10, 10))
    with caplog.at_level(logging.WARNING):
        result = run_ocr(img, engine=mock_engine)
        
    assert result == expected
    assert "Low OCR confidence" in caplog.text


def test_run_ocr_on_document_handles_page_failure():
    mock_engine = MagicMock()
    
    res0 = OCRResult(full_text="page 0", words=[], page_confidence=0.9)
    res2 = OCRResult(full_text="page 2", words=[], page_confidence=0.9)
    
    def mock_run(img):
        if img.shape[0] == 0:
            return res0
        elif img.shape[0] == 1:
            raise OCRFailureError("failed")
        else:
            return res2
            
    mock_engine.run.side_effect = mock_run
    
    images = [np.zeros((0, 0)), np.zeros((1, 1)), np.zeros((2, 2))]
    results = run_ocr_on_document("doc_1", images, engine=mock_engine)
    
    assert len(results) == 3
    assert results[0].full_text == "page 0"
    assert results[1].full_text == ""
    assert results[1].page_confidence == 0.0
    assert results[2].full_text == "page 2"
    assert results[0].page_number == 0
    assert results[1].page_number == 1
    assert results[2].page_number == 2


def test_get_document_text_joins_pages():
    results = [
        OCRResult(full_text="Page 1", words=[], page_confidence=0.9, page_number=0),
        OCRResult(full_text="Page 2", words=[], page_confidence=0.9, page_number=1),
    ]
    text = get_document_text(results)
    assert text == "Page 1\n\n--- Page Break ---\n\nPage 2"


def test_get_low_confidence_pages():
    results = [
        OCRResult(full_text="", words=[], page_confidence=0.9, page_number=0),
        OCRResult(full_text="", words=[], page_confidence=0.3, page_number=1),
        OCRResult(full_text="", words=[], page_confidence=0.8, page_number=2),
    ]
    low = get_low_confidence_pages(results, threshold=0.6)
    assert low == [1]


def test_blank_image_returns_empty_result():
    mock_engine = MagicMock()
    empty = OCRResult(full_text='', words=[], page_confidence=0.0)
    mock_engine.run.return_value = empty
    
    img = np.zeros((100, 100)) # uniform
    res = run_ocr(img, engine=mock_engine)
    assert res.full_text == ''
    assert len(res.words) == 0


def test_tesseract_engine_skipped_if_not_installed():
    """TesseractNotFoundError raised when tesseract binary is unavailable."""
    import sys
    mock_pytesseract = MagicMock()
    mock_pytesseract.get_tesseract_version.side_effect = Exception("Tesseract not found")
    with patch.dict(sys.modules, {'pytesseract': mock_pytesseract}):
        with pytest.raises(TesseractNotFoundError):
            TesseractEngine()
