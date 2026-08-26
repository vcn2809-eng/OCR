"""Tests for Vendor API endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.persistence import database
from app.persistence.models import Base


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


def test_vendor_api_flow():
    with TestClient(app) as client:
        # 1. List vendors (should be empty initially)
        res = client.get("/vendors")
        assert res.status_code == 200
        assert res.json() == []

        # 2. Create Vendor 1
        res = client.post("/vendors", json={"vendor_name": "AIC Enterprises", "address": "Peenya, Bangalore"})
        assert res.status_code == 200
        data = res.json()
        assert "vendor_id" in data
        v1_id = data["vendor_id"]

        # 3. Create Vendor 2
        res = client.post("/vendors", json={"vendor_name": "SRL Fine Chemicals", "address": "Mumbai, MH"})
        assert res.status_code == 200
        v2_id = res.json()["vendor_id"]

        # 4. List vendors (should return sorted name+id)
        res = client.get("/vendors")
        assert res.status_code == 200
        list_data = res.json()
        assert len(list_data) == 2
        assert list_data[0] == {"vendor_id": v1_id, "vendor_name": "AIC Enterprises"}
        assert list_data[1] == {"vendor_id": v2_id, "vendor_name": "SRL Fine Chemicals"}

        # 5. Get vendor details
        res = client.get(f"/vendors/{v1_id}")
        assert res.status_code == 200
        detail = res.json()
        assert detail["vendor_id"] == v1_id
        assert detail["vendor_name"] == "AIC Enterprises"
        assert detail["address"] == "Peenya, Bangalore"

        # 6. Get non-existent vendor (should return 404)
        res = client.get("/vendors/invalid-id-999")
        assert res.status_code == 404
