"""Tests for EAV Schema and persistence functions in app/persistence/db.py."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.persistence import database, db
from app.persistence.models import Base, Document, DocumentField, Vendor


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


def test_save_document_upsert():
    doc_id = "doc_eav_1"
    file_hash = "hash_eav_1"

    # Insert initial document
    res_id = db.save_document(
        document_id=doc_id,
        file_hash=file_hash,
        filename="invoice_001.pdf",
        file_type="pdf",
        document_type="invoice",
        status="processing",
        confidence=0.85,
        raw_text="Invoice #1001 Total $500",
    )
    assert res_id == doc_id

    # Retrieve document
    doc = db.get_document_with_fields(doc_id)
    assert doc is not None
    assert doc["original_filename"] == "invoice_001.pdf"
    assert doc["status"] == "processing"
    assert doc["confidence"] == 0.85

    # Upsert/Update document status, confidence, and vendor
    vendor_id = db.save_vendor("Global Chemical Suppliers", "100 Industrial Way")
    db.save_document(
        document_id=doc_id,
        file_hash=file_hash,
        filename="invoice_001.pdf",
        file_type="pdf",
        document_type="invoice",
        vendor_id=vendor_id,
        status="stored",
        confidence=0.98,
    )

    updated_doc = db.get_document_with_fields(doc_id)
    assert updated_doc["status"] == "stored"
    assert updated_doc["confidence"] == 0.98
    assert updated_doc["vendor_id"] == vendor_id


def test_save_document_fields_replacement():
    doc_id = "doc_fields_replace"
    db.save_document(doc_id, "h_replace", "test.pdf", "pdf", "invoice")

    # Initial fields insertion
    initial_fields = {
        "invoice_number": ("INV-999", "text"),
        "total_amount": (1500.50, "number"),
        "invoice_date": ("2026-08-11", "date"),
    }
    inserted_count = db.save_document_fields(doc_id, initial_fields)
    assert inserted_count == 3

    doc_with_fields = db.get_document_with_fields(doc_id)
    assert doc_with_fields["fields"]["invoice_number"] == "INV-999"
    assert doc_with_fields["fields"]["total_amount"] == 1500.50

    # Reprocessing: save new set of fields for same document_id
    reprocessed_fields = {
        "invoice_number": ("INV-999-REVISED", "text"),
        "total_amount": (1800.00, "number"),
        "payment_terms": ("Net 30", "text"),
    }
    new_count = db.save_document_fields(doc_id, reprocessed_fields)
    assert new_count == 3

    # Confirm old field values were replaced and not duplicated
    final_doc = db.get_document_with_fields(doc_id)
    assert len(final_doc["fields"]) == 3
    assert final_doc["fields"]["invoice_number"] == "INV-999-REVISED"
    assert final_doc["fields"]["total_amount"] == 1800.00
    assert final_doc["fields"]["payment_terms"] == "Net 30"
    assert "invoice_date" not in final_doc["fields"]


def test_get_document_with_fields_reassembles_nested_dict():
    doc_id = "doc_reassemble"
    db.save_document(doc_id, "h_reassemble", "resume.pdf", "pdf", "resume")

    db.save_document_fields(doc_id, {
        "candidate_name": ("John Doe", "text"),
        "email": ("john@example.com", "text"),
        "years_experience": (5.5, "number"),
    })

    result = db.get_document_with_fields(doc_id)
    assert result is not None
    assert result["document_id"] == doc_id
    assert isinstance(result["fields"], dict)
    assert result["fields"]["candidate_name"] == "John Doe"
    assert result["fields"]["email"] == "john@example.com"
    assert result["fields"]["years_experience"] == 5.5


def test_list_documents_filtering():
    v1_id = db.save_vendor("Vendor A", "Address A")
    v2_id = db.save_vendor("Vendor B", "Address B")

    db.save_document("doc_1", "h1", "f1.pdf", "pdf", document_type="invoice", vendor_id=v1_id, status="stored")
    db.save_document("doc_2", "h2", "f2.pdf", "pdf", document_type="invoice", vendor_id=v2_id, status="processing")
    db.save_document("doc_3", "h3", "f3.pdf", "pdf", document_type="resume", vendor_id=v1_id, status="stored")

    # Filter by document_type
    invoices = db.list_documents(document_type="invoice")
    assert len(invoices) == 2
    assert {d["document_id"] for d in invoices} == {"doc_1", "doc_2"}

    # Filter by vendor_id
    vendor1_docs = db.list_documents(vendor_id=v1_id)
    assert len(vendor1_docs) == 2
    assert {d["document_id"] for d in vendor1_docs} == {"doc_1", "doc_3"}

    # Filter by status
    stored_docs = db.list_documents(status="stored")
    assert len(stored_docs) == 2
    assert {d["document_id"] for d in stored_docs} == {"doc_1", "doc_3"}

    # Filter combined (invoice + vendor1 + stored)
    combined = db.list_documents(document_type="invoice", vendor_id=v1_id, status="stored")
    assert len(combined) == 1
    assert combined[0]["document_id"] == "doc_1"


def test_link_vendor_to_document():
    doc_id = "doc_link_vendor"
    v_id = db.save_vendor("Supplier X", "Loc X")
    db.save_document(doc_id, "h_link", "file.pdf", "pdf", "invoice")

    success = db.link_vendor_to_document(doc_id, v_id)
    assert success is True

    doc = db.get_document_with_fields(doc_id)
    assert doc["vendor_id"] == v_id
