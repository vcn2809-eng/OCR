import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.ingestion.agent import (
    compute_file_hash,
    detect_true_file_type,
    scan_input_folder,
    enqueue_file,
)
from app.ingestion.exceptions import IngestionError, FileReadError

def test_compute_file_hash_consistency(tmp_path):
    file_path = tmp_path / "test1.txt"
    file_path.write_text("Hello, world!")
    
    hash1 = compute_file_hash(file_path)
    hash2 = compute_file_hash(file_path)
    
    assert hash1 == hash2

def test_compute_file_hash_different(tmp_path):
    file1 = tmp_path / "test1.txt"
    file1.write_text("Hello, world!")
    
    file2 = tmp_path / "test2.txt"
    file2.write_text("Goodbye, world!")
    
    hash1 = compute_file_hash(file1)
    hash2 = compute_file_hash(file2)
    
    assert hash1 != hash2

@patch("app.ingestion.agent.filetype.guess")
def test_detect_true_file_type_pdf(mock_guess, tmp_path):
    file_path = tmp_path / "test.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")
    
    mock_kind = MagicMock()
    mock_kind.mime = "application/pdf"
    mock_guess.return_value = mock_kind
    
    detected_type = detect_true_file_type(file_path)
    assert detected_type == "pdf"

@patch("app.ingestion.agent.filetype.guess")
@patch("app.ingestion.agent.logger.warning")
def test_detect_mismatch_logs_warning(mock_warning, mock_guess, tmp_path):
    file_path = tmp_path / "test.xlsx"
    file_path.write_bytes(b"%PDF-1.4\n")
    
    mock_kind = MagicMock()
    mock_kind.mime = "application/pdf"
    mock_guess.return_value = mock_kind
    
    detected_type = detect_true_file_type(file_path)
    assert detected_type == "pdf"
    mock_warning.assert_called_once()
    assert "Extension is xlsx but detected type is pdf" in mock_warning.call_args[0][0]

@patch("app.ingestion.agent.settings")
@patch("app.ingestion.agent._persistence")
def test_scan_input_folder_new_file(mock_persistence, mock_settings, tmp_path):
    mock_settings.ALLOWED_EXTENSIONS = ["pdf", "csv", "xlsx"]
    mock_agent = MagicMock()
    mock_agent.hash_exists_in_raw_documents.return_value = False
    mock_agent.hash_exists_in_queue.return_value = False
    mock_persistence.return_value = mock_agent
    
    file_path = tmp_path / "test.pdf"
    file_path.write_text("dummy")
    
    new_files = scan_input_folder(str(tmp_path))
    assert len(new_files) == 1
    assert new_files[0] == file_path

@patch("app.ingestion.agent.settings")
@patch("app.ingestion.agent._persistence")
def test_scan_input_folder_duplicate_skipped(mock_persistence, mock_settings, tmp_path):
    mock_settings.ALLOWED_EXTENSIONS = ["pdf", "csv", "xlsx"]
    mock_agent = MagicMock()
    mock_agent.hash_exists_in_raw_documents.return_value = False
    mock_agent.hash_exists_in_queue.return_value = True
    mock_persistence.return_value = mock_agent
    
    file_path = tmp_path / "test.pdf"
    file_path.write_text("dummy")
    
    new_files = scan_input_folder(str(tmp_path))
    assert len(new_files) == 0

def test_scan_input_folder_nonexistent():
    with pytest.raises(IngestionError):
        scan_input_folder("/tmp/nonexistent_folder_xyz_123")

@patch("app.ingestion.agent._persistence")
def test_enqueue_file(mock_persistence, tmp_path):
    mock_agent = MagicMock()
    mock_persistence.return_value = mock_agent
    
    file_path = tmp_path / "test.pdf"
    
    doc_id = enqueue_file(file_path, "dummy_hash", "pdf")
    
    assert doc_id is not None
    mock_agent.enqueue_document.assert_called_once_with(doc_id, str(file_path), "dummy_hash", "pdf")

@patch("builtins.open", side_effect=IOError("Mock IOError"))
def test_file_read_error(mock_open, tmp_path):
    file_path = tmp_path / "test.txt"
    with pytest.raises(FileReadError):
        compute_file_hash(file_path)
