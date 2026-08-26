"""Tests for Vendor persistence functions using an in-memory database."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.persistence import database, db
from app.persistence.models import Base, Vendor


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


def test_save_vendor_insert_and_upsert():
    # Insert new vendor
    v1_id = db.save_vendor("Acme Corp", "123 Main St")
    assert v1_id is not None
    assert len(v1_id) > 0

    # Retrieve vendor
    v1 = db.get_vendor_by_id(v1_id)
    assert v1 is not None
    assert v1["vendor_name"] == "Acme Corp"
    assert v1["address"] == "123 Main St"

    # Save SAME vendor_name again with a different address (should update in place)
    v2_id = db.save_vendor("Acme Corp", "456 New Road")
    assert v2_id == v1_id  # Same vendor_id returned

    # Verify no duplicate row was created
    vendors = db.list_vendors()
    assert len(vendors) == 1
    assert vendors[0]["vendor_id"] == v1_id
    assert vendors[0]["vendor_name"] == "Acme Corp"

    # Confirm address updated in place
    v_updated = db.get_vendor_by_id(v1_id)
    assert v_updated["address"] == "456 New Road"


def test_list_vendors_returns_name_and_id_sorted():
    db.save_vendor("Zebra Supplies", "Address Z")
    db.save_vendor("Alpha Traders", "Address A")
    db.save_vendor("Beta Logistics", "Address B")

    vendors = db.list_vendors()
    assert len(vendors) == 3

    # Confirm returns ONLY vendor_id and vendor_name
    for v in vendors:
        assert "vendor_id" in v
        assert "vendor_name" in v
        assert "address" not in v

    # Confirm alphabetical sorting by vendor_name
    names = [v["vendor_name"] for v in vendors]
    assert names == ["Alpha Traders", "Beta Logistics", "Zebra Supplies"]


def test_get_vendor_by_id():
    # Found case
    vid = db.save_vendor("Gamma Inc", "789 Pine Ave")
    vendor = db.get_vendor_by_id(vid)
    assert vendor is not None
    assert vendor["vendor_id"] == vid
    assert vendor["vendor_name"] == "Gamma Inc"
    assert vendor["address"] == "789 Pine Ave"

    # Not-found case
    non_existent = db.get_vendor_by_id("non-existent-uuid")
    assert non_existent is None
