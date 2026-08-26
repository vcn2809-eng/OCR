import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    db_path = Path(DATABASE_PATH)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_database() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS raw_documents (
        document_id        TEXT PRIMARY KEY,
        file_hash           TEXT NOT NULL UNIQUE,
        original_filename   TEXT NOT NULL,
        file_type           TEXT NOT NULL,
        document_type       TEXT,
        uploaded_at          TEXT NOT NULL,
        raw_extracted_json  TEXT
    );

    CREATE TABLE IF NOT EXISTS invoices (
        document_id     TEXT PRIMARY KEY REFERENCES raw_documents(document_id),
        invoice_number  TEXT,
        customer_name   TEXT,
        total_amount    REAL,
        invoice_date    TEXT,
        updated_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS extracted_documents (
        document_id      TEXT PRIMARY KEY REFERENCES raw_documents(document_id),
        document_type    TEXT NOT NULL,
        confidence       REAL,
        extracted_json   TEXT NOT NULL,
        model_used       TEXT NOT NULL,
        extracted_at     TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS quarantine (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id    TEXT NOT NULL,
        document_type  TEXT,
        record_json    TEXT NOT NULL,
        reasons_json   TEXT NOT NULL,
        flagged_at     TEXT NOT NULL,
        reviewed       INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS processing_log (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id   TEXT NOT NULL,
        stage         TEXT NOT NULL,
        status        TEXT NOT NULL,
        message       TEXT,
        timestamp     TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS processing_queue (
        document_id  TEXT PRIMARY KEY,
        file_path    TEXT NOT NULL,
        file_hash    TEXT NOT NULL UNIQUE,
        file_type    TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'queued',
        created_at   TEXT NOT NULL
    );
    """

    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(schema)
    logger.info("Database initialized at %s", db_path)


def save_raw_document(document_id: str, file_hash: str, filename: str, file_type: str, document_type: str | None, raw_data: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO raw_documents (document_id, file_hash, original_filename, file_type, document_type, uploaded_at, raw_extracted_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                file_hash,
                filename,
                file_type,
                document_type,
                _now(),
                json.dumps(raw_data),
            ),
        )
    logger.info("Archived raw document %s (%s)", document_id, filename)


def save_extracted_document(document_id: str, document_type: str, confidence: float | None, extracted_fields: dict, model_used: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO extracted_documents (document_id, document_type, confidence, extracted_json, model_used, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                document_type,
                confidence,
                json.dumps(extracted_fields),
                model_used,
                _now(),
            ),
        )
    logger.info("Saved extracted document %s", document_id)


def save_to_quarantine(document_id: str, document_type: str, record: dict, reasons: list[str]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO quarantine (document_id, document_type, record_json, reasons_json, flagged_at, reviewed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                document_id,
                document_type,
                json.dumps(record),
                json.dumps(reasons),
                _now(),
            ),
        )


def log_stage(document_id: str, stage: str, status: str, message: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO processing_log (document_id, stage, status, message, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                document_id,
                stage,
                status,
                message,
                _now(),
            ),
        )


def get_extracted_document(document_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM extracted_documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "document_id": row["document_id"],
        "document_type": row["document_type"],
        "confidence": row["confidence"],
        "extracted_json": json.loads(row["extracted_json"]),
        "model_used": row["model_used"],
        "extracted_at": row["extracted_at"],
    }


def get_document_status(document_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM processing_log WHERE document_id = ? ORDER BY id",
            (document_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def hash_already_exists(file_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM raw_documents WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()
    return row is not None
