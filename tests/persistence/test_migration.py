"""Tests for legacy data migration in app/persistence/db.py."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.persistence import database, db, agent
from app.persistence.models import Base, RawDocument, Invoice, Resume, Document, DocumentField


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


def test_migrate_legacy_data():
    # Populate legacy records
    agent.save_raw_document(
        document_id="legacy_inv_101",
        file_hash="legacy_hash_101",
        filename="invoice_101.pdf",
        file_type="pdf",
        document_type="invoice",
        raw_data='{"raw_key": "raw_val"}',
    )
    agent.save_record("legacy_inv_101", "invoice", {
        "invoice_number": "INV-101",
        "customer_name": "East Point College",
        "total_amount": 3363.00,
    })

    agent.save_raw_document(
        document_id="legacy_res_202",
        file_hash="legacy_hash_202",
        filename="resume_202.pdf",
        file_type="pdf",
        document_type="resume",
        raw_data='{"name": "Alice Smith"}',
    )
    agent.save_record("legacy_res_202", "resume", {
        "name": "Alice Smith",
        "email": "alice@example.com",
    })

    # Execute legacy migration
    summary = db.migrate_legacy_data()

    assert summary["migrated_documents"] >= 2
    assert summary["migrated_fields"] >= 4

    # Verify migrated invoice document in EAV schema
    inv_doc = db.get_document_with_fields("legacy_inv_101")
    assert inv_doc is not None
    assert inv_doc["original_filename"] == "invoice_101.pdf"
    assert inv_doc["fields"]["invoice_number"] == "INV-101"
    assert inv_doc["fields"]["customer_name"] == "East Point College"

    # Verify migrated resume document in EAV schema
    res_doc = db.get_document_with_fields("legacy_res_202")
    assert res_doc is not None
    assert res_doc["original_filename"] == "resume_202.pdf"
    assert res_doc["fields"]["email"] == "alice@example.com"
