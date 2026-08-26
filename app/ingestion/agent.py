"""
Ingestion Agent — detects new files in the input folder, verifies real file type via magic bytes,
deduplicates by SHA-256 hash, and enqueues verified files for downstream processing.
"""

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Optional

try:
    import filetype
except ImportError:
    filetype = None

from app.config import settings
from app.ingestion.exceptions import (
    IngestionError,
    DuplicateFileError,
    UnsupportedFileTypeError,
    FileReadError,
)

logger = logging.getLogger(__name__)

def _persistence():
    from app.persistence import agent as _persistence_agent
    return _persistence_agent

def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
    except IOError as e:
        raise FileReadError(f"Failed to read file {file_path} for hashing: {e}") from e
    return sha256.hexdigest()

def detect_true_file_type(file_path: Path) -> str:
    """Detect file type using magic bytes."""
    try:
        if filetype is not None:
            kind = filetype.guess(str(file_path))
        else:
            kind = None
    except IOError as e:
        raise FileReadError(f"Failed to read file {file_path} for type detection: {e}") from e

    detected_type = "unknown"
    if kind is not None:
        mime = kind.mime
        if mime == "application/pdf":
            detected_type = "pdf"
        elif mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            detected_type = "xlsx"
        elif mime == "application/vnd.ms-excel":
            detected_type = "xls"
        elif mime == "text/csv":
            detected_type = "csv"
    else:
        if file_path.suffix.lower() == ".csv":
            detected_type = "csv"
            
    file_ext = file_path.suffix.lstrip(".").lower()
    if file_ext and detected_type != "unknown" and detected_type != file_ext:
        logger.warning(f"File extension mismatch for {file_path}: Extension is {file_ext} but detected type is {detected_type}")
        
    return detected_type

def scan_input_folder(folder_path: str) -> list[Path]:
    """Scan folder for new, valid files."""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise IngestionError(f"Input folder does not exist or is not a directory: {folder_path}")

    new_files = []
    persistence_agent = _persistence()

    files_scanned = 0
    duplicates_skipped = 0
    
    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
            
        ext = file_path.suffix.lstrip(".").lower()
        if ext not in getattr(settings, "ALLOWED_EXTENSIONS", []):
            continue
            
        files_scanned += 1
        try:
            file_hash = compute_file_hash(file_path)
            if persistence_agent.hash_exists_in_raw_documents(file_hash) or persistence_agent.hash_exists_in_queue(file_hash):
                logger.info(f"Duplicate file skipped: {file_path}")
                duplicates_skipped += 1
                continue
            new_files.append(file_path)
        except Exception as e:
            logger.error(f"Error scanning file {file_path}: {e}")
            
    logger.info(f"Scan summary for {folder_path}: Scanned {files_scanned} files, skipped {duplicates_skipped} duplicates, found {len(new_files)} new files.")
    return new_files

def enqueue_file(file_path: Path, file_hash: str, file_type: str) -> str:
    """Enqueue a file for processing."""
    document_id = str(uuid.uuid4())
    persistence_agent = _persistence()
    try:
        persistence_agent.enqueue_document(document_id, str(file_path), file_hash, file_type)
        logger.info(f"Enqueued document {document_id} from {file_path}")
        return document_id
    except Exception as e:
        raise IngestionError(f"Failed to enqueue document {document_id}: {e}") from e

def get_next_queued_document() -> dict | None:
    """Get the next document from the queue."""
    persistence_agent = _persistence()
    docs = persistence_agent.get_next_queued_documents(batch_size=1)
    if docs:
        return docs[0]
    return None

def ingest_folder(folder_path: str) -> list[str]:
    """Scan folder, detect types, compute hashes, and enqueue new files."""
    new_files = scan_input_folder(folder_path)
    enqueued_ids = []
    for file_path in new_files:
        try:
            file_type = detect_true_file_type(file_path)
            file_hash = compute_file_hash(file_path)
            doc_id = enqueue_file(file_path, file_hash, file_type)
            enqueued_ids.append(doc_id)
        except Exception as e:
            logger.error(f"Failed to ingest file {file_path}: {e}", exc_info=True)
            
    return enqueued_ids
