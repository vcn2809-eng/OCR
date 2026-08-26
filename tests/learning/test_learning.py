"""Tests for the Learning Agent."""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.learning.agent import (
    learn_alias,
    resolve_alias,
    extract_partial_values,
    learn_from_document,
    get_all_learned_aliases,
    bulk_learn_aliases,
    _in_memory_aliases,
)
from app.learning.exceptions import InvalidAliasError
from app.learning.models import AliasMapping, MatchResult
from app.persistence import database, agent as persistence_agent
from app.persistence.models import Base
from app.schema_mapping.agent import map_fields


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Setup in-memory SQLite database and reset learning agent cache for clean test runs."""
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    test_session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)

    monkeypatch.setattr(database, "_engine", test_engine)
    monkeypatch.setattr(database, "_SessionFactory", test_session_factory)

    database.init_db()

    # Reset cache
    import app.learning.agent as learning_agent
    learning_agent._is_cache_initialized = False
    learning_agent._in_memory_aliases.clear()

    yield

    Base.metadata.drop_all(test_engine)


def test_learn_and_resolve_exact_alias():
    mapping = learn_alias("mtrl", "materials")
    assert mapping.alias == "mtrl"
    assert mapping.canonical_name == "materials"

    match = resolve_alias("mtrl")
    assert match is not None
    assert match.canonical_name == "materials"
    assert match.match_type in ("exact", "alias")


def test_abbreviation_matching():
    match_qty = resolve_alias("qty")
    assert match_qty is not None
    assert match_qty.canonical_name == "quantity"
    assert match_qty.match_type in ("exact", "alias", "abbreviation")

    match_desc = resolve_alias("desc")
    assert match_desc is not None
    assert match_desc.canonical_name == "description"


def test_fuzzy_matching_with_typo():
    learn_alias("materials", "materials")
    match = resolve_alias("materiass", threshold=0.7)
    assert match is not None
    assert match.canonical_name == "materials"
    assert match.match_type == "fuzzy"


def test_extract_partial_values_from_text():
    raw_text = "Check item mtrl specification and qty 100"
    matches = extract_partial_values(raw_text)

    canonical_names = [m.canonical_name for m in matches]
    assert "materials" in canonical_names
    assert "quantity" in canonical_names


def test_learn_from_document_extractions():
    raw_keys = ["mtrl_cost", "vendor_id"]
    mapped_record = {"material_cost": 500.0, "vendor_name": "ACME"}

    count = learn_from_document(raw_keys, mapped_record)
    assert count >= 1

    match = resolve_alias("mtrl_cost")
    assert match is not None
    assert match.canonical_name == "material_cost"


def test_bulk_learn_aliases():
    pairs = [("inv", "invoice_number"), ("cust_name", "customer_name")]
    learned_count = bulk_learn_aliases(pairs)
    assert learned_count == 2

    match = resolve_alias("cust_name")
    assert match is not None
    assert match.canonical_name == "customer_name"


def test_invalid_alias_raises_error():
    with pytest.raises(InvalidAliasError):
        learn_alias("", "materials")


def test_schema_mapping_uses_learning_agent():
    learn_alias("mtrl", "materials")
    raw_row = {"mtrl": "Stainless Steel"}

    # 'mtrl' is not in field_mappings.yaml, so schema_mapping falls back to Learning Agent
    mapped = map_fields(raw_row, "invoice")
    assert mapped.get("materials") == "Stainless Steel"
