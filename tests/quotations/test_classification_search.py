import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.persistence.models import Base, BillingVendor, BillingCustomer, SearchAlias
from app.quotation_extraction.classifier import classify_document_text
from app.quotation_extraction.loader import get_or_create_vendor, get_or_create_customer
from app.quotation_extraction.search import seed_search_aliases, expand_query


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing database helpers."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_classify_document_text_heuristics():
    """Verify that heuristic document type classification rules work correctly."""
    # Proforma
    doc_type, conf, reason = classify_document_text("Invoice details: PROFORMA INVOICE No 123")
    assert doc_type == "invoice_proforma"
    assert conf == Decimal("1.000")

    # Purchase Order
    doc_type, conf, reason = classify_document_text("This is our Purchase Order PO #887")
    assert doc_type == "purchase_order"
    assert conf == Decimal("1.000")

    # Tax Invoice
    doc_type, conf, reason = classify_document_text("TAX INVOICE Invoice No: INV-456")
    assert doc_type == "invoice_final"
    assert conf == Decimal("1.000")

    # Quotation
    doc_type, conf, reason = classify_document_text("QUOTATION Price offer validity date is tomorrow")
    assert doc_type == "quotation"
    assert conf == Decimal("0.950")


def test_get_or_create_vendor_deduplication(db_session):
    """Verify that vendor lookup correctly matches by GSTIN or fuzzy name to prevent duplicates."""
    # Create initial vendor
    v1_id = get_or_create_vendor(db_session, "AIC Enterprises Pvt Ltd", "29AASCA0900A1Z3")
    db_session.commit()
    assert v1_id is not None

    # Match by exact GSTIN
    v2_id = get_or_create_vendor(db_session, "AIC Enterprises", "29AASCA0900A1Z3")
    assert v2_id == v1_id

    # Match by fuzzy name (no GSTIN provided)
    v3_id = get_or_create_vendor(db_session, "AIC Enterprises Private Limited", None)
    assert v3_id == v1_id

    # Create new vendor if no match
    v4_id = get_or_create_vendor(db_session, "Different Vendor", "29BBBBB1234A1Z1")
    assert v4_id != v1_id

    # Check database row count
    assert db_session.query(BillingVendor).count() == 2


def test_get_or_create_customer_deduplication(db_session):
    """Verify that customer lookup matches by GSTIN or fuzzy name."""
    c1_id = get_or_create_customer(db_session, "East Point College of Pharmacy", "29EEEEE1234A1Z2")
    db_session.commit()

    # Exact match GSTIN
    c2_id = get_or_create_customer(db_session, "East Point College", "29EEEEE1234A1Z2")
    assert c2_id == c1_id

    # Fuzzy name match
    c3_id = get_or_create_customer(db_session, "East Point College of Pharmacy Ltd.", None)
    assert c3_id == c1_id

    assert db_session.query(BillingCustomer).count() == 1


def test_expand_query_synonyms(db_session):
    """Verify that search query terms are correctly expanded using seeded aliases."""
    seed_search_aliases(db_session)
    db_session.commit()

    # Expand "qty" -> should include "qty" and "quantity"
    exp_qty = expand_query(db_session, "qty")
    assert len(exp_qty) == 1
    assert "qty" in exp_qty[0]
    assert "quantity" in exp_qty[0]

    # Expand "ext" -> should include "ext" and "extrapure"
    exp_ext = expand_query(db_session, "ext")
    assert len(exp_ext) == 1
    assert "ext" in exp_ext[0]
    assert "extrapure" in exp_ext[0]

    # Multiple terms
    exp_multi = expand_query(db_session, "qty mtrl")
    assert len(exp_multi) == 2
    assert "quantity" in exp_multi[0]
    assert "material" in exp_multi[1]
