"""Tests for the Persistence Agent using an in-memory SQLite database."""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.persistence import database, agent
from app.persistence.models import Base
from app.persistence.exceptions import UnsupportedDocumentTypeError


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Creates a fresh in-memory database for each test."""
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    test_session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    
    monkeypatch.setattr(database, "_engine", test_engine)
    monkeypatch.setattr(database, "_SessionFactory", test_session_factory)
    
    database.init_db()
    
    yield
    
    Base.metadata.drop_all(test_engine)


def test_save_and_retrieve_raw_document():
    doc_id = "doc_123"
    file_hash = "hash_123"
    agent.save_raw_document(
        document_id=doc_id,
        file_hash=file_hash,
        filename="test.pdf",
        file_type="pdf",
        document_type="invoice",
        raw_data='{"raw": "data"}'
    )
    
    doc = agent.get_raw_document(doc_id)
    assert doc is not None
    assert doc["document_id"] == doc_id
    assert doc["file_hash"] == file_hash
    assert doc["document_type"] == "invoice"


def test_save_record_invoice():
    doc_id = "doc_inv_1"
    agent.save_raw_document(doc_id, "h1", "f.pdf", "pdf", "invoice", None)
    
    record = {
        "invoice_number": "INV-001",
        "customer_name": "Acme Corp",
        "total_amount": 100.50
    }
    
    agent.save_record(doc_id, "invoice", record)
    
    saved = agent.get_document_record(doc_id)
    assert saved is not None
    assert saved["invoice_number"] == "INV-001"
    assert float(saved["total_amount"]) == 100.50


def test_upsert_does_not_duplicate():
    doc_id = "doc_upsert"
    agent.save_raw_document(doc_id, "h_up", "f.pdf", "pdf", "invoice", None)
    
    agent.save_record(doc_id, "invoice", {"invoice_number": "001"})
    agent.save_record(doc_id, "invoice", {"invoice_number": "002"})
    
    with database.get_db_session() as session:
        from app.persistence.models import Invoice
        from sqlalchemy import select
        count = session.execute(select(Invoice).where(Invoice.document_id == doc_id)).scalars().all()
        assert len(count) == 1
        assert count[0].invoice_number == "002"


def test_save_to_quarantine():
    doc_id = "doc_q_1"
    agent.save_to_quarantine(doc_id, "invoice", {"bad": "data"}, ["Missing total"])
    
    items = agent.get_quarantine_items()
    assert len(items) == 1
    assert items[0]["document_id"] == doc_id
    assert "Missing total" in items[0]["reasons"]


def test_log_stage():
    doc_id = "doc_log_1"
    agent.log_stage(doc_id, "OCR", "SUCCESS", "Extracted 10 lines")
    
    logs = agent.get_processing_status(doc_id)
    assert len(logs) == 1
    assert logs[0]["stage"] == "OCR"
    assert logs[0]["status"] == "SUCCESS"


def test_hash_exists_functions():
    doc_id = "doc_hash_1"
    file_hash = "hash_unique_1"
    
    assert agent.hash_exists_in_queue(file_hash) is False
    assert agent.hash_exists_in_raw_documents(file_hash) is False
    
    agent.enqueue_document(doc_id, "/path", file_hash, "pdf")
    
    assert agent.hash_exists_in_queue(file_hash) is True
    assert agent.hash_exists_in_raw_documents(file_hash) is False


def test_update_queue_status():
    doc_id = "doc_queue_1"
    agent.enqueue_document(doc_id, "/path", "hash_q", "pdf")
    
    agent.update_queue_status(doc_id, "processing", "invoice", 0.95)
    
    with database.get_db_session() as session:
        from app.persistence.models import ProcessingQueue
        item = session.get(ProcessingQueue, doc_id)
        assert item.status == "processing"
        assert item.document_type == "invoice"
        assert item.classification_confidence == 0.95
